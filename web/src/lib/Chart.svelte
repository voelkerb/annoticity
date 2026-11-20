<script lang="ts">
  import { untrack } from 'svelte'
  import uPlot from 'uplot'
  import 'uplot/dist/uPlot.min.css'
  import { formatTime, labelColor } from './labels'
  import { app } from './state.svelte'

  let host: HTMLDivElement
  let overlay: HTMLDivElement
  let u: uPlot | undefined
  let tick = $state(0)
  let box = $state<{ x0: number; x1: number } | null>(null)
  let builtKey = ''

  const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const nonNull = (a: (number | null)[]) => a as number[]

  function build() {
    const s = app.series
    const ds = app.dataset
    if (!s || !ds) return
    const info = app.measureInfo
    const ids = Object.keys(s.series)
    const n = ids.length
    const data: uPlot.AlignedData = [s.t, ...ids.map((id) => nonNull(s.series[id].avg))]
    if (!s.raw) for (const id of ids) data.push(nonNull(s.series[id].min!), nonNull(s.series[id].max!))

    const key = [ds.id, ids.join(), s.raw, app.theme, app.showingWaveform].join('|')
    if (u && key === builtKey) {
      u.setData(data, true)
      return
    }
    builtKey = key
    u?.destroy()

    const axisColor = css('--chart-axis'), grid = css('--chart-grid')
    const font = `12px ${css('--font')}`
    const meas = ids.map((id, i) => info.find((m) => m.id === id) ?? { id, name: id, unit: '', axis: 'Value', color: '#a78bfa', kind: 'power' as const, i })
    const scales: Record<string, uPlot.Scale> = { x: { time: true, auto: false, min: app.view[0], max: app.view[1] } }
    const axisKeys = [...new Set(meas.map((m) => m.axis))]
    for (const k of axisKeys) {
      const wave = meas.find((m) => m.axis === k)?.kind === 'wave'
      // Range from the averaged series only, so short spikes in the min/max band don't flatten the plot
      const idx = meas.map((m, i) => (m.axis === k ? i + 1 : -1)).filter((i) => i > 0)
      scales[k] = {
        auto: true,
        range: (self, dMin, dMax) => {
          let lo = Infinity, hi = -Infinity
          const [x0, x1] = [self.scales.x.min ?? -Infinity, self.scales.x.max ?? Infinity]
          const xs = self.data[0]
          for (const i of idx) {
            const ys = self.data[i]
            for (let j = 0; j < xs.length; j++) {
              const y = ys[j]
              if (y == null || xs[j] < x0 || xs[j] > x1) continue
              if (y < lo) lo = y
              if (y > hi) hi = y
            }
          }
          if (!isFinite(lo)) { lo = dMin; hi = dMax }
          if (hi - lo < 1e-9) { hi = lo + 1 }
          const pad = (hi - lo) * (wave ? 0.1 : 0.12)
          return [wave || lo < 0 ? lo - pad : Math.min(0, lo), hi + pad]
        },
      } as uPlot.Scale
    }

    const series: uPlot.Series[] = [{}]
    for (const m of meas) {
      series.push({
        label: m.name, scale: m.axis, stroke: m.color, width: s.raw ? 1.6 : 1.4, spanGaps: false,
        points: { show: s.raw && s.t.length < 150, size: 4 }, paths: s.raw && m.kind === 'power' && s.t.length > 1 ? uPlot.paths.stepped!({ align: 1 }) : undefined,
      })
    }
    if (!s.raw) for (const m of meas) for (let k = 0; k < 2; k++) series.push({ label: `${m.name} ${k ? 'max' : 'min'}`, scale: m.axis, stroke: 'transparent', width: 0, points: { show: false } })
    const bands: uPlot.Band[] = s.raw ? [] : meas.map((m, i) => ({ series: [1 + n + 2 * i + 1, 1 + n + 2 * i] as [number, number], fill: m.color + '30' }))

    const tz = ds.tz
    const opts: uPlot.Options = {
      width: host.clientWidth, height: host.clientHeight,
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), tz),
      legend: { show: false }, padding: [14, 14, 0, 0],
      cursor: { drag: { x: false, y: false, setScale: false }, points: { size: 8 }, y: false },
      select: { show: false, left: 0, top: 0, width: 0, height: 0 },
      scales, series, bands,
      axes: [
        { stroke: axisColor, font, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid, width: 1 }, space: 90 },
        ...axisKeys.map((k, i) => {
          const m = meas.find((x) => x.axis === k)!
          return {
            scale: k, side: (i === 0 ? 3 : 1) as 1 | 3, stroke: axisColor, font, size: 64,
            label: `${k}${m.unit ? ` (${m.unit})` : ''}`, labelFont: font, labelSize: 18,
            grid: { show: i === 0, stroke: grid, width: 1 }, ticks: { stroke: grid, width: 1 },
          }
        }),
      ],
      hooks: {
        setScale: [(_u, k) => { if (k === 'x') tick++ }],
        draw: [(p) => {
          // u.over has its real size only after uPlot's first layout pass
          if (p.over.clientWidth > 0) app.plotWidth = p.over.clientWidth
          tick++
        }],
        setCursor: [(p) => {
          const left = p.cursor.left ?? -1
          if (left < 0) { app.cursor = null; return }
          const idx = p.cursor.idx
          const values: Record<string, number | null> = {}
          ids.forEach((id, i) => (values[id] = idx != null ? ((p.data[i + 1][idx] as number | null) ?? null) : null))
          app.cursor = { t: p.posToVal(left, 'x'), values }
        }],
      },
    }
    u = new uPlot(opts, data, host)
    u.over.appendChild(overlay)
    bind(u.over)
    tick++
  }

  // ---- interaction ------------------------------------------------------------

  const xAt = (e: { clientX: number }) => e.clientX - u!.over.getBoundingClientRect().left
  const tAt = (e: { clientX: number }) => u!.posToVal(xAt(e), 'x')

  function bind(over: HTMLElement) {
    over.addEventListener('wheel', onWheel, { passive: false })
    over.addEventListener('pointerdown', onDown)
    over.addEventListener('dblclick', () => app.resetView())
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault()
    const [min, max] = app.view
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      const d = (e.deltaX / u!.over.clientWidth) * (max - min)
      return app.setView(min + d, max + d)
    }
    const f = Math.exp(Math.max(-60, Math.min(60, e.deltaY)) * 0.0022)
    const t = tAt(e)
    app.setView(t - (t - min) * f, t + (max - t) * f)
  }

  function onDown(e: PointerEvent) {
    if (e.button !== 0 || !u) return
    // Label markers handle their own drag; Svelte delegates their handlers to the root, so this native listener fires first
    if ((e.target as HTMLElement).closest('.line, .chip, .edge')) return
    const over = u.over
    over.setPointerCapture(e.pointerId)
    const startX = xAt(e)
    const [min0, max0] = app.view
    const select = e.shiftKey
    let moved = false
    over.style.cursor = select ? 'col-resize' : 'grabbing'

    const move = (ev: PointerEvent) => {
      const x = xAt(ev)
      if (Math.abs(x - startX) > 3) moved = true
      if (!moved) return
      if (select) box = { x0: Math.min(startX, x), x1: Math.max(startX, x) }
      else {
        const d = ((x - startX) / over.clientWidth) * (max0 - min0)
        app.setView(min0 - d, max0 - d)
      }
    }
    const up = (ev: PointerEvent) => {
      over.removeEventListener('pointermove', move)
      over.removeEventListener('pointerup', up)
      over.removeEventListener('pointercancel', up)
      over.style.cursor = ''
      if (select && box && box.x1 - box.x0 > 6) app.setView(u!.posToVal(box.x0, 'x'), u!.posToVal(box.x1, 'x'), true)
      box = null
      if (!moved && ev.type === 'pointerup') {
        if (app.addMode) {
          const near = app.labelNear(tAt(ev))
          if (near) app.selectedId = near.id
          else app.addLabel(tAt(ev))
        } else app.selectedId = null
      }
    }
    over.addEventListener('pointermove', move)
    over.addEventListener('pointerup', up)
    over.addEventListener('pointercancel', up)
  }

  function dragLabel(e: PointerEvent, id: string, edge: 'start' | 'end' = 'start') {
    e.stopPropagation()
    app.selectedId = id
    const el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    const label = app.labels.find((l) => l.id === id)!
    const origin = label[edge]!
    const startX = e.clientX
    let moved = false
    const move = (ev: PointerEvent) => {
      if (!moved && Math.abs(ev.clientX - startX) < 3) return
      if (!moved) { app.checkpoint(); moved = true }
      const t = tAt(ev)
      label[edge] = app.snap && !ev.altKey ? app.snapTime(t, 10, id) : t
    }
    const up = () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      if (moved) {
        if (label.end !== undefined && label.end < label.start) [label.start, label.end] = [label.end, label.start]
        label.auto = false
        app.persist()
      } else label[edge] = origin
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }

  // ---- reactive wiring -----------------------------------------------------

  $effect(() => {
    app.series; app.theme
    untrack(build)
  })

  $effect(() => {
    const [min, max] = app.view
    if (u && (Math.abs(u.scales.x.min! - min) > 1e-9 || Math.abs(u.scales.x.max! - max) > 1e-9)) u.setScale('x', { min, max })
  })

  $effect(() => {
    const ro = new ResizeObserver(() => {
      if (!u) return
      u.setSize({ width: host.clientWidth, height: host.clientHeight })
    })
    ro.observe(host)
    return () => { ro.disconnect(); u?.destroy(); u = undefined }
  })

  $effect(() => {
    if (u) u.over.style.cursor = app.addMode ? 'crosshair' : ''
  })

  const placed = $derived.by(() => {
    void tick
    if (!u) return []
    const w = u.over.clientWidth
    const rows = [-1e9, -1e9, -1e9]
    return app.sortedLabels
      .map((l) => ({ l, x: u!.valToPos(l.start, 'x'), x2: l.end !== undefined ? u!.valToPos(l.end, 'x') : null }))
      .filter(({ x, x2 }) => (x2 ?? x) >= -4 && x <= w + 4)
      .map((p) => {
        const width = 16 + Math.max(2, p.l.text.length) * 7
        let row = rows.findIndex((r) => r <= p.x)
        if (row < 0) row = 0
        rows[row] = p.x + width + 4
        return { ...p, row, color: labelColor(p.l.text) }
      })
  })
