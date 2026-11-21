import fs from "node:fs/promises";
import path from "node:path";
import h5wasm from "h5wasm/node";
import { config } from "../config.js";
import { ftpSource } from "../ftp.js";
import { cachedFile, httpError, once } from "../cache.js";
import { zonedDayStart } from "../tz.js";
import { dayFormatter, defaultMeasures, sortMeasures } from "./common.js";

const { tz } = config.blond;
const ftp = ftpSource(config.blond);
const SETS = ["BLOND-50", "BLOND-250"];
const MEDALS = 15, SOCKETS = 6;
/** Raw mains waveforms (50/250 kHz) are averaged down to at most this rate before sending. */
const MAX_WAVE_RATE = 12_500;
const RAW_FILES_KEPT = 6;
const memo = new Map();
const localDay = dayFormatter(tz);

function memoize(key, ttlMs, fn) {
  if (config.cacheTtlMs) ttlMs = Math.min(ttlMs, config.cacheTtlMs);
  const hit = memo.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.value;
  const value = fn().catch((e) => { if (memo.get(key)?.value === value) memo.delete(key); throw e; });
  memo.set(key, { at: Date.now(), value });
  if (Number.isFinite(ttlMs)) {
    const timer = setTimeout(() => { if (memo.get(key)?.value === value) memo.delete(key); }, ttlMs);
    timer.unref();
  }
  return value;
}

const cachePath = (sub) => path.join(config.cacheDir, "BLOND", sub);
const download = (sub) => cachedFile(cachePath(sub), () => ftp.download(sub));

/** Every recorded day, mapped to the BLOND set that contains it. */
const remoteDaySets = () => memoize("remote-days", 86400e3, async () => {
  const map = new Map();
  for (const set of SETS) for (const d of await ftp.list(set + "/")) if (/^\d{4}-\d{2}-\d{2}$/.test(d)) map.set(d, set);
  return map;
});

const daySets = () => memoize("days", 86400e3, async () => {
  if (!config.blond.path) return remoteDaySets();
  const files = await fs.readdir(path.join(config.blond.path, "tmp"));
  return new Map(files.map((name) => /^summary-(\d{4}-\d{2}-\d{2})-(?:clear|medal-\d+)\.hdf5$/.exec(name))
    .filter(Boolean).map((m) => [m[1], null]));
});

const applianceLog = () => memoize("log", config.cacheTtlMs || Infinity, async () => {
  const file = config.blond.path ? path.join(config.blond.path, "appliance_log.json") : await download("appliance_log.json");
  return JSON.parse(await fs.readFile(file, "utf8"));
});

function parseMeter(id) {
  if (id === "clear") return { medal: "clear" };
  const m = /^medal-(\d+)-s(\d)$/.exec(id);
  if (!m || +m[1] < 1 || +m[1] > MEDALS || +m[2] < 1 || +m[2] > SOCKETS) throw httpError(404, `Unknown meter ${id}`);
  return { medal: `medal-${m[1]}`, n: +m[1], socket: +m[2] };
}

const applianceName = (a) => [a?.class_name, a?.appliance_name].filter(Boolean).join(" · ") || "Nothing connected";

/** Appliances plugged into a socket, optionally only those present on `day`. */
function appliancesOf(log, n, socket, day) {
  const entries = log[`MEDAL-${n}`]?.entries ?? [];
  const at = (e) => e.timestamp.slice(0, 10);
  let chosen = entries;
  if (day) {
    const before = entries.filter((e) => at(e) <= day);
    chosen = [before.at(-1), ...entries.filter((e) => at(e) === day)].filter(Boolean);
  }
  return [...new Set(chosen.map((e) => applianceName(e[`socket_${socket}`])))];
}

async function meters() {
  const log = await applianceLog();
  const list = [{ id: "clear", label: "Mains (CLEAR, all phases)", details: [], aggregate: true, short: "CLEAR", highFreq: true }];
  for (let n = 1; n <= MEDALS; n++) {
    const phase = log[`MEDAL-${n}`]?.circuit_id ?? "";
    for (let s = 1; s <= SOCKETS; s++) {
      const names = appliancesOf(log, n, s);
      const connected = names.filter((x) => x !== "Nothing connected");
      const classes = [...new Set((connected.length ? connected : names).map((x) => x.split(" · ")[0]))];
      list.push({
        id: `medal-${n}-s${s}`,
        label: classes.join(", "),
        group: `MEDAL ${n}${phase ? ` · ${phase}` : ""}`,
        details: names,
        aggregate: false,
        short: `M${n} S${s}`,
        highFreq: true,
      });
    }
  }
  return list;
}

