import { tzOffset } from "../tz.js";

/** Order measures so power comes first and phases are grouped (p_l1, q_l1, ..., p_l2, ...). */
export function sortMeasures(ids) {
  const order = ["p", "q", "s", "i_rms", "v_rms"];
  const split = (id) => /^(.*?)(?:_l(\d))?$/.exec(id);
  const rank = (id) => { const r = order.indexOf(split(id)[1]); return r < 0 ? order.length : r; };
  return [...ids].sort((a, b) => (split(a)[2] ?? "").localeCompare(split(b)[2] ?? "") || rank(a) - rank(b));
}

/** Measures shown on first load: total active power, else the per-phase powers, else the first one. */
export function defaultMeasures(measures) {
  for (const base of ["p", "s"]) {
    if (measures.includes(base)) return [base];
    const legs = measures.filter((m) => new RegExp(`^${base}_l\\d$`).test(m));
    if (legs.length) return legs;
  }
  return measures.slice(0, 1);
}

/** "YYYY-MM-DD" of an epoch second in a time zone (offsets are cached per hour). */
export function dayFormatter(tz) {
  const offsets = new Map();
  return (ts) => {
    const hour = Math.floor(ts / 3600);
    let off = offsets.get(hour);
    if (off === undefined) offsets.set(hour, (off = tzOffset(hour * 3600, tz)));
    return new Date((ts + off) * 1000).toISOString().slice(0, 10);
  };
}

export function* dayRange(first, last) {
  for (let t = Date.parse(first); t <= Date.parse(last); t += 86400e3) yield new Date(t).toISOString().slice(0, 10);
}

export const isDay = (day) => /^\d{4}-\d{2}-\d{2}$/.test(day);

/**
 * Put irregular readings onto a regular grid of `period` seconds. Bins are averaged, empty bins
 * repeat the last reading while it is younger than `maxGap` and are NaN (a gap) afterwards.
 */
export function toGrid(ts, columns, period, maxGap = Math.max(6 * period, 60)) {
  if (!ts.length) return { t0: 0, channels: columns.map(() => new Float32Array(0)) };
  const t0 = Math.floor(ts[0] / period) * period;
  const n = Math.floor((ts[ts.length - 1] - t0) / period) + 1;
  const counts = new Uint32Array(n);
  const sums = columns.map(() => new Float64Array(n));
  for (let k = 0; k < ts.length; k++) {
    const b = Math.floor((ts[k] - t0) / period);
    if (b < 0 || b >= n) continue;
    counts[b]++;
    for (let c = 0; c < columns.length; c++) sums[c][b] += columns[c][k];
  }
  const channels = columns.map(() => new Float32Array(n));
  let lastBin = -Infinity;
  for (let b = 0; b < n; b++) {
    if (counts[b]) lastBin = b;
    const hold = (b - lastBin) * period <= maxGap;
    for (let c = 0; c < columns.length; c++) {
      channels[c][b] = counts[b] ? sums[c][b] / counts[b] : hold ? channels[c][b - 1] : NaN;
    }
  }
  return { t0, channels };
}

/** Typical spacing of timestamps, rounded to whole seconds (at least 1 s). */
export function typicalPeriod(ts) {
  const diffs = [];
  const step = Math.max(1, Math.floor(ts.length / 2000));
  for (let k = step; k < ts.length; k += step) diffs.push(ts[k] - ts[k - 1]);
  diffs.sort((a, b) => a - b);
  return Math.max(1, Math.round(diffs[Math.floor(diffs.length / 2)] ?? 1));
}

export const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
