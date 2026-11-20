import { api, type AutoLabelParams, type AutoLabelResult, type DatasetInfo, type LoadResult, type Measure, type Meter, type SeriesData } from './api'
import { fromText, newId, type Label } from './labels'

export interface Toast { id: number; kind: 'info' | 'error' | 'success'; text: string }

const PREFERRED = ['s', 's_l1', 'p', 'p_l1']
const WAVE_MAX_SECONDS = 30
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

class AppState {
  meters = $state<Meter[]>([])
  dataset = $state<DatasetInfo | null>(null)
  busy = $state<string | null>(null)
  toasts = $state<Toast[]>([])

  labels = $state<Label[]>([])
  selectedId = $state<string | null>(null)
  editingId = $state<string | null>(null)
  focusListId = $state<string | null>(null)
  addMode = $state(false)
  snap = $state(true)
  defaultText = $state('')

  enabled = $state<string[]>([])
  view = $state<[number, number]>([0, 1])
  series = $state.raw<SeriesData | null>(null)
  fetching = $state(false)
  waveform = $state(false)
  plotWidth = 1000
  cursor = $state<{ t: number; values: Record<string, number | null> } | null>(null)

  auto = $state<AutoLabelParams & { scope: 'all' | 'view'; replace: boolean }>({
    measure: '', rate: 1, thres: 10, linearCoeff: 0.005, pre: 1, post: 1, minDist: 1, scope: 'all', replace: true,
  })
  autoResult = $state<AutoLabelResult | null>(null)
  autoRunning = $state(false)

  theme = $state<'dark' | 'light'>(
    (localStorage.getItem('annoticity:theme') as 'dark' | 'light' | null) ??
      (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'),
  )

  #undo: string[] = []
  #redo: string[] = []
  #abort?: AbortController
  #timer?: ReturnType<typeof setTimeout>
  #toastId = 0

  constructor() {
    try {
      const saved = localStorage.getItem('annoticity:v2:auto')
      if (saved) Object.assign(this.auto, JSON.parse(saved))
    } catch { /* ignore broken settings */ }
  }

  setTheme(t: 'dark' | 'light') {
    this.theme = t
    localStorage.setItem('annoticity:theme', t)
  }

  notify(text: string, kind: Toast['kind'] = 'info') {
    const id = ++this.#toastId
    this.toasts.push({ id, kind, text })
    setTimeout(() => (this.toasts = this.toasts.filter((t) => t.id !== id)), kind === 'error' ? 7000 : 3500)
  }

  get measureInfo(): Measure[] {
    return this.series?.measures ?? this.dataset?.measures ?? []
  }

  get span() {
    return this.view[1] - this.view[0]
  }

  get canWaveform() {
    return !!this.dataset?.highFreq && this.span <= WAVE_MAX_SECONDS
  }

  get showingWaveform() {
    return this.waveform && this.canWaveform
  }

  get sortedLabels() {
    return [...this.labels].sort((a, b) => a.start - b.start)
  }

  // ---- loading -------------------------------------------------------------

  async loadMeters() {
    try { this.meters = await api.meters() } catch (e) { this.notify(`Could not reach the FIRED index: ${(e as Error).message}`, 'error') }
  }

  async loadFired(meter: string, day: string) {
    await this.#load(`Loading ${meter} · ${day} (first load downloads the file)`, () => api.loadFired(meter, day))
  }

  async loadFile(file: File) {
    await this.#load(`Uploading ${file.name}`, () => api.upload(file))
  }

  async #load(message: string, fn: () => Promise<LoadResult>) {
    this.busy = message
    try {
      const res = await fn()
      this.#adopt(res)
    } catch (e) {
      this.notify((e as Error).message, 'error')
    } finally {
      this.busy = null
    }
  }

