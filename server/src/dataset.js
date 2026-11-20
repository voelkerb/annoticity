import { randomUUID } from "node:crypto";
import { describeMeasure } from "./measures.js";

/**
 * Time series container. Regular data is described by `t0` + `sampleRate`,
 * irregular data carries an explicit `ts` (epoch seconds) array.
 */
export class Dataset {
  constructor({ title, info = "", tz = "UTC", t0 = 0, sampleRate, measures, data, ts = null, source, meta = {} }) {
    this.id = randomUUID();
    this.title = title;
    this.info = info;
    this.tz = tz;
    this.t0 = t0;
    this.sampleRate = sampleRate;
    this.measureIds = measures;
    this.data = data;
    this.ts = ts;
    this.source = source;
    this.meta = meta;
  }

  get length() {
    return this.data[this.measureIds[0]].length;
  }

  get start() {
    return this.ts ? this.ts[0] : this.t0;
  }

  get end() {
    return this.ts ? this.ts[this.length - 1] : this.t0 + this.length / this.sampleRate;
  }

  timeAt(i) {
    return this.ts ? this.ts[i] : this.t0 + i / this.sampleRate;
  }

  /** First index whose time is >= t. */
  lowerBound(t) {
    if (!this.ts) return Math.min(this.length, Math.max(0, Math.ceil((t - this.t0) * this.sampleRate - 1e-9)));
    let lo = 0, hi = this.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.ts[mid] < t) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  describe() {
    return {
      id: this.id,
      title: this.title,
      info: this.info,
      tz: this.tz,
      source: this.source,
      start: this.start,
      end: this.end,
      sampleRate: this.sampleRate,
      samples: this.length,
      irregular: !!this.ts,
      measures: this.measureIds.map((id, i) => describeMeasure(id, i)),
      ...this.meta,
    };
  }

  /**
   * Return at most `maxPoints` points of [start, stop). Over-long ranges are bucketed and
   * every bucket reports mean, min and max so short spikes are never lost.
   */
  query(start, stop, maxPoints = 1500, measureIds = this.measureIds) {
    const i0 = this.lowerBound(start);
    const i1 = Math.max(i0, this.lowerBound(stop));
    const n = i1 - i0;
    const buckets = Math.max(1, Math.min(maxPoints, n));
    const raw = n <= maxPoints;
    const t = new Array(buckets);
    const series = {};
    for (const id of measureIds) {
      const src = this.data[id];
      if (!src) continue;
      const avg = new Array(buckets), lo = new Array(buckets), hi = new Array(buckets);
      for (let b = 0; b < buckets; b++) {
        const a = raw ? i0 + b : i0 + Math.floor((b * n) / buckets);
        const e = raw ? a + 1 : i0 + Math.floor(((b + 1) * n) / buckets);
        let sum = 0, mn = Infinity, mx = -Infinity, cnt = 0;
        for (let k = a; k < e; k++) {
          const v = src[k];
          if (Number.isNaN(v)) continue;
          sum += v; cnt++;
          if (v < mn) mn = v;
          if (v > mx) mx = v;
        }
        if (cnt === 0) { avg[b] = lo[b] = hi[b] = null; continue; }
        avg[b] = round(sum / cnt);
        lo[b] = round(mn);
        hi[b] = round(mx);
      }
      series[id] = raw ? { avg } : { avg, min: lo, max: hi };
    }
    for (let b = 0; b < buckets; b++) {
      const a = raw ? i0 + b : i0 + Math.floor((b * n) / buckets);
      const e = raw ? a + 1 : i0 + Math.floor(((b + 1) * n) / buckets);
      t[b] = round((this.timeAt(a) + this.timeAt(Math.max(a, e - 1))) / 2, 4);
    }
    return { start, stop, raw, step: n > 0 ? (this.timeAt(i1 - 1) - this.timeAt(i0)) / Math.max(1, buckets - 1) : 0, t, series };
  }

  /**
   * Resample one measure onto a regular grid at `rate` Hz by bin-averaging.
   * Empty bins (gaps in irregular data) hold the previous value.
   */
  regularSeries(measureId, rate, start = this.start, stop = this.end) {
    const src = this.data[measureId];
    const i0 = this.lowerBound(start);
    const i1 = Math.max(i0, this.lowerBound(stop));
    if (!this.ts && rate >= this.sampleRate) {
      return { values: Float64Array.from(src.subarray(i0, i1)), rate: this.sampleRate, t0: this.timeAt(i0) };
    }
    const tStart = this.timeAt(i0);
    const bins = Math.max(1, Math.floor((stop - tStart) * rate));
    const sums = new Float64Array(bins), counts = new Uint32Array(bins);
    for (let k = i0; k < i1; k++) {
      const v = src[k];
      if (Number.isNaN(v)) continue;
      const b = Math.floor((this.timeAt(k) - tStart) * rate);
      if (b >= 0 && b < bins) { sums[b] += v; counts[b]++; }
    }
    const values = new Float64Array(bins);
    let last = 0, seen = false;
    for (let b = 0; b < bins; b++) {
      if (counts[b]) { last = sums[b] / counts[b]; seen = true; values[b] = last; }
      else values[b] = seen ? last : NaN;
    }
    let first = values.findIndex((v) => !Number.isNaN(v));
    if (first > 0) values.fill(values[first], 0, first);
    return { values, rate, t0: tStart };
  }
}

function round(v, d = 3) {
  const f = 10 ** d;
  return Math.round(v * f) / f;
}

/** Small LRU keyed by id so the server does not grow without bound. */
export class DatasetStore {
  constructor(max = 8) {
    this.max = max;
    this.map = new Map();
  }

  add(ds) {
    this.map.set(ds.id, ds);
    while (this.map.size > this.max) this.map.delete(this.map.keys().next().value);
    return ds;
  }

  get(id) {
    const ds = this.map.get(id);
    if (ds) { this.map.delete(id); this.map.set(id, ds); }
    return ds;
  }
}
