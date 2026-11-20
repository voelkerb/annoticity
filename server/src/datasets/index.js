import path from "node:path";
import { config } from "../config.js";
import { encodeChannels } from "../binary.js";
import { cachedFile, httpError } from "../cache.js";
import { isDay } from "./common.js";
import fired from "./fired.js";
import blond from "./blond.js";
import redd from "./redd.js";
import ukdale from "./ukdale.js";
import eco from "./eco.js";

/** Bump when the decoded day format changes so stale cache files are ignored. */
const CACHE_VERSION = "v2";

export const providers = Object.fromEntries([fired, blond, redd, ukdale, eco].map((p) => [p.id, p]));

export function provider(id) {
  const p = providers[id];
  if (!p) throw httpError(404, `Unknown dataset ${id}`);
  return p;
}

export async function listDatasets() {
  return Promise.all(Object.values(providers).map(async (p) => {
    let status;
    try { status = await p.status(); } catch (e) { status = { available: false, reason: e.message }; }
    return { id: p.id, name: p.name, description: p.description, url: p.url, tz: p.tz, waveforms: !!p.waveform, ...status };
  }));
}

async function meterInfo(p, meter) {
  const info = (await p.meters()).find((m) => m.id === meter);
  if (!info) throw httpError(404, `Unknown meter ${meter} in ${p.name}`);
  return info;
}

/** Path of the encoded day (binary channel format), decoded once and then served from disk. */
export async function dayFile(id, meter, day) {
  const p = provider(id);
  if (!isDay(day)) throw httpError(400, "day must be YYYY-MM-DD");
  const info = await meterInfo(p, meter);
  const dest = path.join(config.cacheDir, "decoded", CACHE_VERSION, p.id, meter.replace(/[^\w.-]/g, "_"), `${day}.f32`);
  return cachedFile(dest, async () => {
    if (!(await p.days(meter)).includes(day)) throw httpError(404, `No ${p.name} data for ${meter} on ${day}`);
    const { header, channels } = await p.day(meter, day, info);
    header.meta = { ...header.meta, dataset: p.id, meter, day, highFreq: !!(info.highFreq && p.waveform), label: `${p.name} · ${info.short} · ${day}` };
    return encodeChannels(header, channels);
  });
}

export async function waveform(id, meter, start, stop) {
  const p = provider(id);
  if (!p.waveform) throw httpError(404, `${p.name} has no raw waveforms`);
  if (!/^[\w-]+$/.test(meter)) throw httpError(404, `Unknown meter ${meter}`);
  const out = await p.waveform(meter, start, stop);
  if (!out) throw httpError(404, "No raw waveform available for this time range");
  return encodeChannels(out.header, out.channels);
}
