import { describeMeasure, type Measure } from './measures.ts'

export type Series = { avg: (number | null)[]; min?: (number | null)[]; max?: (number | null)[] }

export interface SeriesData {
  start: number; stop: number; raw: boolean; step: number; t: number[]
  series: Record<string, Series>
  measures?: Measure[]
}

export interface DatasetInit {
  title: string; info?: string; tz?: string; t0?: number; sampleRate: number
  measures: string[]; data: Record<string, Float32Array>; ts?: Float64Array | null
  source: 'fired' | 'upload'; meta?: Record<string, unknown>
}

/** Samples summarised per block; queries spanning many blocks read the summaries instead of raw samples. */
const BLOCK = 256

interface Blocks { min: Float32Array; max: Float32Array; sum: Float64Array; count: Uint32Array }

let nextId = 0

/**
 * In-memory time series. Regular data is described by `t0` + `sampleRate`,
 * irregular data carries an explicit `ts` (epoch seconds) array.
 */
export class Dataset {
  id: string
  title: string
  info: string
  tz: string
  t0: number
  sampleRate: number
  measureIds: string[]
  data: Record<string, Float32Array>
  ts: Float64Array | null
  source: 'fired' | 'upload'
  meta: Record<string, unknown>
  #blocks = new Map<string, Blocks>()

  constructor(init: DatasetInit) {
    this.id = `ds${++nextId}`
    this.title = init.title
    this.info = init.info ?? ''
    this.tz = init.tz ?? 'UTC'
    this.t0 = init.t0 ?? 0
    this.sampleRate = init.sampleRate
    this.measureIds = init.measures
    this.data = init.data
    this.ts = init.ts ?? null
    this.source = init.source
    this.meta = init.meta ?? {}
  }

  get length() {
    return this.data[this.measureIds[0]].length
  }

  get start() {
    return this.ts ? this.ts[0] : this.t0
  }

  get end() {
    return this.ts ? this.ts[this.length - 1] : this.t0 + this.length / this.sampleRate
  }

  timeAt(i: number) {
    return this.ts ? this.ts[i] : this.t0 + i / this.sampleRate
  }