async function days() {
  return [...(await daySets()).keys()].sort();
}

async function setOf(day) {
  const set = (await remoteDaySets()).get(day);
  if (!set) throw httpError(404, `BLOND has no recording on ${day}`);
  return set;
}

await h5wasm.ready;

function withH5(file, fn) {
  const f = new h5wasm.File(file, "r");
  try { return fn(f); } finally { f.close(); }
}

const attr = (obj, k) => { const v = obj.attrs[k]?.value; return typeof v === "bigint" ? Number(v) : v; };

/** One day of 1 Hz summary data (BLOND's own power, current and voltage RMS values). */
async function day(meter, d, info) {
  const { medal, socket } = parseMeter(meter);
  const name = `summary-${d}-${medal}.hdf5`;
  const local = config.blond.path && path.join(config.blond.path, "tmp", name);
  let file, set;
  try { if (local) await fs.access(local); else throw Object.assign(new Error("No local BLOND path"), { code: "ENOENT" }); file = local; }
  catch (e) {
    if (e.code !== "ENOENT") throw e;
    set = await setOf(d);
    file = await download(`${set}/${d}/${medal}/${name}`);
  }
  const data = withH5(file, (f) => {
    const read = (name) => (f.keys().includes(name) ? Float32Array.from(f.get(name).value) : null);
    const leg = (k, suffix) => {
      const p = read(`real_power${k}`), s = read(`apparent_power${k}`);
      if (!p || !s) return {};
      const q = s.map((sv, i) => Math.sqrt(Math.max(0, sv * sv - p[i] * p[i])));
      return {
        [`p${suffix}`]: p, [`q${suffix}`]: q, [`s${suffix}`]: s,
        [`i_rms${suffix}`]: read(`current_rms${k}`),
        [`v_rms${suffix}`]: read(`voltage_rms${k}`) ?? read("voltage_rms"),
      };
    };
    const channels = socket ? leg(socket, "") : Object.assign({}, leg(1, "_l1"), leg(2, "_l2"), leg(3, "_l3"));
    for (const k of Object.keys(channels)) if (!channels[k]) delete channels[k];
    const delay = attr(f, "delay_after_midnight") ?? 0;
    return { channels, t0: zonedDayStart(d, tz) + delay };
  });
  const measures = sortMeasures(Object.keys(data.channels));
  if (!measures.length) throw httpError(404, `No data for ${meter} on ${d}`);
  const today = socket ? appliancesOf(await applianceLog(), parseMeter(meter).n, socket, d) : [];
  return {
    header: {
      title: socket ? today.join(", ") || info.label : info.label,
      info: `${set ?? "BLOND (local)"} · ${socket ? `${info.group}, socket ${socket}` : "3-phase mains"}`,
      tz,
      t0: data.t0,
      sampleRate: 1,
      measures,
      meta: { defaultMeasures: defaultMeasures(measures) },
    },
    channels: measures.map((m) => data.channels[m]),
  };
}

const RAW_NAME = /^(?:clear|medal-\d+)-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2}(?:\.\d+)?)T([+-]\d{2})(\d{2})-\d+\.hdf5$/;

/** Start time (epoch seconds) encoded in a raw BLOND file name, e.g. medal-3-2016-10-02T00-15-04.928023T+0200-0000149.hdf5 */
export function rawFileStart(name) {
  const m = RAW_NAME.exec(name);
  if (!m) return null;
  const sec = Number(m[4]);
  const whole = Math.floor(sec);
  return Date.parse(`${m[1]}T${m[2]}:${m[3]}:${String(whole).padStart(2, "0")}${m[5]}:${m[6]}`) / 1000 + (sec - whole);
}

async function rawFiles(medal, d) {
  const set = (await remoteDaySets()).get(d);
  if (!set) return [];
  return memoize(`raw:${medal}:${d}`, 86400e3, async () =>
    (await ftp.list(`${set}/${d}/${medal}/`))
      .map((name) => ({ name, sub: `${set}/${d}/${medal}/${name}`, start: rawFileStart(name), set }))
      .filter((f) => f.start != null)
      .sort((a, b) => a.start - b.start));
}

