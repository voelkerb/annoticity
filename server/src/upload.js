import fs from "node:fs/promises";
import path from "node:path";
import { Dataset } from "./dataset.js";
import { probe, decodeAudio, deinterleave, extractSubtitles } from "./ffmpeg.js";

const TIME_COLUMNS = ["timestamp", "ts", "time", "datetime", "date", "datum", "unix", "epoch"];

function bad(message) {
  return Object.assign(new Error(message), { status: 400 });
}

function detectDelimiter(line) {
  const counts = [",", ";", "\t", " "].map((d) => [d, line.split(d).length - 1]);
  counts.sort((a, b) => b[1] - a[1]);
  return counts[0][1] > 0 ? counts[0][0] : ",";
}

/** Convert a time cell to epoch seconds; handles seconds, ms, µs, ns and common date strings. */
export function parseTime(cell) {
  const s = cell.trim();
  if (s === "") return NaN;
  const num = Number(s);
  if (Number.isFinite(num)) {
    const a = Math.abs(num);
    if (a >= 1e17) return num / 1e9;
    if (a >= 1e14) return num / 1e6;
    if (a >= 1e11) return num / 1e3;
    return num;
  }
  const dmy = /^(\d{1,2})[-.](\d{1,2})[-.](\d{4})(.*)$/.exec(s);
  const iso = dmy ? `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}${dmy[4]}` : s;
  const withZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : iso.replace(" ", "T") + (iso.includes("T") || iso.includes(" ") ? "Z" : "T00:00:00Z");
  const ms = Date.parse(withZone);
  return Number.isNaN(ms) ? NaN : ms / 1000;
}

export function parseCsv(text, filename = "upload") {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length < 3) throw bad("The file needs a header row and at least two data rows.");
  const delim = detectDelimiter(lines[0]);
  const rows = lines.map((l) => l.split(delim).map((c) => c.trim().replace(/^"|"$/g, "")));
  const header = rows[0];
  if (header.every((h) => Number.isFinite(Number(h)))) {
    throw bad('Please add a header row, e.g. "timestamp,p". One column must be named one of: ' + TIME_COLUMNS.join(", ") + ".");
  }
  const timeCol = header.findIndex((h) => TIME_COLUMNS.includes(h.toLowerCase()));
  if (timeCol < 0) throw bad("Cannot find a time column. Name it one of: " + TIME_COLUMNS.join(", ") + ".");

  const body = rows.slice(1);
  const valueCols = header.map((h, i) => i).filter((i) => i !== timeCol && body.slice(0, 20).some((r) => Number.isFinite(Number(r[i])) && r[i] !== ""));
  if (!valueCols.length) throw bad("No numeric data columns found.");

  const n = body.length;
  let ts = new Float64Array(n);
  const cols = valueCols.map(() => new Float32Array(n));
  let kept = 0, sorted = true;
  for (const r of body) {
    const t = parseTime(r[timeCol] ?? "");
    if (Number.isNaN(t)) continue;
    if (kept && t < ts[kept - 1]) sorted = false;
    ts[kept] = t;
    valueCols.forEach((c, k) => { const v = r[c] === "" || r[c] === undefined ? NaN : Number(r[c]); cols[k][kept] = v; });
    kept++;
  }
  if (kept < 2) throw bad("Could not parse the time column.");
  ts = ts.slice(0, kept);
  let data = cols.map((c) => c.slice(0, kept));
  if (!sorted) {
    const order = Uint32Array.from(ts.keys()).sort((a, b) => ts[a] - ts[b]);
    ts = Float64Array.from(order, (i) => ts[i]);
    data = data.map((c) => Float32Array.from(order, (i) => c[i]));
  }

  const dts = Float64Array.from({ length: kept - 1 }, (_, i) => ts[i + 1] - ts[i]).sort();
  const median = dts[dts.length >> 1];
  if (!(median > 0)) throw bad("Timestamps are not increasing.");
  const regular = dts[0] > median * 0.99 && dts[dts.length - 1] < median * 1.01;

  const ids = valueCols.map((c) => header[c].toLowerCase());
  const base = path.basename(filename).replace(/\.[^.]+$/, "").replaceAll("_", " ");
  return new Dataset({
    title: base,
    tz: "UTC",
    t0: ts[0],
    sampleRate: 1 / median,
    measures: ids,
    data: Object.fromEntries(ids.map((id, i) => [id, data[i]])),
    ts: regular ? null : ts,
    source: "upload",
    meta: { filename, label: filename },
  });
}

async function loadMedia(file, filename) {
  const info = await probe(file);
  if (!info.audio.length) throw bad("The file contains no data stream.");
  const stream = info.audio[0];
  const channels = deinterleave(await decodeAudio(file, stream.index), stream.channels);
  const ids = stream.measures ?? channels.map((_, i) => `ch${i + 1}`);
  const ds = new Dataset({
    title: stream.title ?? path.basename(filename).replace(/\.[^.]+$/, ""),
    tz: "UTC",
    t0: stream.timestamp ?? 0,
    sampleRate: stream.sampleRate,
    measures: ids,
    data: Object.fromEntries(ids.map((id, i) => [id, channels[i]])),
    source: "upload",
    meta: { filename, label: filename },
  });
  const warnings = [];
  if (info.audio.length > 1) warnings.push("File has more than one stream, only the first one is shown.");
  if (!stream.timestamp) warnings.push("No timestamp found in file, showing seconds since start.");
  const subtitles = info.subs.length ? await extractSubtitles(file, info.subs[0].index) : null;
  return { dataset: ds, warnings, embeddedLabels: subtitles ? { format: "srt", text: subtitles } : null };
}

/** Parse an uploaded file into a Dataset. */
export async function loadUpload(file, originalName) {
  const ext = path.extname(originalName).toLowerCase();
  if ([".csv", ".tsv", ".txt"].includes(ext)) {
    return { dataset: parseCsv(await fs.readFile(file, "utf8"), originalName), warnings: [], embeddedLabels: null };
  }
  if ([".mkv", ".mka", ".wv", ".wav", ".flac"].includes(ext)) return loadMedia(file, originalName);
  throw bad("Unsupported file type. Please upload a .csv or .mkv file.");
}
