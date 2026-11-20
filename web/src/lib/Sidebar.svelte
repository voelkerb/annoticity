<script lang="ts">
  import { api, type Meter } from './api'
  import { app } from './state.svelte'

  const STORE = 'annoticity:v2:dataset'

  let tab = $state<'dataset' | 'upload'>('dataset')
  let source = $state(localStorage.getItem(STORE) ?? 'fired')
  let meters = $state<Meter[]>([])
  let loadingMeters = $state(false)
  let meter = $state<string | null>(null)
  let days = $state<string[]>([])
  let day = $state('')
  let dragging = $state(false)

  const current = $derived(app.datasets.find((d) => d.id === source))
  const groups = $derived.by(() => {
    const sorted = [...meters].sort((a, b) => Number(b.aggregate) - Number(a.aggregate))
    const map = new Map<string, Meter[]>()
    for (const m of sorted) map.set(m.group ?? '', [...(map.get(m.group ?? '') ?? []), m])
    return [...map.entries()].sort(([a], [b]) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b, undefined, { numeric: true })))
  })

  $effect(() => { app.loadDatasets() })

  $effect(() => {
    if (current?.available) loadMeters(current.id)
    else meters = []
  })

  async function loadMeters(ds: string) {
    meters = []; meter = null; days = []
    loadingMeters = true
    try {
      const list = await api.meters(ds)
      if (source === ds) meters = list
    } catch (e) {
      app.notify((e as Error).message, 'error')
    } finally {
      loadingMeters = false
    }
  }

  function chooseSource(id: string) {
    source = id
    localStorage.setItem(STORE, id)
  }

  async function pick(id: string) {
    const ds = source
    meter = id
    days = []
    try {
      days = await api.days(ds, id)
      if (!days.length) return app.notify('No recordings for this meter', 'error')
      const last = app.dataset?.dataset === ds && app.dataset.meter !== id ? app.dataset.day : undefined
      day = last && days.includes(last) ? last : days[Math.floor(days.length / 2)] ?? ''
      if (day) app.loadDay(ds, id, day)
    } catch (e) {
      app.notify((e as Error).message, 'error')
    }
  }

  function go(offset: number) {
    const i = days.indexOf(day) + offset
    if (i >= 0 && i < days.length && meter) { day = days[i]; app.loadDay(source, meter, day) }
  }

  function onDay() {
    if (!meter || !day) return
    if (!days.includes(day)) return app.notify('No recording for that day', 'error')
    app.loadDay(source, meter, day)
  }

  function onFiles(files: FileList | null | undefined) {
    const f = files?.[0]
    if (f) app.loadFile(f)
  }
</script>

<div class="source">
  <div class="tabs" role="tablist">
    <button role="tab" aria-selected={tab === 'dataset'} class:active={tab === 'dataset'} onclick={() => (tab = 'dataset')}>Datasets</button>
    <button role="tab" aria-selected={tab === 'upload'} class:active={tab === 'upload'} onclick={() => (tab = 'upload')}>Your data</button>
  </div>

  {#if tab === 'dataset'}
    <select class="datasets" value={source} onchange={(e) => { chooseSource(e.currentTarget.value); e.currentTarget.blur() }} aria-label="Dataset" title={current?.description}>
      {#if !app.datasets.length}<option value={source}>Loading…</option>{/if}
      {#each app.datasets as d (d.id)}
        <option value={d.id}>{d.name}{d.available ? '' : ' · not set up'}</option>
      {/each}
    </select>
    {#if current && !current.available}
      <span class="muted small notice">{current.reason}. <a href={current.url} target="_blank" rel="noreferrer">Get {current.name}</a></span>
    {:else if current}
      <select class="meters" value={meter ?? ''} onchange={(e) => { pick(e.currentTarget.value); e.currentTarget.blur() }} aria-label="Meter">
        <option value="" disabled>{loadingMeters ? 'Loading meters…' : meters.length ? 'Choose a meter…' : 'No meters found'}</option>
        {#each groups as [group, list] (group)}
          {#if group}
            <optgroup label={group}>
              {#each list as m (m.id)}<option value={m.id}>{m.label} · {m.short}</option>{/each}
            </optgroup>
          {:else}
            {#each list as m (m.id)}<option value={m.id}>{m.label} · {m.short}</option>{/each}
          {/if}
        {/each}
      </select>
      {#if meter && days.length}
        <div class="row">
          <button class="btn sm" onclick={() => go(-1)} disabled={days.indexOf(day) <= 0} aria-label="Previous day">◀</button>
          <input type="date" bind:value={day} min={days[0]} max={days.at(-1)} onchange={onDay} />
          <button class="btn sm" onclick={() => go(1)} disabled={days.indexOf(day) >= days.length - 1} aria-label="Next day">▶</button>
        </div>
        <span class="muted small">{days.length} days · {days[0]} → {days.at(-1)}</span>
      {:else if !meter && meters.length}
        <span class="muted small desc">{current.description}</span>
      {/if}
    {/if}
  {:else}
    <label
      class="drop" class:dragging
      ondragover={(e) => { e.preventDefault(); dragging = true }}
      ondragleave={() => (dragging = false)}
      ondrop={(e) => { e.preventDefault(); dragging = false; onFiles(e.dataTransfer?.files) }}
    >
      <input type="file" accept=".csv,.tsv,.txt,.mkv,.mka,.wv,.wav,.flac" hidden onchange={(e) => onFiles(e.currentTarget.files)} />
      <strong>Drop a file</strong> <span class="muted">or click to browse</span>
    </label>
    <span class="muted small">CSV with a header and a time column (timestamp, ts, time, date) plus numeric columns, or FIRED-style MKV.</span>
  {/if}
</div>

<style>
  .source { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border); }
  .tabs { display: flex; gap: 4px; }
  .tabs button { padding: 6px 12px; border-radius: 8px; border: 0; background: transparent; color: var(--muted); font-weight: 600; }
  .tabs button.active { background: var(--accent-soft); color: var(--text); }
  .datasets { width: auto; min-width: 120px; font-weight: 600; }
  .meters { width: 360px; max-width: 100%; }
  .notice a { color: var(--accent); }
  .desc { max-width: 520px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row { display: flex; gap: 6px; }
  .row input { width: auto; }
  .small { font-size: 12px; }
  .drop {
    display: flex; align-items: center; gap: 8px; padding: 6px 14px; cursor: pointer;
    border: 1.5px dashed var(--border); border-radius: var(--radius); background: var(--panel-2); transition: all 0.12s;
  }
  .drop:hover, .drop.dragging { border-color: var(--accent); background: var(--accent-soft); }
</style>
