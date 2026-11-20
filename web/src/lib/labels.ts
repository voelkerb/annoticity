export interface Label { id: string; start: number; end?: number; text: string; auto?: boolean }

let counter = 0
export const newId = () => `l${Date.now().toString(36)}${(counter++).toString(36)}`

const PALETTE = ['#818cf8', '#34d399', '#fbbf24', '#f472b6', '#38bdf8', '#fb923c', '#a3e635', '#c084fc']

export function labelColor(text: string): string {
  if (!text) return '#94a3b8'
  let h = 0
  for (const c of text) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

export function formatTime(epoch: number, tz: string, ms = true): string {
  const d = new Date(epoch * 1000)
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(d)
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]))
  const frac = ms ? '.' + String(Math.round((epoch % 1) * 1000) % 1000).padStart(3, '0') : ''
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}${frac}`
}

export function formatClock(epoch: number, tz: string, ms = false): string {
  return formatTime(epoch, tz, ms).slice(11)
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0')

function srtTime(sec: number, comma: boolean) {
  const t = Math.max(0, sec)
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60)
  const ms = Math.round((t - Math.floor(t)) * 1000)
  return comma ? `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}` : `${h}:${pad(m)}:${pad(s)}.${pad(Math.floor(ms / 10))}`
}

function spans(labels: Label[], origin: number) {
  const sorted = [...labels].sort((a, b) => a.start - b.start)
  return sorted.map((l, i) => {
    const next = sorted[i + 1]?.start
    const end = l.end ?? (next !== undefined && next > l.start ? Math.min(next, l.start + 5) : l.start + 1)
    return { text: l.text, start: l.start - origin, end: end - origin }
  })
}

export type LabelFormat = 'csv' | 'srt' | 'ass' | 'json'

export function exportLabels(labels: Label[], format: LabelFormat, origin: number): string {
  const sorted = [...labels].sort((a, b) => a.start - b.start)
  if (format === 'json') return JSON.stringify(sorted.map(({ id, auto, ...l }) => l), null, 2)
  if (format === 'csv') {
    const ranges = sorted.some((l) => l.end !== undefined)
    const q = (s: string) => (/[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s)
    const head = ranges ? 'startTs,stopTs,label' : 'startTs,label'
    return [head, ...sorted.map((l) => (ranges ? `${l.start.toFixed(3)},${(l.end ?? l.start).toFixed(3)},${q(l.text)}` : `${l.start.toFixed(3)},${q(l.text)}`))].join('\n') + '\n'
  }
  const s = spans(sorted, origin)
  if (format === 'srt') {
    return s.map((l, i) => `${i + 1}\n${srtTime(l.start, true)} --> ${srtTime(l.end, true)}\n${l.text}\n`).join('\n')
  }
  return [
    '[Script Info]', 'ScriptType: v4.00+', '', '[V4+ Styles]',
    'Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment',
    'Style: Default,Arial,20,&H00FFFFFF,0,2', '', '[Events]',
    'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ...s.map((l) => `Dialogue: 0,${srtTime(l.start, false)},${srtTime(l.end, false)},Default,,0,0,0,,${l.text}`),
  ].join('\n') + '\n'
}

function parseClock(s: string): number {
  const m = /(\d+):(\d{2}):(\d{2})[,.](\d+)/.exec(s.trim())
  if (!m) return NaN
  return +m[1] * 3600 + +m[2] * 60 + +m[3] + Number('0.' + m[4])
}

function splitRow(line: string, delim: string): string[] {
  const out: string[] = []
  let cur = '', quoted = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++ }
      else if (c === '"') quoted = false
      else cur += c
    } else if (c === '"') quoted = true
    else if (c === delim) { out.push(cur); cur = '' }
    else cur += c
  }
  out.push(cur)
  return out.map((x) => x.trim())
}

/** Parse csv/srt/ass/json label files. Relative times are shifted by `origin`. */
export function importLabels(text: string, filename: string, origin: number): { labels: Label[]; note?: string } {
  const ext = filename.split('.').pop()?.toLowerCase() ?? ''
  return fromText(text, ext, origin)
}

export function fromText(text: string, ext: string, origin: number): { labels: Label[]; note?: string } {
  if (ext === 'json') {
    const arr = JSON.parse(text) as { start: number; end?: number; text?: string }[]
    return { labels: arr.map((l) => ({ id: newId(), start: l.start, end: l.end, text: l.text ?? '' })) }
  }
  if (ext === 'srt') {
    const labels: Label[] = []
    for (const block of text.replace(/\r/g, '').split(/\n{2,}/)) {
      const lines = block.split('\n').filter(Boolean)
      const at = lines.findIndex((l) => l.includes('-->'))
      if (at < 0) continue
      const [a, b] = lines[at].split('-->')
      labels.push({ id: newId(), start: origin + parseClock(a), end: origin + parseClock(b), text: lines.slice(at + 1).join(' ') })
    }
    return { labels }
  }
  if (ext === 'ass') {
    const labels: Label[] = []
    for (const line of text.replace(/\r/g, '').split('\n')) {
      if (!line.startsWith('Dialogue:')) continue
      const f = line.slice(9).split(',')
      labels.push({ id: newId(), start: origin + parseClock(f[1]), end: origin + parseClock(f[2]), text: f.slice(9).join(',').trim() })
    }
    return { labels }
  }
  if (ext === 'csv' || ext === 'txt' || ext === 'tsv') {
    const lines = text.split(/\r?\n/).filter((l) => l.trim())
    if (!lines.length) return { labels: [] }
    const delim = [',', ';', '\t'].map((d) => [d, lines[0].split(d).length] as const).sort((a, b) => b[1] - a[1])[0][0]
    let rows = lines.map((l) => splitRow(l, delim))
    const hasHeader = rows[0].some((c) => c !== '' && !Number.isFinite(Number(c)))
    let startCol = -1, endCol = -1, textCol = -1, note: string | undefined
    if (hasHeader) {
      const h = rows[0].map((c) => c.toLowerCase())
      startCol = h.findIndex((c) => ['startts', 'start', 'timestamp', 'ts', 'time'].includes(c))
      endCol = h.findIndex((c) => ['stopts', 'stop', 'end', 'endts'].includes(c))
      textCol = h.findIndex((c) => ['label', 'text', 'name', 'description'].includes(c))
      rows = rows.slice(1)
    } else {
      const numeric = rows[0].map((c) => Number.isFinite(Number(c)) && c !== '')
      startCol = numeric.indexOf(true)
      textCol = numeric.indexOf(false)
      const second = numeric.indexOf(true, startCol + 1)
      if (second > 0 && rows.every((r) => Number(r[second]) >= Number(r[startCol]))) endCol = second
      note = 'No header found, guessed columns.'
    }
    if (startCol < 0) throw new Error('Could not find a start time column (expected "startTs" or "timestamp").')
    const labels = rows.map((r) => {
      let start = Number(r[startCol]), end = endCol >= 0 ? Number(r[endCol]) : undefined
      if (start < 1e8) { start += origin; if (end !== undefined) end += origin }
      if (start > 1e11) { start /= 1000; if (end !== undefined) end /= 1000 }
      return { id: newId(), start, end: end !== undefined && end > start ? end : undefined, text: textCol >= 0 ? r[textCol] ?? '' : '' }
    }).filter((l) => Number.isFinite(l.start))
    return { labels, note }
  }
  throw new Error('Unsupported label file. Use csv, srt, ass or json.')
}

export function download(name: string, content: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
