export interface Measure { id: string; name: string; unit: string; axis: string; color: string; kind: 'power' | 'wave' }

export interface DatasetInfo {
  id: string; title: string; info: string; tz: string; source: 'fired' | 'upload'
  start: number; end: number; sampleRate: number; samples: number; irregular: boolean
  measures: Measure[]; label: string
  meter?: string; day?: string; defaultMeasures?: string[]; highFreq?: boolean
}

export interface LoadResult {
  dataset: DatasetInfo; warnings: string[]
  embeddedLabels: { format: 'srt'; text: string } | null
}

export interface Meter { id: string; smartmeter: boolean; phase: number; appliances: string[]; details: string[]; label: string }

export interface SeriesData {
  start: number; stop: number; raw: boolean; step: number; t: number[]
  series: Record<string, { avg: (number | null)[]; min?: (number | null)[]; max?: (number | null)[] }>
  measures?: Measure[]
}

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

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText
    try { message = (await res.json()).error ?? message } catch { /* keep status text */ }
    throw new Error(message)
  }
  return res.json()
}

const get = <T>(path: string, signal?: AbortSignal) => fetch(BASE + path, { signal }).then((r) => json<T>(r))
const post = <T>(path: string, body: unknown) =>
  fetch(BASE + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<T>(r))

export const api = {
  meters: () => get<Meter[]>('/api/fired/meters'),
  days: (meter: string) => get<{ days: string[] }>(`/api/fired/meters/${meter}/days`).then((r) => r.days),
  loadFired: (meter: string, day: string) => post<LoadResult>('/api/datasets/fired', { meter, day }),
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return fetch(BASE + '/api/datasets/upload', { method: 'POST', body: form }).then((r) => json<LoadResult>(r))
  },
  data: (id: string, start: number, stop: number, maxPoints: number, measures: string[], signal?: AbortSignal) =>
    get<SeriesData>(`/api/datasets/${id}/data?start=${start}&stop=${stop}&maxPoints=${maxPoints}&measures=${measures.join(',')}`, signal),
  waveform: (id: string, start: number, stop: number, maxPoints: number, signal?: AbortSignal) =>
    get<SeriesData>(`/api/datasets/${id}/waveform?start=${start}&stop=${stop}&maxPoints=${maxPoints}`, signal),
  autolabel: (id: string, params: AutoLabelParams) => post<AutoLabelResult>(`/api/datasets/${id}/autolabel`, params),
}
