import fs from "node:fs/promises";
import path from "node:path";
import { config } from "./config.js";
import { encodeChannels } from "./binary.js";
import { probe, decodeAudio, deinterleave } from "./ffmpeg.js";
import { fileStamp, zonedDayStart } from "./tz.js";

const { baseUrl, user, password, tz } = config.fired;
const authHeader = "Basic " + Buffer.from(`${user}:${password}`).toString("base64");
const inflight = new Map();
const memo = new Map();

async function remote(subPath) {
  const res = await fetch(new URL(subPath, baseUrl), { headers: { Authorization: authHeader } });
  if (!res.ok) throw Object.assign(new Error(`FIRED server answered ${res.status} for ${subPath}`), { status: res.status === 404 ? 404 : 502 });
  return res;
}

function once(key, fn) {
  if (!inflight.has(key)) inflight.set(key, fn().finally(() => inflight.delete(key)));
  return inflight.get(key);
}

/** Download a remote file into the local cache (atomic, de-duplicated). */
export function ensureFile(subPath) {
  const dest = path.join(config.cacheDir, "FIRED", subPath);
  return once("file:" + subPath, async () => {
    try { await fs.access(dest); return dest; } catch { /* not cached yet */ }
    await fs.mkdir(path.dirname(dest), { recursive: true });
    const res = await remote(subPath);
    const tmp = `${dest}.${process.pid}.part`;
    await fs.writeFile(tmp, Buffer.from(await res.arrayBuffer()));
    await fs.rename(tmp, dest);
    return dest;
  });
}

async function remoteJson(name) {
  if (!memo.has(name)) memo.set(name, remote(name).then((r) => r.json()).catch((e) => { memo.delete(name); throw e; }));
  return memo.get(name);
}

export async function listMeters() {
  const [mapping, devices] = await Promise.all([remoteJson("info/deviceMapping.json"), remoteJson("info/deviceInfo.json")]);
  return Object.entries(mapping).map(([id, m]) => {
    const smart = id.startsWith("smartmeter");
    const appliances = smart ? ["Whole apartment (aggregated)"] : m.appliances;
    const details = smart ? [] : m.appliances.map((a) => devices[a]).filter(Boolean).map((d) => `${d.brand} ${d.model}`.trim());
    return { id, smartmeter: smart, phase: m.phase, appliances, details, label: smart ? "Aggregated (smart meter)" : m.appliances.join(", ") };
  });
}

/** Days with a 50 Hz summary file for the given meter. */
export async function listDays(meter) {
  const key = "days:" + meter;
  const hit = memo.get(key);
  if (hit && Date.now() - hit.at < 3600e3) return hit.days;
  const res = await remote(`summary/50Hz/${meter}/`);
  const html = await res.text();
  const days = [...html.matchAll(new RegExp(`href="${meter}_(\\d{4})_(\\d{2})_(\\d{2})__00_00_00\\.mkv"`, "g"))]
    .map((m) => `${m[1]}-${m[2]}-${m[3]}`);
  memo.set(key, { at: Date.now(), days });
  return days;
}

/** Order measures so that power channels come first (L1, L2, L3 for the smart meter). */
function sortMeasures(ids) {
  const rank = (id) => ["p", "q", "s"].indexOf(id.split("_l")[0]);
  return [...ids].sort((a, b) => (a.split("_l")[1] ?? "").localeCompare(b.split("_l")[1] ?? "") || rank(a) - rank(b));
}

/** Decode every stream of a FIRED file; multiple streams (smart meter legs) get an `_lN` suffix. */
async function decodeFile(file, fallbackMeasures) {
  const info = await probe(file);
  if (!info.audio.length) throw new Error("No data stream in FIRED file");
  const data = {};
  const multi = info.audio.length > 1;
  for (const [s, stream] of info.audio.entries()) {
    const channels = deinterleave(await decodeAudio(file, stream.index), stream.channels);
    const names = stream.measures ?? fallbackMeasures ?? channels.map((_, i) => `ch${i}`);
    channels.forEach((arr, c) => (data[multi ? `${names[c]}_l${s + 1}` : names[c]] = arr));
  }
  return { data, sampleRate: info.audio[0].sampleRate, t0: info.audio[0].timestamp };
}

