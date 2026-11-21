import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { config } from "../config.js";
import { cachedFile, httpError, once } from "../cache.js";
import { dayFormatter, defaultMeasures, sortMeasures, toGrid, typicalPeriod } from "./common.js";

/**
 * Index a "timestamp value [value ...]" text file by local day: { "YYYY-MM-DD": [startByte, endByte] }.
 * Files are chronological, so each day is one contiguous byte range.
 */
export async function indexDays(file, tz) {
  const toDay = dayFormatter(tz);
  const days = {};
  let pos = 0, lineStart = 0, current = null, rangeStart = 0;
  let ts = 0, inTs = true, digits = 0;
  for await (const chunk of fs.createReadStream(file, { highWaterMark: 1 << 20 })) {
    for (let i = 0; i < chunk.length; i++, pos++) {
      const c = chunk[i];
      if (c === 10) {
        if (digits) {
          const d = toDay(ts);
          if (d !== current) {
            if (current) days[current] = [rangeStart, lineStart];
            current = d; rangeStart = lineStart;
          }
        }
        lineStart = pos + 1; ts = 0; inTs = true; digits = 0;
      } else if (inTs) {
        if (c >= 48 && c <= 57) { ts = ts * 10 + (c - 48); digits++; }
        else if (digits) inTs = false;
      }
    }
  }
  if (digits) {
    const d = toDay(ts);
    if (d !== current) { if (current) days[current] = [rangeStart, lineStart]; current = d; rangeStart = lineStart; }
  }
  if (current) days[current] = [rangeStart, pos];
  return days;
}

/** Parse "timestamp v1 v2 ..." lines into a time array and one Float32Array per value column. */
export function parseLines(text, columns) {
  const lines = text.split("\n");
  const ts = new Float64Array(lines.length);
  const cols = Array.from({ length: columns }, () => new Float32Array(lines.length));
  let n = 0;
  for (const line of lines) {
    const parts = line.trim().split(/[\s,]+/);
    const t = Number(parts[0]);
    if (!Number.isFinite(t) || parts.length < columns + 1) continue;
    ts[n] = t;
    for (let c = 0; c < columns; c++) cols[c][n] = Number(parts[c + 1]);
    n++;
  }
  return { ts: ts.subarray(0, n), cols: cols.map((c) => c.subarray(0, n)) };
}

/** Merge per-file grids (same period, epoch aligned) into one set of channels. */
function mergeGrids(grids, period) {
  const valid = grids.filter((g) => g.channels[0]?.length);
  if (!valid.length) return null;
  const t0 = Math.min(...valid.map((g) => g.t0));
  const end = Math.max(...valid.map((g) => g.t0 + g.channels[0].length * period));
  const n = Math.round((end - t0) / period);
  const channels = grids.flatMap((g) => g.channels.map((src) => {
    const out = new Float32Array(n).fill(NaN);
    if (src.length) out.set(src, Math.round((g.t0 - t0) / period));
    return out;
  }));
  return { t0, channels };
}

/**
 * Datasets distributed as folders of "house_N/channel_M.dat" text files plus a labels.dat
 * (REDD low_freq, UK-DALE). Days are indexed once per file and cached on disk.
 */