  #adopt({ dataset, warnings, embeddedLabels }: LoadResult) {
    this.dataset = dataset
    this.#abort?.abort()
    this.series = null
    this.autoResult = null
    this.#undo = []
    this.#redo = []
    this.selectedId = this.editingId = null
    this.addMode = false
    this.waveform = false
    const preferred = dataset.defaultMeasures ?? [PREFERRED.find((p) => dataset.measures.some((m) => m.id === p)) ?? dataset.measures[0].id]
    this.enabled = preferred
    this.auto.measure = preferred[0]
    this.auto.rate = Math.min(this.auto.rate, dataset.sampleRate)
    this.view = [dataset.start, dataset.end]
    this.labels = this.#restore() ?? []
    if (!this.labels.length && embeddedLabels) {
      this.labels = fromText(embeddedLabels.text, 'srt', dataset.start).labels
      if (this.labels.length) this.notify(`Loaded ${this.labels.length} labels embedded in the file`, 'success')
    } else if (this.labels.length) this.notify(`Restored ${this.labels.length} labels from your last session`)
    for (const w of warnings) this.notify(w)
    this.refresh()
  }

  // ---- view & data ---------------------------------------------------------

  setView(min: number, max: number, immediate = false) {
    const ds = this.dataset
    if (!ds) return
    const full = ds.end - ds.start
    const minSpan = ds.highFreq ? 0.01 : Math.max(0.02, 3 / ds.sampleRate)
    let span = clamp(max - min, minSpan, full)
    let lo = min
    if (max - min !== span) lo = (min + max) / 2 - span / 2
    lo = clamp(lo, ds.start, ds.end - span)
    this.view = [lo, lo + span]
    clearTimeout(this.#timer)
    this.#timer = setTimeout(() => this.refresh(), immediate ? 0 : 140)
  }

  resetView() {
    if (this.dataset) this.setView(this.dataset.start, this.dataset.end, true)
  }

  toggleMeasure(id: string) {
    this.enabled = this.enabled.includes(id) ? this.enabled.filter((m) => m !== id) : [...this.enabled, id]
    if (!this.enabled.length) this.enabled = [id]
    this.refresh()
  }

  setWaveform(on: boolean) {
    this.waveform = on
    this.refresh()
  }

  async refresh() {
    const ds = this.dataset
    if (!ds) return
    this.#abort?.abort()
    const ctl = (this.#abort = new AbortController())
    this.fetching = true
    const [start, stop] = this.view
    const points = Math.round(clamp(this.plotWidth * 1.5, 400, 4000))
    try {
      const data = this.showingWaveform
        ? await api.waveform(ds.id, start, stop, points, ctl.signal)
        : await api.data(ds.id, start, stop, points, this.enabled, ctl.signal)
      if (ctl.signal.aborted) return
      this.series = data
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      if (this.showingWaveform) {
        this.waveform = false
        this.notify((e as Error).message, 'error')
        this.refresh()
        return
      }
      this.notify((e as Error).message, 'error')
    } finally {
      if (this.#abort === ctl) this.fetching = false
    }
  }

  // ---- labels --------------------------------------------------------------

  get #key() {
    const d = this.dataset
    return d ? `annoticity:v2:labels:${d.source}:${d.meter ?? d.label}:${d.day ?? d.start}:${d.samples}` : ''
  }

  #restore(): Label[] | null {
    try { return JSON.parse(localStorage.getItem(this.#key) ?? 'null') } catch { return null }
  }

  persist() {
    if (!this.dataset) return
    try {
      if (this.labels.length) localStorage.setItem(this.#key, JSON.stringify($state.snapshot(this.labels)))
      else localStorage.removeItem(this.#key)
    } catch { /* storage full or disabled */ }
  }

  /** Remember the current labels so the next change can be undone. */
  checkpoint() {
    this.#undo.push(JSON.stringify($state.snapshot(this.labels)))
    if (this.#undo.length > 100) this.#undo.shift()
    this.#redo = []
  }

  get canUndo() { return this.#undo.length > 0 }
  get canRedo() { return this.#redo.length > 0 }

  undo() {
    const prev = this.#undo.pop()
    if (prev === undefined) return
    this.#redo.push(JSON.stringify($state.snapshot(this.labels)))
    this.labels = JSON.parse(prev)
    this.persist()
  }

  redo() {
    const next = this.#redo.pop()
    if (next === undefined) return
    this.#undo.push(JSON.stringify($state.snapshot(this.labels)))
    this.labels = JSON.parse(next)
    this.persist()
  }

  /** Time of the steepest slope near t so clicks land exactly on an edge. */
  snapTime(t: number, tolerancePx = 10): number {
    const s = this.series
    if (!s || s.t.length < 3) return t
    const id = this.enabled.find((m) => s.series[m]) ?? Object.keys(s.series)[0]
    const avg = s.series[id]?.avg
    if (!avg) return t
    const tol = (tolerancePx / this.plotWidth) * this.span
    let best = -1, bestDiff = 0
    for (let i = 1; i < s.t.length - 1; i++) {
      if (s.t[i] < t - tol) continue
      if (s.t[i] > t + tol) break
      const a = avg[i - 1], b = avg[i + 1]
      if (a == null || b == null) continue
      const d = Math.abs(b - a)
      if (d > bestDiff) { bestDiff = d; best = i }
    }
    return best >= 0 && bestDiff > 0 ? s.t[best] : t
  }

  addLabel(t: number, text = this.defaultText) {
    this.checkpoint()
    const label: Label = { id: newId(), start: this.snap ? this.snapTime(t) : t, text }
    this.labels.push(label)
    this.selectedId = label.id
    this.focusListId = label.id
    this.persist()
  }

  removeLabel(id: string) {
    this.checkpoint()
    this.labels = this.labels.filter((l) => l.id !== id)
    if (this.selectedId === id) this.selectedId = null
    this.persist()
  }

  renameLabel(id: string, text: string) {
    const l = this.labels.find((x) => x.id === id)
    if (!l || l.text === text) return
    this.checkpoint()
    l.text = text
    l.auto = false
    if (text) this.defaultText = text
    this.persist()
  }

  clearLabels(onlyAuto = false) {
    this.checkpoint()
    this.labels = onlyAuto ? this.labels.filter((l) => !l.auto) : []
    this.selectedId = null
    this.persist()
  }

  addImported(labels: Label[]) {
    this.checkpoint()
    this.labels.push(...labels)
    this.persist()
  }

  centerOn(id: string) {
    const l = this.labels.find((x) => x.id === id)
    if (!l) return
    this.selectedId = id
    const span = this.span
    const mid = l.end ? (l.start + l.end) / 2 : l.start
    this.setView(mid - span / 2, mid + span / 2, true)
  }

  step(direction: 1 | -1) {
    const sorted = this.sortedLabels
    const cur = this.labels.find((l) => l.id === this.selectedId)
    const ref = cur?.start ?? (this.view[0] + this.view[1]) / 2
    const next = direction > 0 ? sorted.find((l) => l.start > ref + 1e-6) : [...sorted].reverse().find((l) => l.start < ref - 1e-6)
    if (next) this.centerOn(next.id)
  }

  // ---- auto labeling -------------------------------------------------------

  async runAutoLabel() {
    const ds = this.dataset
    if (!ds || this.autoRunning) return
    this.autoRunning = true
    localStorage.setItem('annoticity:v2:auto', JSON.stringify(this.auto))
    const { scope, replace, ...params } = $state.snapshot(this.auto)
    if (scope === 'view') { params.start = this.view[0]; params.stop = this.view[1] }
    try {
      const res = await api.autolabel(ds.id, params)
      this.autoResult = res
      this.checkpoint()
      const inScope = (t: number) => scope === 'all' || (t >= this.view[0] && t <= this.view[1])
      if (replace) this.labels = this.labels.filter((l) => !(l.auto && inScope(l.start)))
      this.labels.push(...res.labels.map((l) => ({ id: newId(), start: l.start, text: l.text, auto: true })))
      this.persist()
      if (res.warning) this.notify(res.warning)
      else this.notify(`Found ${res.labels.length} events in ${res.ms} ms`, 'success')
    } catch (e) {
      this.notify((e as Error).message, 'error')
    } finally {
      this.autoRunning = false
    }
  }
}

export const app = new AppState()
