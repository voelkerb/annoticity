import fs from "node:fs/promises";
import path from "node:path";
import { config } from "./config.js";
import { Dataset } from "./dataset.js";
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

const decoded = new Map();

async function decodeDay(meter, day) {
  const key = `${meter}:${day}`;
  if (decoded.has(key)) {
    const v = decoded.get(key);
    decoded.delete(key); decoded.set(key, v);
    return v;
  }
  const result = await once("decode:" + key, async () => {
    const file = await ensureFile(`summary/50Hz/${meter}/${meter}_${day.replaceAll("-", "_")}__00_00_00.mkv`);
    const info = await probe(file);
    if (!info.audio.length) throw new Error("No data stream in FIRED file");
    const data = {}, measures = [];
    const multi = info.audio.length > 1;
    for (const [s, stream] of info.audio.entries()) {
      const channels = deinterleave(await decodeAudio(file, stream.index), stream.channels);
      const names = stream.measures ?? channels.map((_, i) => `ch${i}`);
      channels.forEach((arr, c) => {
        const id = multi ? `${names[c]}_l${s + 1}` : names[c];
        data[id] = arr;
        measures.push(id);
      });
    }
    const first = info.audio[0];
    return { data, measures, sampleRate: first.sampleRate, t0: first.timestamp ?? zonedDayStart(day, tz) };
  });
  decoded.set(key, result);
  while (decoded.size > 3) decoded.delete(decoded.keys().next().value);
  return result;
}

/** Order measures so that power channels come first (L1, L2, L3 for the smart meter). */
function sortMeasures(ids) {
  const rank = (id) => ["p", "q", "s"].indexOf(id.split("_l")[0]);
  return [...ids].sort((a, b) => (a.split("_l")[1] ?? "").localeCompare(b.split("_l")[1] ?? "") || rank(a) - rank(b));
}

export async function loadFiredDay(meter, day) {
  const meters = await listMeters();
  const info = meters.find((m) => m.id === meter);
  if (!info) throw Object.assign(new Error(`Unknown meter ${meter}`), { status: 404 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw Object.assign(new Error("day must be YYYY-MM-DD"), { status: 400 });
  const days = await listDays(meter);
  if (!days.includes(day)) throw Object.assign(new Error(`No data for ${meter} on ${day}`), { status: 404 });

  const d = await decodeDay(meter, day);
  const dayStart = zonedDayStart(day, tz);
  const ordered = sortMeasures(d.measures);
  const legs = ordered.filter((id) => /^p_l\d$/.test(id));
  const preferred = ordered.includes("p") ? ["p"] : legs.length ? legs : ordered.slice(0, 1);
  return new Dataset({
    title: info.smartmeter ? "Smart meter" : `${info.label[0].toUpperCase()}${info.label.slice(1)}`,
    info: info.details.join(" · "),
    tz,
    t0: d.t0,
    sampleRate: d.sampleRate,
    measures: ordered,
    data: d.data,
    source: "fired",
    meta: {
      meter, day, dayStart, defaultMeasures: preferred,
      highFreq: true, label: `${meter} · ${day}`,
    },
  });
}

const HF_SECONDS = 600;

/** Raw voltage/current (2 kHz appliances, 8 kHz smart meter) for a short window. */
export async function loadHighFreq(ds, start, stop) {
  const { meter } = ds.meta;
  const first = Math.floor(start / HF_SECONDS) * HF_SECONDS;
  const parts = [];
  for (let t = first; t < stop; t += HF_SECONDS) {
    const name = `${meter}_${fileStamp(t, tz)}.mkv`;
    let file;
    try { file = await ensureFile(`highFreq/${meter}/${name}`); } catch (e) { if (e.status === 404) continue; throw e; }
    const info = await probe(file);
    const arrays = {};
    const multi = info.audio.length > 1;
    for (const [s, stream] of info.audio.entries()) {
      const ch = deinterleave(await decodeAudio(file, stream.index), stream.channels);
      (stream.measures ?? ["v", "i"]).forEach((m, c) => (arrays[multi ? `${m}_l${s + 1}` : m] = ch[c]));
    }
    parts.push({ t0: info.audio[0].timestamp ?? t, sampleRate: info.audio[0].sampleRate, arrays });
  }
  if (!parts.length) throw Object.assign(new Error("No raw waveform available for this time range"), { status: 404 });
  const { sampleRate } = parts[0];
  const ids = Object.keys(parts[0].arrays);
  const t0 = Math.max(start, parts[0].t0);
  const n = Math.max(0, Math.floor((Math.min(stop, parts.at(-1).t0 + parts.at(-1).arrays[ids[0]].length / sampleRate) - t0) * sampleRate));
  const data = Object.fromEntries(ids.map((id) => [id, new Float32Array(n)]));
  for (const part of parts) {
    const offset = Math.round((part.t0 - t0) * sampleRate);
    for (const id of ids) {
      const src = part.arrays[id];
      for (let i = Math.max(0, -offset); i < src.length && offset + i < n; i++) data[id][offset + i] = src[i];
    }
  }
  return new Dataset({ title: ds.title, tz, t0, sampleRate, measures: ids, data, source: "fired-hf" });
}
