<script lang="ts">
  import { api } from './api'
  import { app } from './state.svelte'

  let tab = $state<'fired' | 'upload'>('fired')
  let search = $state('')
  let meter = $state<string | null>(null)
  let days = $state<string[]>([])
  let day = $state('')
  let dragging = $state(false)

  const meters = $derived(
    app.meters
      .filter((m) => !search || (m.label + m.details.join(' ') + m.id).toLowerCase().includes(search.toLowerCase()))
      .sort((a, b) => Number(b.smartmeter) - Number(a.smartmeter) || a.label.localeCompare(b.label)),
  )

  $effect(() => { app.loadMeters() })

  async function pick(id: string) {
    meter = id
    days = []
    try {
      days = await api.days(id)
      const last = app.dataset?.meter === id ? app.dataset.day : undefined
      day = last && days.includes(last) ? last : days[Math.floor(days.length / 2)] ?? ''
      if (day) app.loadFired(id, day)
    } catch (e) {
      app.notify((e as Error).message, 'error')
    }
  }

  function go(offset: number) {
    const i = days.indexOf(day) + offset
    if (i >= 0 && i < days.length && meter) { day = days[i]; app.loadFired(meter, day) }
  }

  function onDay() {
    if (!meter || !day) return
    if (!days.includes(day)) return app.notify('No recording for that day', 'error')
    app.loadFired(meter, day)
  }

  function onFiles(files: FileList | null | undefined) {
    const f = files?.[0]
    if (f) app.loadFile(f)
  }
</script>

<div class="source">
  <div class="tabs" role="tablist">
    <button role="tab" aria-selected={tab === 'fired'} class:active={tab === 'fired'} onclick={() => (tab = 'fired')}>FIRED dataset</button>
    <button role="tab" aria-selected={tab === 'upload'} class:active={tab === 'upload'} onclick={() => (tab = 'upload')}>Your data</button>
  </div>

  {#if tab === 'fired'}
    <select class="meters" value={meter ?? ''} onchange={(e) => pick(e.currentTarget.value)} aria-label="Meter">
      <option value="" disabled>{app.meters.length ? 'Choose a meter…' : 'Loading meters…'}</option>
      {#each meters as m (m.id)}
        <option value={m.id}>{m.label}{m.smartmeter ? ' (all phases)' : ''} · {m.id.replace('powermeter', 'PM ').replace('smartmeter', 'SM ')}</option>
      {/each}
    </select>
    {#if meter && days.length}
      <div class="row">
        <button class="btn sm" onclick={() => go(-1)} disabled={days.indexOf(day) <= 0} aria-label="Previous day">◀</button>
        <input type="date" bind:value={day} min={days[0]} max={days.at(-1)} onchange={onDay} />
        <button class="btn sm" onclick={() => go(1)} disabled={days.indexOf(day) >= days.length - 1} aria-label="Next day">▶</button>
      </div>
      <span class="muted small">{days.length} days · {days[0]} → {days.at(-1)}</span>
    {/if}
  {:else}
    <label
      class="drop" class:dragging
      ondragover={(e) => { e.preventDefault(); dragging = true }}
      ondragleave={() => (dragging = false)}
      ondrop={(e) => { e.preventDefault(); dragging = false; onFiles(e.dataTransfer?.files) }}
    >
      <input type="file" accept=".csv,.tsv,.txt,.mkv,.mka" hidden onchange={(e) => onFiles(e.currentTarget.files)} />
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
  .meters { width: 340px; max-width: 100%; text-transform: capitalize; }
  .row { display: flex; gap: 6px; }
  .row input { width: auto; }
  .small { font-size: 12px; }
  .drop {
    display: flex; align-items: center; gap: 8px; padding: 6px 14px; cursor: pointer;
    border: 1.5px dashed var(--border); border-radius: var(--radius); background: var(--panel-2); transition: all 0.12s;
  }
  .drop:hover, .drop.dragging { border-color: var(--accent); background: var(--accent-soft); }
</style>