  /** First index whose time is >= t. */
  lowerBound(t: number) {
    if (!this.ts) return Math.min(this.length, Math.max(0, Math.ceil((t - this.t0) * this.sampleRate - 1e-9)))
    let lo = 0, hi = this.length
    while (lo < hi) {
      const mid = (lo + hi) >>> 1
      if (this.ts[mid] < t) lo = mid + 1
      else hi = mid
    }
    return lo
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
      label: String(this.meta.label ?? this.title),
      ...this.meta,
    }
  }

  #summary(id: string): Blocks {
    let b = this.#blocks.get(id)
    if (b) return b
    const src = this.data[id]
    const n = Math.ceil(src.length / BLOCK)
    b = { min: new Float32Array(n), max: new Float32Array(n), sum: new Float64Array(n), count: new Uint32Array(n) }
    for (let k = 0; k < n; k++) {
      let mn = Infinity, mx = -Infinity, sum = 0, cnt = 0
      const end = Math.min(src.length, (k + 1) * BLOCK)
      for (let i = k * BLOCK; i < end; i++) {
        const v = src[i]
        if (v !== v) continue
        sum += v; cnt++
        if (v < mn) mn = v
        if (v > mx) mx = v
      }
      b.min[k] = mn; b.max[k] = mx; b.sum[k] = sum; b.count[k] = cnt
    }
    this.#blocks.set(id, b)
    return b
  }

  /**
   * Return at most `maxPoints` points of [start, stop). Over-long ranges are bucketed and
   * every bucket reports mean, min and max so short spikes are never lost.
   */
  query(start: number, stop: number, maxPoints = 1500, measureIds = this.measureIds): SeriesData {
    const i0 = this.lowerBound(start)
    const i1 = Math.max(i0, this.lowerBound(stop))
    const n = i1 - i0
    const buckets = Math.max(1, Math.min(maxPoints, n))
    const raw = n <= maxPoints
    const edge = (b: number) => (raw ? i0 + b : i0 + Math.floor((b * n) / buckets))
    const t = new Array<number>(buckets)
    for (let b = 0; b < buckets; b++) {
      const a = edge(b), e = raw ? a + 1 : edge(b + 1)
      t[b] = (this.timeAt(a) + this.timeAt(Math.max(a, e - 1))) / 2
    }
    const series: Record<string, Series> = {}
    for (const id of measureIds) {
      const src = this.data[id]
      if (!src) continue
      const avg = new Array<number | null>(buckets)
      if (raw) {
        for (let b = 0; b < buckets; b++) { const v = src[i0 + b]; avg[b] = v === v ? v : null }
        series[id] = { avg }
        continue
      }
      const lo = new Array<number | null>(buckets), hi = new Array<number | null>(buckets)
      const useBlocks = n / buckets >= 4 * BLOCK
      const blk = useBlocks ? this.#summary(id) : null
      for (let b = 0; b < buckets; b++) {
        const a = edge(b), e = edge(b + 1)
        let sum = 0, mn = Infinity, mx = -Infinity, cnt = 0
        const scan = (from: number, to: number) => {
          for (let k = from; k < to; k++) {
            const v = src[k]
            if (v !== v) continue
            sum += v; cnt++
            if (v < mn) mn = v
            if (v > mx) mx = v
          }
        }
        if (blk) {
          const k0 = Math.ceil(a / BLOCK), k1 = Math.floor(e / BLOCK)
          scan(a, k0 * BLOCK)
          for (let k = k0; k < k1; k++) {
            if (!blk.count[k]) continue
            sum += blk.sum[k]; cnt += blk.count[k]
            if (blk.min[k] < mn) mn = blk.min[k]
            if (blk.max[k] > mx) mx = blk.max[k]
          }
          scan(k1 * BLOCK, e)
        } else scan(a, e)
        if (cnt === 0) { avg[b] = lo[b] = hi[b] = null; continue }
        avg[b] = sum / cnt; lo[b] = mn; hi[b] = mx
      }
      series[id] = { avg, min: lo, max: hi }
    }
    return { start, stop, raw, step: n > 0 ? (this.timeAt(i1 - 1) - this.timeAt(i0)) / Math.max(1, buckets - 1) : 0, t, series }
  }

  /**
   * Resample one measure onto a regular grid at `rate` Hz by bin-averaging.
   * Empty bins (gaps in irregular data) hold the previous value.
   */
  regularSeries(measureId: string, rate: number, start = this.start, stop = this.end) {
    const src = this.data[measureId]
    const i0 = this.lowerBound(start)
    const i1 = Math.max(i0, this.lowerBound(stop))
    if (!this.ts && rate >= this.sampleRate) {
      return { values: Float64Array.from(src.subarray(i0, i1)), rate: this.sampleRate, t0: this.timeAt(i0) }
    }
    const tStart = this.timeAt(i0)
    const bins = Math.max(1, Math.floor((stop - tStart) * rate))
    const sums = new Float64Array(bins), counts = new Uint32Array(bins)
    for (let k = i0; k < i1; k++) {
      const v = src[k]
      if (v !== v) continue
      const b = Math.floor((this.timeAt(k) - tStart) * rate)
      if (b >= 0 && b < bins) { sums[b] += v; counts[b]++ }
    }
    const values = new Float64Array(bins)
    let last = 0, seen = false
    for (let b = 0; b < bins; b++) {
      if (counts[b]) { last = sums[b] / counts[b]; seen = true; values[b] = last }
      else values[b] = seen ? last : NaN
    }
    const first = values.findIndex((v) => !Number.isNaN(v))
    if (first > 0) values.fill(values[first], 0, first)
    return { values, rate, t0: tStart }
  }
}