/**
 * One FIRED day at 50 Hz in the binary channel format. The encoded result is cached on disk,
 * so after the first request a day is served straight from a file.
 */
export async function firedDayFile(meter, day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw Object.assign(new Error("day must be YYYY-MM-DD"), { status: 400 });
  const meters = await listMeters();
  const info = meters.find((m) => m.id === meter);
  if (!info) throw Object.assign(new Error(`Unknown meter ${meter}`), { status: 404 });
  const name = `${meter}_${day.replaceAll("-", "_")}__00_00_00`;
  const dest = path.join(config.cacheDir, "decoded", meter, `${name}.f32`);
  return once("day:" + dest, async () => {
    try { await fs.access(dest); return dest; } catch { /* decode below */ }
    const days = await listDays(meter);
    if (!days.includes(day)) throw Object.assign(new Error(`No data for ${meter} on ${day}`), { status: 404 });
    const d = await decodeFile(await ensureFile(`summary/50Hz/${meter}/${name}.mkv`));
    const measures = sortMeasures(Object.keys(d.data));
    const legs = measures.filter((id) => /^p_l\d$/.test(id));
    const header = {
      title: info.smartmeter ? "Smart meter" : `${info.label[0].toUpperCase()}${info.label.slice(1)}`,
      info: info.details.join(" · "),
      tz,
      t0: d.t0 ?? zonedDayStart(day, tz),
      sampleRate: d.sampleRate,
      measures,
      meta: {
        meter, day, highFreq: true, label: `${meter} · ${day}`,
        defaultMeasures: measures.includes("p") ? ["p"] : legs.length ? legs : measures.slice(0, 1),
      },
    };
    await fs.mkdir(path.dirname(dest), { recursive: true });
    const tmp = `${dest}.${process.pid}.part`;
    await fs.writeFile(tmp, encodeChannels(header, measures.map((m) => d.data[m])));
    await fs.rename(tmp, dest);
    return dest;
  });
}

const HF_SECONDS = 600;
const hfCache = new Map();

async function hfPart(meter, t) {
  const sub = `highFreq/${meter}/${meter}_${fileStamp(t, tz)}.mkv`;
  if (hfCache.has(sub)) {
    const v = hfCache.get(sub);
    hfCache.delete(sub); hfCache.set(sub, v);
    return v;
  }
  const part = await once("hf:" + sub, async () => {
    let file;
    try { file = await ensureFile(sub); } catch (e) { if (e.status === 404) return null; throw e; }
    const d = await decodeFile(file, ["v", "i"]);
    return { ...d, t0: d.t0 ?? t };
  });
  hfCache.set(sub, part);
  while (hfCache.size > 6) hfCache.delete(hfCache.keys().next().value);
  return part;
}

/** Raw voltage/current (2 kHz appliances, 8 kHz smart meter) for a short window, binary encoded. */
export async function highFreqWindow(meter, start, stop) {
  if (!/^[\w-]+$/.test(meter)) throw Object.assign(new Error(`Unknown meter ${meter}`), { status: 404 });
  const parts = [];
  for (let t = Math.floor(start / HF_SECONDS) * HF_SECONDS; t < stop; t += HF_SECONDS) {
    const p = await hfPart(meter, t);
    if (p) parts.push(p);
  }
  if (!parts.length) throw Object.assign(new Error("No raw waveform available for this time range"), { status: 404 });
  const { sampleRate } = parts[0];
  const ids = Object.keys(parts[0].data);
  const t0 = Math.max(start, parts[0].t0);
  const last = parts.at(-1);
  const n = Math.max(0, Math.floor((Math.min(stop, last.t0 + last.data[ids[0]].length / sampleRate) - t0) * sampleRate));
  const out = ids.map(() => new Float32Array(n));
  for (const part of parts) {
    const offset = Math.round((part.t0 - t0) * sampleRate);
    ids.forEach((id, k) => {
      const src = part.data[id];
      const from = Math.max(0, -offset), to = Math.min(src.length, n - offset);
      if (to > from) out[k].set(src.subarray(from, to), offset + from);
    });
  }
  return encodeChannels({ title: meter, tz, t0, sampleRate, measures: ids }, out);
}