</script>

<div class="host" bind:this={host}></div>

<div class="overlay" bind:this={overlay}>
  {#each placed as { l, x, x2, row, color } (l.id)}
    {#if x2 !== null}
      <div class="range" style="left:{x}px;width:{Math.max(1, x2 - x)}px;--c:{color}"></div>
      <div class="edge" style="left:{x2}px;--c:{color}" onpointerdown={(e) => dragLabel(e, l.id, 'end')} role="presentation"></div>
    {/if}
    <div class="line" class:sel={app.selectedId === l.id} style="left:{x}px;--c:{color}" onpointerdown={(e) => dragLabel(e, l.id)} role="presentation"></div>
    <div
      class="chip" class:sel={app.selectedId === l.id} class:auto={l.auto}
      style="left:{x}px;top:{6 + row * 22}px;--c:{color}"
      onpointerdown={(e) => dragLabel(e, l.id)}
      ondblclick={(e) => { e.stopPropagation(); app.editingId = l.id }}
      role="presentation"
    >
      {#if app.editingId === l.id}
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="text" autofocus value={l.text} size={Math.max(4, l.text.length + 1)}
          onpointerdown={(e) => e.stopPropagation()}
          onfocus={(e) => e.currentTarget.select()}
          onkeydown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') { app.editingId = null } e.stopPropagation() }}
          onblur={(e) => { if (app.editingId === l.id) { app.renameLabel(l.id, e.currentTarget.value); app.editingId = null } }}
        />
      {:else}
        {l.text || '·'}
      {/if}
    </div>
  {/each}
  {#if box}<div class="box" style="left:{box.x0}px;width:{box.x1 - box.x0}px"></div>{/if}
  {#if app.cursor && app.dataset}
    <div class="readout mono">
      <div>{formatTime(app.cursor.t, app.dataset.tz)}</div>
      {#each app.measureInfo.filter((m) => app.cursor!.values[m.id] != null) as m (m.id)}
        <div><i style="background:{m.color}"></i>{m.name}: <b>{app.cursor.values[m.id]!.toFixed(2)}</b> {m.unit}</div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .host { position: absolute; inset: 0; }
  /* Layering: ranges < marker lines < flags, so flags are never crossed by any line */
  .overlay { position: absolute; inset: 0; pointer-events: none; overflow: hidden; z-index: 5; isolation: isolate; }
  .line { position: absolute; z-index: 2; top: 0; bottom: 0; width: 9px; margin-left: -4px; pointer-events: auto; cursor: ew-resize; }
  .line::after { content: ''; position: absolute; left: 4px; top: 0; bottom: 0; width: 1.5px; background: var(--c); opacity: 0.75; }
  .line.sel { z-index: 3; }
  .line.sel::after { width: 2.5px; left: 3px; opacity: 1; box-shadow: 0 0 8px var(--c); }
  .line:hover::after { opacity: 1; }
  .range { position: absolute; z-index: 1; top: 0; bottom: 0; background: var(--c); opacity: 0.13; }
  .edge { position: absolute; z-index: 2; top: 0; bottom: 0; width: 7px; margin-left: -3px; cursor: ew-resize; pointer-events: auto; }
  .edge::after { content: ''; position: absolute; left: 3px; top: 0; bottom: 0; width: 1px; background: var(--c); }
  .chip {
    position: absolute; z-index: 10; transform: translateX(-4px); padding: 1px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; white-space: nowrap;
    background: color-mix(in srgb, var(--c) 22%, var(--panel)); border: 1px solid var(--c); color: var(--text); pointer-events: auto; cursor: grab;
  }
  .chip.auto { border-style: dashed; }
  .chip.sel { z-index: 11; background: var(--c); color: #0b0e14; }
  .chip input { all: unset; min-width: 3ch; }
  .box { position: absolute; top: 0; bottom: 0; background: var(--accent-soft); border: 1px solid var(--accent); }
  .readout {
    position: absolute; z-index: 20; right: 12px; bottom: 34px; padding: 6px 10px; border-radius: 8px; background: var(--tooltip-bg);
    border: 1px solid var(--border); box-shadow: var(--shadow); color: var(--text); white-space: nowrap; line-height: 1.5;
  }
  .readout i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
</style>