export function datFolderProvider({ id, name, description, url, paperUrl, tz, base, env, measureOf, extraMeters = () => [] }) {
  const indexes = new Map();

  async function housesDir() {
    if (!base) return null;
    for (const dir of [path.join(base, "low_freq"), base]) {
      if ((await fsp.readdir(dir).catch(() => [])).some((n) => /^house_\d+$/.test(n))) return dir;
    }
    return null;
  }

  async function status() {
    if (!base) return { available: false, reason: `Set ${env} in server/.env to the local ${name} folder` };
    if (!(await housesDir())) return { available: false, reason: `No house_N folders found in ${env}=${base}` };
    return { available: true };
  }

  async function labels(dir) {
    const text = await fsp.readFile(path.join(dir, "labels.dat"), "utf8").catch(() => "");
    return Object.fromEntries(text.split("\n").map((l) => l.trim().split(/\s+/)).filter((p) => p.length >= 2).map(([n, ...rest]) => [n, rest.join(" ")]));
  }

  let scanned = null;
  const scan = () => {
    if (!scanned || Date.now() - scanned.at > 300e3) {
      scanned = { at: Date.now(), value: scanHouses().catch((e) => { scanned = null; throw e; }) };
    }
    return scanned.value;
  };

  async function scanHouses() {
    const root = await housesDir();
    if (!root) throw httpError(503, (await status()).reason);
    const list = [];
    const houses = (await fsp.readdir(root)).map((n) => /^house_(\d+)$/.exec(n)).filter(Boolean).sort((a, b) => a[1] - b[1]);
    for (const [dirName, house] of houses) {
      const dir = path.join(root, dirName);
      const names = await labels(dir);
      const files = await fsp.readdir(dir);
      const channels = files.map((f) => /^channel_(\d+)\.dat$/.exec(f)).filter(Boolean).map((m) => +m[1]).sort((a, b) => a - b);
      const meters = channels.map((c) => {
        const label = names[c] ?? `channel ${c}`;
        return {
          id: `h${house}-c${c}`, label: label.replaceAll("_", " "), group: `House ${house}`, details: [`channel ${c}`],
          aggregate: /^(mains|aggregate)$/i.test(label), short: `H${house} C${c}`, highFreq: false,
          sources: [{ file: path.join(dir, `channel_${c}.dat`), measures: [measureOf(label)] }],
        };
      });
      list.push(...extraMeters({ house, dir, files, meters }), ...meters);
    }
    return list;
  }

  async function index(file) {
    const stat = await fsp.stat(file);
    const key = `${file}:${stat.size}:${stat.mtimeMs}`;
    if (indexes.has(key)) return indexes.get(key);
    const dest = path.join(config.cacheDir, "index", id, crypto.createHash("sha1").update(key).digest("hex") + ".json");
    const days = await once("index:" + key, async () => {
      const cacheFile = await cachedFile(dest, async () => Buffer.from(JSON.stringify(await indexDays(file, tz))));
      return JSON.parse(await fsp.readFile(cacheFile, "utf8"));
    });
    indexes.set(key, days);
    return days;
  }

  async function find(meterId) {
    const m = (await scan()).find((x) => x.id === meterId);
    if (!m) throw httpError(404, `Unknown meter ${meterId}`);
    return m;
  }

  async function readRange(file, [a, b]) {
    const fh = await fsp.open(file);
    try {
      const buf = Buffer.alloc(b - a);
      await fh.read(buf, 0, buf.length, a);
      return buf.toString("latin1");
    } finally { await fh.close(); }
  }

  return {
    id, name, description, url, paperUrl, tz, status,
    meters: async () => (await scan()).map(({ sources: _s, ...m }) => m),
    async days(meterId) {
      const m = await find(meterId);
      const sets = await Promise.all(m.sources.map((s) => index(s.file)));
      return [...new Set(sets.flatMap((d) => Object.keys(d)))].sort();
    },
    async day(meterId, day, info) {
      const m = await find(meterId);
      const parsed = [];
      for (const src of m.sources) {
        const range = (await index(src.file))[day];
        parsed.push(range ? parseLines(await readRange(src.file, range), src.measures.length) : { ts: new Float64Array(0), cols: src.measures.map(() => new Float32Array(0)) });
      }
      const longest = parsed.reduce((a, b) => (b.ts.length > a.ts.length ? b : a));
      if (!longest.ts.length) throw httpError(404, `No data for ${meterId} on ${day}`);
      const period = typicalPeriod(longest.ts);
      const merged = mergeGrids(parsed.map((p) => toGrid(p.ts, p.cols, period)), period);
      const ids = m.sources.flatMap((s) => s.measures);
      const measures = sortMeasures(ids);
      return {
        header: {
          title: info.label[0].toUpperCase() + info.label.slice(1),
          info: `${m.group} · ${m.details.join(", ")} · ${period} s readings`,
          tz,
          t0: merged.t0,
          sampleRate: 1 / period,
          measures,
          meta: { defaultMeasures: defaultMeasures(measures) },
        },
        channels: measures.map((x) => merged.channels[ids.indexOf(x)]),
      };
    },
  };
}