/** Keep only the most recently used raw files on disk; they are 30–120 MB each. */
async function pruneRaw(keep) {
  const dir = cachePath("raw");
  const files = await Promise.all((await fs.readdir(dir).catch(() => [])).filter((f) => f.endsWith(".hdf5"))
    .map(async (f) => ({ f, at: (await fs.stat(path.join(dir, f))).atimeMs })));
  files.sort((a, b) => b.at - a.at);
  for (const { f } of files.slice(RAW_FILES_KEPT)) if (f !== keep) await fs.rm(path.join(dir, f), { force: true });
}

function rawFile(entry) {
  const dest = cachePath(`raw/${entry.name}`);
  return once("raw:" + dest, async () => {
    const file = await cachedFile(dest, () => ftp.download(entry.sub));
    if (!config.cacheTtlMs) {
      const now = new Date();
      await fs.utimes(file, now, now);
      await pruneRaw(entry.name);
    }
    return file;
  });
}

function decimate(src, factor) {
  if (factor <= 1) return src;
  const out = new Float32Array(Math.floor(src.length / factor));
  for (let i = 0; i < out.length; i++) {
    let s = 0;
    for (let k = i * factor, e = k + factor; k < e; k++) s += src[k];
    out[i] = s / factor;
  }
  return out;
}

/** Raw voltage and current for a short window (MEDAL 6.4 kHz, CLEAR mains averaged down to ≤ 12.5 kHz). */
async function waveform(meter, start, stop) {
  const { medal, socket } = parseMeter(meter);
  const dayList = [...new Set([localDay(start - 86400), localDay(start), localDay(stop)])];
  const files = (await Promise.all(dayList.map((d) => rawFiles(medal, d)))).flat().sort((a, b) => a.start - b.start);
  const used = files.filter((f, i) => f.start < stop && (files[i + 1]?.start ?? Infinity) > start);
  if (!used.length) return null;

  const parts = [];
  for (const entry of used) {
    const file = await rawFile(entry);
    parts.push(withH5(file, (f) => {
      const keys = f.keys();
      const first = f.get(keys.find((k) => k.startsWith("voltage")));
      const total = first.shape[0];
      const rate = attr(f, "frequency") ?? (entry.set === "BLOND-250" ? 250_000 : 50_000);
      const factor = Math.max(1, Math.ceil(rate / MAX_WAVE_RATE));
      const i0 = Math.max(0, Math.floor((start - entry.start) * rate / factor) * factor);
      const i1 = Math.min(total, Math.ceil((stop - entry.start) * rate));
      if (i1 <= i0) return null;
      const read = (name) => {
        const ds = f.get(name);
        const cf = attr(ds, "calibration_factor") ?? 1;
        const raw = ds.slice([[i0, i1]]);
        const out = new Float32Array(raw.length);
        for (let k = 0; k < raw.length; k++) out[k] = raw[k] * cf;
        return decimate(out, factor);
      };
      const channels = socket
        ? { v: read("voltage"), i: read(`current${socket}`) }
        : Object.fromEntries([1, 2, 3].flatMap((k) => [[`v_l${k}`, read(`voltage${k}`)], [`i_l${k}`, read(`current${k}`)]]));
      return { t0: entry.start + i0 / rate, sampleRate: rate / factor, channels };
    }));
  }
  const valid = parts.filter(Boolean);
  if (!valid.length) return null;
  const { sampleRate } = valid[0];
  const ids = Object.keys(valid[0].channels);
  const t0 = valid[0].t0;
  const last = valid.at(-1);
  const n = Math.round((last.t0 - t0) * sampleRate) + last.channels[ids[0]].length;
  const out = ids.map(() => new Float32Array(n).fill(NaN));
  for (const part of valid) {
    const offset = Math.round((part.t0 - t0) * sampleRate);
    ids.forEach((id, k) => out[k].set(part.channels[id].subarray(0, Math.max(0, n - offset)), offset));
  }
  return { header: { title: meter, tz, t0, sampleRate, measures: ids }, channels: out };
}

export default {
  id: "blond",
  name: "BLOND",
  description: "Building-Level Office eNvironment Dataset · office in Germany, 3-phase mains and 90 sockets",
  url: "https://mediatum.ub.tum.de/1375836",
  paperUrl: "https://doi.org/10.1038/sdata.2018.48",
  tz,
  status: async () => ({ available: true }),
  meters,
  days,
  day,
  waveform,
};
