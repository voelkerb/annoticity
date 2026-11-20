<script lang="ts">
  import { download, exportLabels, formatTime, importLabels, labelColor, type LabelFormat } from './labels'
  import { app } from './state.svelte'

  let filter = $state('')
  let format = $state<LabelFormat>('csv')
  let inputs: Record<string, HTMLInputElement | undefined> = $state({})

  const shown = $derived(app.sortedLabels.filter((l) => !filter || l.text.toLowerCase().includes(filter.toLowerCase())))
  // Texts already used, most frequent first, for quick reuse as the text of new labels
  const texts = $derived.by(() => {
    const counts = new Map<string, number>()
    for (const l of app.labels) if (l.text) counts.set(l.text, (counts.get(l.text) ?? 0) + 1)
    return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  })

  let open = $state(false)
  let typed = $state(false)
  let active = $state(-1)
  let presetInput: HTMLInputElement | undefined = $state()
  const options = $derived(
    typed && app.defaultText ? texts.filter(([t]) => t.toLowerCase().includes(app.defaultText.toLowerCase())) : texts,
  )

  function openList(fromTyping: boolean) {
    typed = fromTyping
    open = true
    active = -1
  }
  function pick(text: string) {
    app.defaultText = text
    open = false
    presetInput?.blur()
  }
  function presetKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) return openList(false)
      const n = options.length
      if (n) active = (active + (e.key === 'ArrowDown' ? 1 : n - 1)) % n
    } else if (e.key === 'Enter') {
      if (open && active >= 0 && options[active]) pick(options[active][0])
      else { open = false; presetInput?.blur() }
    } else if (e.key === 'Escape') {
      if (open) { open = false; e.stopPropagation() } else presetInput?.blur()
    }
  }

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
    <div class="preset" onfocusout={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && (open = false)}>
      <label for="label-preset" title="Labels you add by clicking the chart start with this text">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>
        New labels
      </label>
      <div class="combo" class:open>
        <span class="dot" style="background:{labelColor(app.defaultText)}"></span>
        <input
          id="label-preset" type="text" placeholder="no text" autocomplete="off" bind:this={presetInput}
          role="combobox" aria-expanded={open} aria-controls="label-preset-list" aria-autocomplete="list"
          bind:value={app.defaultText}
          oninput={() => openList(true)}
          onkeydown={presetKey}
        />
        {#if app.defaultText}
          <button class="icon" onclick={() => { app.defaultText = ''; presetInput?.focus() }} aria-label="Clear text for new labels" title="Clear">✕</button>
        {/if}
        <button class="icon" onclick={() => (open ? (open = false) : (openList(false), presetInput?.focus()))} aria-label="Show used label texts" title="Used label texts" disabled={!texts.length}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        {#if open && options.length}
          <ul class="menu" id="label-preset-list" role="listbox">
            {#each options as [t, n], i (t)}
              <li role="option" aria-selected={i === active} class:active={i === active}>
                <button tabindex="-1" onmousedown={(e) => e.preventDefault()} onclick={() => pick(t)}>
                  <span class="dot" style="background:{labelColor(t)}"></span><span class="txt">{t}</span><span class="n">{n}×</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
    {#if app.labels.length > 6}<input class="filter" type="search" placeholder="Filter labels" bind:value={filter} aria-label="Filter labels" />{/if}
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
  .preset { display: flex; align-items: center; gap: 8px; }
  .preset label { display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: var(--muted); white-space: nowrap; cursor: help; }
  .preset label svg, .icon svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .combo {
    position: relative; display: flex; align-items: center; gap: 2px; width: 240px; padding: 0 4px 0 9px;
    border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2);
  }
  .combo:focus-within { border-color: var(--accent); }
  .combo input { flex: 1; min-width: 0; border: 0; background: transparent; padding: 4px 2px; font-size: 13px; box-shadow: none; outline: none; }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; }
  .icon { display: grid; place-items: center; width: 22px; height: 22px; padding: 0; border: 0; border-radius: 5px; background: transparent; color: var(--muted); font-size: 11px; }
  .icon:hover:not(:disabled) { background: var(--accent-soft); color: var(--text); }
  .icon:disabled { opacity: 0.35; cursor: default; }
  .open .icon:last-of-type svg { transform: rotate(180deg); }
  .menu {
    position: absolute; z-index: 30; left: -1px; right: -1px; top: calc(100% + 4px); max-height: 220px; overflow: auto;
    display: block; margin: 0; padding: 4px; list-style: none;
    border: 1px solid var(--border); border-radius: 8px; background: var(--tooltip-bg); box-shadow: var(--shadow);
  }
  .menu li { display: block; padding: 0; border: 0; }
  .menu button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 5px 8px; border: 0; border-radius: 5px; background: transparent; color: var(--text); text-align: left; font-size: 13px; }
  .menu li.active button, .menu button:hover { background: var(--accent-soft); }
  .menu .txt { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .menu .n { color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .filter { width: 180px; font-size: 13px; padding: 4px 8px; }
  ul { list-style: none; margin: 0; padding: 0 6px 6px; overflow: auto; flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 2px 8px; align-content: start; }
  li { display: grid; grid-template-columns: auto 1fr auto auto; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 8px; border: 1px solid transparent; }
  li.sel { background: var(--accent-soft); border-color: var(--accent); }
  li.empty { display: block; padding: 14px 10px; grid-column: 1 / -1; }
  li input { padding: 3px 7px; }
  .time { border: 0; background: transparent; padding: 2px 4px; border-left: 3px solid var(--c); border-radius: 3px; }
  .time:hover { background: var(--panel-2); }
  .auto { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
</style>
