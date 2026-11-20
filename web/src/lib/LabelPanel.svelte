<script lang="ts">
  import { download, exportLabels, formatTime, importLabels, labelColor, type LabelFormat } from './labels'
  import { app } from './state.svelte'

  let filter = $state('')
  let format = $state<LabelFormat>('csv')
  let inputs: Record<string, HTMLInputElement | undefined> = $state({})

  const shown = $derived(app.sortedLabels.filter((l) => !filter || l.text.toLowerCase().includes(filter.toLowerCase())))
  const texts = $derived([...new Set(app.labels.map((l) => l.text).filter(Boolean))])

  $effect(() => {
    const id = app.focusListId
    if (id && inputs[id]) {
      inputs[id]!.focus()
      inputs[id]!.select()
      app.focusListId = null
    }
  })

  function save() {
    const ds = app.dataset
    if (!ds) return
    const base = `${ds.meter ?? ds.title}${ds.day ? '_' + ds.day : ''}_labels`.replace(/\s+/g, '_')
    download(`${base}.${format}`, exportLabels(app.labels, format, ds.start))
  }

  async function load(e: Event) {
    const input = e.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file || !app.dataset) return
    try {
      const { labels, note } = importLabels(await file.text(), file.name, app.dataset.start)
      app.addImported(labels)
      app.notify(`Imported ${labels.length} labels${note ? ' · ' + note : ''}`, 'success')
    } catch (err) {
      app.notify((err as Error).message, 'error')
    }
  }
</script>

<section>
  <header>
    <div class="spacer"></div>
    <select bind:value={format} aria-label="Export format">
      <option value="csv">CSV</option>
      <option value="srt">SRT</option>
      <option value="ass">ASS</option>
      <option value="json">JSON</option>
    </select>
    <button class="btn sm primary" onclick={save} disabled={!app.labels.length}>Export</button>
    <label class="btn sm">Import<input type="file" accept=".csv,.srt,.ass,.json,.txt" hidden onchange={load} /></label>
    <button class="btn sm" onclick={() => app.clearLabels(true)} disabled={!app.labels.some((l) => l.auto)} title="Remove all auto-generated labels">Clear auto</button>
    <button class="btn sm" onclick={() => confirm('Remove all labels?') && app.clearLabels()} disabled={!app.labels.length}>Clear</button>
  </header>

  <div class="quick">
    <input type="text" placeholder="Text for new labels" bind:value={app.defaultText} list="label-texts" aria-label="Text for new labels" />
    <datalist id="label-texts">{#each texts as t}<option value={t}></option>{/each}</datalist>
    {#if app.labels.length > 6}<input type="text" placeholder="Filter labels" bind:value={filter} />{/if}
  </div>

  <ul>
    {#each shown as l (l.id)}
      <li class:sel={app.selectedId === l.id}>
        <button class="time mono" onclick={() => app.centerOn(l.id)} title="Jump to label" style="--c:{labelColor(l.text)}">
          {app.dataset ? formatTime(l.start, app.dataset.tz).slice(11) : ''}
        </button>
        <input
          type="text" value={l.text} placeholder="Add description…" bind:this={inputs[l.id]}
          onfocus={() => (app.selectedId = l.id)}
          onchange={(e) => app.renameLabel(l.id, e.currentTarget.value)}
          onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        />
        {#if l.auto}<span class="auto" title="Generated automatically">auto</span>{/if}
        <button class="btn sm ghost" onclick={() => app.removeLabel(l.id)} aria-label="Delete label">✕</button>
      </li>
    {:else}
      <li class="empty muted">
        No labels yet. Press <span class="kbd">A</span> and click on the chart, or run the auto labeler.
      </li>
    {/each}
  </ul>

</section>

<style>
  section { display: flex; flex-direction: column; min-height: 0; flex: 1; }
  header { display: flex; align-items: center; gap: 6px; padding: 4px 12px 8px; }
  /* Same box as the small buttons next to it */
  header select { width: auto; font-size: 12px; line-height: inherit; padding: 3px 28px 3px 8px; background-position: right 9px center; }
  .spacer { flex: 1; }
  .quick { padding: 0 12px 8px; display: flex; gap: 8px; }
  .quick input { max-width: 260px; }
  ul { list-style: none; margin: 0; padding: 0 6px 6px; overflow: auto; flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 2px 8px; align-content: start; }
  li { display: grid; grid-template-columns: auto 1fr auto auto; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 8px; border: 1px solid transparent; }
  li.sel { background: var(--accent-soft); border-color: var(--accent); }
  li.empty { display: block; padding: 14px 10px; grid-column: 1 / -1; }
  li input { padding: 3px 7px; }
  .time { border: 0; background: transparent; padding: 2px 4px; border-left: 3px solid var(--c); border-radius: 3px; }
  .time:hover { background: var(--panel-2); }
  .auto { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
</style>
