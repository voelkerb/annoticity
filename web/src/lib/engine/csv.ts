import { Dataset } from './dataset.ts'

const TIME_COLUMNS = ['timestamp', 'ts', 'time', 'datetime', 'date', 'datum', 'unix', 'epoch']

function detectDelimiter(line: string) {
  const counts = [',', ';', '\t', ' '].map((d) => [d, line.split(d).length - 1] as const)
  const best = [...counts].sort((a, b) => b[1] - a[1])[0]
  return best[1] > 0 ? best[0] : ','
}

/** Convert a time cell to epoch seconds; handles seconds, ms, µs, ns and common date strings. */
export function parseTime(cell: string) {
  const s = cell.trim()
  if (s === '') return NaN
  const num = Number(s)
  if (Number.isFinite(num)) {
    const a = Math.abs(num)
    if (a >= 1e17) return num / 1e9
    if (a >= 1e14) return num / 1e6
    if (a >= 1e11) return num / 1e3
    return num
  }
  const dmy = /^(\d{1,2})[-.](\d{1,2})[-.](\d{4})(.*)$/.exec(s)
  const iso = dmy ? `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}${dmy[4]}` : s
  const withZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : iso.replace(' ', 'T') + (iso.includes('T') || iso.includes(' ') ? 'Z' : 'T00:00:00Z')
  const ms = Date.parse(withZone)
  return Number.isNaN(ms) ? NaN : ms / 1000
}

export function parseCsv(text: string, filename = 'upload'): Dataset {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '')
  if (lines.length < 3) throw new Error('The file needs a header row and at least two data rows.')
  const delim = detectDelimiter(lines[0])
  const split = (l: string) => l.split(delim).map((c) => c.trim().replace(/^"|"$/g, ''))
  const header = split(lines[0])
  if (header.every((h) => Number.isFinite(Number(h)))) {
    throw new Error('Please add a header row, e.g. "timestamp,p". One column must be named one of: ' + TIME_COLUMNS.join(', ') + '.')
  }
  const timeCol = header.findIndex((h) => TIME_COLUMNS.includes(h.toLowerCase()))
  if (timeCol < 0) throw new Error('Cannot find a time column. Name it one of: ' + TIME_COLUMNS.join(', ') + '.')

  const sample = lines.slice(1, 21).map(split)
  const valueCols = header.map((_, i) => i).filter((i) => i !== timeCol && sample.some((r) => r[i] !== '' && r[i] !== undefined && Number.isFinite(Number(r[i]))))
  if (!valueCols.length) throw new Error('No numeric data columns found.')

  const n = lines.length - 1
  let ts = new Float64Array(n)
  const cols = valueCols.map(() => new Float32Array(n))
  let kept = 0, sorted = true
  for (let li = 1; li < lines.length; li++) {
    const r = split(lines[li])
    const t = parseTime(r[timeCol] ?? '')
    if (Number.isNaN(t)) continue
    if (kept && t < ts[kept - 1]) sorted = false
    ts[kept] = t
    valueCols.forEach((c, k) => (cols[k][kept] = r[c] === '' || r[c] === undefined ? NaN : Number(r[c])))
    kept++
  }
  if (kept < 2) throw new Error('Could not parse the time column.')
  ts = ts.slice(0, kept)
  let data = cols.map((c) => c.slice(0, kept))
  if (!sorted) {
    const order = Uint32Array.from(ts.keys()).sort((a, b) => ts[a] - ts[b])
    ts = Float64Array.from(order, (i) => ts[i])
    data = data.map((c) => Float32Array.from(order, (i) => c[i]))
  }

  const dts = Float64Array.from({ length: kept - 1 }, (_, i) => ts[i + 1] - ts[i]).sort()
  const median = dts[dts.length >> 1]
  if (!(median > 0)) throw new Error('Timestamps are not increasing.')
  const regular = dts[0] > median * 0.99 && dts[dts.length - 1] < median * 1.01

  const ids = valueCols.map((c) => header[c].toLowerCase())
  const base = filename.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, '').replaceAll('_', ' ')
  return new Dataset({
    title: base,
    tz: 'UTC',
    t0: ts[0],
    sampleRate: 1 / median,
    measures: ids,
    data: Object.fromEntries(ids.map((id, i) => [id, data[i]])),
    ts: regular ? null : ts,
    source: 'upload',
    meta: { filename, label: filename },
  })
}
