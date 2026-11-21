import { decodeChannels } from './engine/binary'
import { Dataset } from './engine/dataset'
import type { Measure } from './engine/measures'

export type { Measure } from './engine/measures'
export type { SeriesData } from './engine/dataset'

export interface DatasetInfo {
  id: string; title: string; info: string; tz: string; source: string
  start: number; end: number; sampleRate: number; samples: number; irregular: boolean
  measures: Measure[]; label: string
  dataset?: string; meter?: string; day?: string; defaultMeasures?: string[]; highFreq?: boolean
}

export interface LoadResult {
  dataset: Dataset; warnings: string[]
  embeddedLabels: { format: 'srt'; text: string } | null
}

export interface DatasetSource {
  id: string; name: string; description: string; url: string; paperUrl: string; tz: string
  waveforms: boolean; available: boolean; reason?: string
}

export interface Meter { id: string; label: string; group?: string; details: string[]; aggregate: boolean; short: string; highFreq: boolean }

export interface AutoLabelParams {
  measure: string; rate: number; thres: number; linearCoeff: number
  pre: number; post: number; minDist: number; start?: number; stop?: number
}

export interface AutoLabelResult {
  labels: { start: number; text: string; delta: number }[]
  states: { id: number; mean: number; segments: number; seconds: number }[]
  rate: number; ms: number; measure: string; warning: string | null
}

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

async function ok(res: Response) {
  if (!res.ok) {
    let message = res.statusText
    try { message = (await res.json()).error ?? message } catch { /* keep status text */ }
    throw new Error(message)
  }
  return res
}

const get = <T>(path: string) => fetch(BASE + path).then(ok).then((r) => r.json() as Promise<T>)

/** Read a response body while reporting download progress (0..1, or null if the size is unknown). */
async function download(res: Response, onProgress?: (p: number | null) => void): Promise<ArrayBuffer> {
  const total = Number(res.headers.get('content-length')) || 0
  if (!onProgress || !res.body) return res.arrayBuffer()
  const buf = new Uint8Array(total || 0)
  const chunks: Uint8Array[] = []
  let got = 0
  const reader = res.body.getReader()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (total && got + value.length <= total) buf.set(value, got)
    else chunks.push(value)
    got += value.length
    onProgress(total ? got / total : null)
  }
  if (total && got === total) return buf.buffer
  const out = new Uint8Array(got)
  let pos = 0
  for (const c of total ? [buf.subarray(0, Math.min(got, total)), ...chunks] : chunks) { out.set(c, pos); pos += c.length }
  return out.buffer
}

function toDataset(buf: ArrayBuffer, source: string) {
  const { header, data } = decodeChannels(buf)
  const dataset = new Dataset({ ...header, data, source })
  return { dataset, warnings: header.warnings ?? [], embeddedLabels: header.embeddedLabels ?? null }
}

export const api = {
  datasets: () => get<DatasetSource[]>('/api/datasets'),
  meters: (ds: string) => get<Meter[]>(`/api/datasets/${ds}/meters`),
  days: (ds: string, meter: string) => get<{ days: string[] }>(`/api/datasets/${ds}/meters/${encodeURIComponent(meter)}/days`).then((r) => r.days),

  async loadDay(ds: string, meter: string, day: string, onProgress?: (p: number | null) => void): Promise<LoadResult> {
    const res = await fetch(`${BASE}/api/datasets/${ds}/meters/${encodeURIComponent(meter)}/days/${day}`).then(ok)
    return toDataset(await download(res, onProgress), ds)
  },

  async decode(file: File, onProgress?: (p: number | null) => void): Promise<LoadResult> {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(BASE + '/api/decode', { method: 'POST', body: form }).then(ok)
    return toDataset(await download(res, onProgress), 'upload')
  },

  async waveform(ds: string, meter: string, start: number, stop: number, signal?: AbortSignal): Promise<Dataset> {
    const res = await fetch(`${BASE}/api/datasets/${ds}/meters/${encodeURIComponent(meter)}/waveform?start=${start}&stop=${stop}`, { signal }).then(ok)
    return toDataset(await res.arrayBuffer(), ds).dataset
  },
}
