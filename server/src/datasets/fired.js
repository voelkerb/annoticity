import path from "node:path";
import { config } from "../config.js";
import { probe, decodeAudio, deinterleave } from "../ffmpeg.js";
import { fileStamp, zonedDayStart } from "../tz.js";
import { cachedFile, httpError, once } from "../cache.js";
import { capitalize, defaultMeasures, sortMeasures } from "./common.js";

const { baseUrl, user, password, tz } = config.fired;
const authHeader = "Basic " + Buffer.from(`${user}:${password}`).toString("base64");
const memo = new Map();

async function remote(subPath) {
  const res = await fetch(new URL(subPath, baseUrl), { headers: { Authorization: authHeader } });
  if (!res.ok) throw httpError(res.status === 404 ? 404 : 502, `FIRED server answered ${res.status} for ${subPath}`);
  return res;
}

/** Download a remote file into the local cache (atomic, de-duplicated). */
function ensureFile(subPath) {
  return cachedFile(path.join(config.cacheDir, "FIRED", subPath), async () => Buffer.from(await (await remote(subPath)).arrayBuffer()));
}

function remoteJson(name) {
  if (!memo.has(name)) memo.set(name, remote(name).then((r) => r.json()).catch((e) => { memo.delete(name); throw e; }));
  return memo.get(name);
}

async function meters() {
  const [mapping, devices] = await Promise.all([remoteJson("info/deviceMapping.json"), remoteJson("info/deviceInfo.json")]);
  return Object.entries(mapping).map(([id, m]) => {
    const smart = id.startsWith("smartmeter");
    const details = smart ? [] : m.appliances.map((a) => devices[a]).filter(Boolean).map((d) => `${d.brand} ${d.model}`.trim());
    return {
      id,
      label: smart ? "Aggregated (smart meter, all phases)" : capitalize(m.appliances.join(", ")),
      details,
      aggregate: smart,
      short: id.replace("powermeter", "PM ").replace("smartmeter", "SM "),
      highFreq: true,
    };
  });
}

/** Days with a 50 Hz summary file for the given meter. */
async function days(meter) {
  const key = "days:" + meter;
  const hit = memo.get(key);
  if (hit && Date.now() - hit.at < 3600e3) return hit.days;
  const html = await (await remote(`summary/50Hz/${meter}/`)).text();
  const list = [...html.matchAll(new RegExp(`href="${meter}_(\\d{4})_(\\d{2})_(\\d{2})__00_00_00\\.mkv"`, "g"))]
    .map((m) => `${m[1]}-${m[2]}-${m[3]}`);
  memo.set(key, { at: Date.now(), days: list });
  return list;
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

/** One FIRED day at 50 Hz. */
async function day(meter, d, info) {
  const name = `${meter}_${d.replaceAll("-", "_")}__00_00_00`;
  const decoded = await decodeFile(await ensureFile(`summary/50Hz/${meter}/${name}.mkv`));
  const measures = sortMeasures(Object.keys(decoded.data));
  return {
    header: {
      title: info.aggregate ? "Smart meter" : info.label,
      info: info.details.join(" · "),
      tz,
      t0: decoded.t0 ?? zonedDayStart(d, tz),
      sampleRate: decoded.sampleRate,
      measures,
      meta: { defaultMeasures: defaultMeasures(measures) },
    },
    channels: measures.map((m) => decoded.data[m]),
  };
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
    // FIRED stores raw current in mA; the UI expects A
    for (const [id, arr] of Object.entries(d.data)) if (/^i(_|$)/.test(id)) for (let k = 0; k < arr.length; k++) arr[k] /= 1000;
    return { ...d, t0: d.t0 ?? t };
  });
  hfCache.set(sub, part);
  while (hfCache.size > 6) hfCache.delete(hfCache.keys().next().value);
  return part;
}

/** Raw voltage/current (2 kHz appliances, 8 kHz smart meter) for a short window. */
async function waveform(meter, start, stop) {
  const parts = [];
  for (let t = Math.floor(start / HF_SECONDS) * HF_SECONDS; t < stop; t += HF_SECONDS) {
    const p = await hfPart(meter, t);
    if (p) parts.push(p);
  }
  if (!parts.length) return null;
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
  return { header: { title: meter, tz, t0, sampleRate, measures: ids }, channels: out };
}

export default {
  id: "fired",
  name: "FIRED",
  description: "Appliance-level and aggregate power of a German apartment, raw waveforms at 2–8 kHz",
  url: "https://github.com/voelkerb/FIRED_dataset_helper",
  tz,
  status: async () => ({ available: true }),
  meters,
  days,
  day,
  waveform,
};
