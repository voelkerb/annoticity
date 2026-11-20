<script lang="ts">
  import AutoLabelPanel from './lib/AutoLabelPanel.svelte'
  import Chart from './lib/Chart.svelte'
  import LabelPanel from './lib/LabelPanel.svelte'
  import Sidebar from './lib/Sidebar.svelte'
  import Toasts from './lib/Toasts.svelte'
  import Toolbar from './lib/Toolbar.svelte'
  import { formatTime } from './lib/labels'
  import { app } from './lib/state.svelte'
  import { fade } from 'svelte/transition'

  let panel = $state<'labels' | 'auto'>('labels')
  let help = $state(false)
  let hintVisible = $state(false)

  $effect(() => {
    if (!app.addMode) { hintVisible = false; return }
    hintVisible = true
    const timer = setTimeout(() => (hintVisible = false), 6000)
    return () => clearTimeout(timer)
  })
  let open = $state(true)

  $effect(() => { document.documentElement.dataset.theme = app.theme })

  function onKey(e: KeyboardEvent) {
    if (e.target instanceof Element && e.target.closest('input, select, textarea')) return
    const mod = e.metaKey || e.ctrlKey
    if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? app.redo() : app.undo(); return }
    if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); app.redo(); return }
    if (mod || !app.dataset) return
    const [min, max] = app.view
    switch (e.key) {
      case 'a': case 'A': app.addMode = !app.addMode; break
      case 'Escape': app.addMode = false; app.selectedId = null; help = false; break
      case 'Delete': case 'Backspace': if (app.selectedId) app.removeLabel(app.selectedId); break
      case '0': case 'Home': app.resetView(); break
      case '+': case '=': app.setView(min + app.span * 0.25, max - app.span * 0.25, true); break
      case '-': app.setView(min - app.span * 0.5, max + app.span * 0.5, true); break
      case 'ArrowLeft': app.setView(min - app.span * 0.2, max - app.span * 0.2); break
      case 'ArrowRight': app.setView(min + app.span * 0.2, max + app.span * 0.2); break
      case '[': app.step(-1); break
      case ']': app.step(1); break
      case '?': help = !help; break
      default: return
    }
    e.preventDefault()
  }

  const shortcuts: [string, string][] = [
    ['A', 'Toggle label mode, then click the chart'], ['Del', 'Delete selected label'], ['Double-click chip', 'Rename label'],
    ['Drag label', 'Move label'], ['Wheel', 'Zoom around cursor'], ['Drag', 'Pan'], ['Shift + drag', 'Zoom to selection'],
    ['Wheel / drag on y axis', 'Zoom / pan y'], ['Alt + wheel', 'Zoom y'],
    ['0 / double-click', 'Fit full range and y'], ['← →', 'Pan'], ['+ −', 'Zoom'], ['[ ]', 'Previous / next label'], ['Ctrl/⌘ Z', 'Undo (Shift for redo)'],
  ]
</script>

<svelte:window onkeydown={onKey} />

{#snippet lightning()}
  <svg class="logo" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M13.5 1 4 13h7l-1 10 10-13h-7z" />
  </svg>
{/snippet}

<div class="shell">
  <header>
    <div class="brand">{@render lightning()} Annoticity <span class="tag">v2</span></div>
    {#if app.dataset}
      <div class="ds">
        <b>{app.dataset.title}</b>
        <span class="muted">{app.dataset.info ? app.dataset.info + ' · ' : ''}{formatTime(app.dataset.start, app.dataset.tz, false).slice(0, 10)} · {app.dataset.sampleRate < 1 ? app.dataset.sampleRate.toPrecision(2) : Math.round(app.dataset.sampleRate)} Hz · {app.dataset.samples.toLocaleString()} samples · {app.dataset.tz}</span>
      </div>
    {/if}
    <div class="spacer"></div>
    <button class="btn ghost sm" onclick={() => (help = true)} title="Keyboard shortcuts (?)">Shortcuts <span class="kbd">?</span></button>
    <button class="btn ghost sm" onclick={() => app.setTheme(app.theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">{app.theme === 'dark' ? '☀' : '☾'}</button>
    <a class="btn ghost sm" href="https://github.com/voelkerb/annoticity" target="_blank" rel="noreferrer">GitHub</a>
  </header>

  <Sidebar />
  <div><Toolbar /></div>

  <main class="plot">
    {#if app.dataset}
      <Chart />
      {#if !app.series}<div class="center muted">Loading data…</div>{/if}
      {#if app.addMode && hintVisible}<div class="hint" transition:fade={{ duration: 200 }}>Label mode: click on the chart to add a label · <span class="kbd">Esc</span> to stop</div>{/if}
    {:else}
      <div class="center empty">
        <div class="empty-logo">{@render lightning()}</div>
        <h2>Inspect and label electricity data</h2>
        <p class="muted">Pick a meter and day of the FIRED dataset above, or upload your own CSV / MKV file.</p>
      </div>
    {/if}
    {#if app.busy}
      <div class="busy"><div class="spinner"></div><span>{app.busy}…</span></div>
    {/if}
  </main>

  {#if app.dataset}
  <section class="drawer" class:closed={!open}>
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected={open && panel === 'labels'} class:active={open && panel === 'labels'} onclick={() => { panel = 'labels'; open = true }}>Labels <span class="count">{app.labels.length}</span></button>
      <button role="tab" aria-selected={open && panel === 'auto'} class:active={open && panel === 'auto'} onclick={() => { panel = 'auto'; open = true }}>Auto-label</button>
      <div class="spacer"></div>
      <button class="btn ghost sm" onclick={() => (open = !open)} aria-label="Toggle panel">{open ? '▾ Hide' : '▴ Show'}</button>
    </div>
    {#if open}
      <div class="body">{#if panel === 'labels'}<LabelPanel />{:else}<AutoLabelPanel />{/if}</div>
    {/if}
  </section>
  {/if}
</div>

{#if help}
  <div class="modal" role="presentation" onclick={() => (help = false)}>
    <div class="card" role="dialog" aria-label="Keyboard shortcuts" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
      <h3>Shortcuts</h3>
      <dl>{#each shortcuts as [k, d]}<dt><span class="kbd">{k}</span></dt><dd>{d}</dd>{/each}</dl>
    </div>
  </div>
{/if}

<Toasts />

<style>
  .shell { display: grid; grid-template-rows: 52px auto auto minmax(0, 1fr) auto; grid-template-columns: minmax(0, 1fr); height: 100%; }
  header { display: flex; align-items: center; gap: 14px; padding: 0 14px; border-bottom: 1px solid var(--border); background: var(--panel); }
  .brand { font-weight: 700; font-size: 16px; display: flex; align-items: center; gap: 8px; }
  .logo { color: var(--accent); width: 20px; height: 20px; flex: none; }
  .empty-logo .logo { width: 56px; height: 56px; }
  .tag { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: var(--accent-soft); color: var(--accent-text); }
  .ds { display: grid; line-height: 1.2; font-size: 13px; }
  .ds .muted { font-size: 12px; }
  .spacer { flex: 1; }
  a.btn { text-decoration: none; }
  .plot { position: relative; min-height: 0; background: var(--plot-bg); }
  .center { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; pointer-events: none; }
  .empty h2 { margin: 4px 0; }
  .empty p { max-width: 380px; margin: 0 auto; }
  .hint { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); padding: 4px 12px; border-radius: 999px; background: var(--accent); color: var(--accent-contrast); font-size: 12px; pointer-events: none; z-index: 5; }
  .busy { position: absolute; inset: 0; display: flex; gap: 12px; align-items: center; justify-content: center; background: color-mix(in srgb, var(--bg) 78%, transparent); backdrop-filter: blur(3px); z-index: 10; }
  .spinner { width: 20px; height: 20px; border-radius: 50%; border: 3px solid var(--border); border-top-color: var(--accent); animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .drawer { display: flex; flex-direction: column; background: var(--panel); border-top: 1px solid var(--border); height: clamp(210px, 30vh, 380px); }
  .drawer.closed { height: auto; }
  .drawer .tabs { display: flex; align-items: center; gap: 4px; padding: 6px 10px; }
  .drawer .tabs button:not(.btn) { padding: 6px 14px; border-radius: 8px; border: 0; background: transparent; color: var(--muted); font-weight: 600; }
  .drawer .tabs button.active { background: var(--accent-soft); color: var(--text); }
  .count { margin-left: 4px; padding: 0 7px; border-radius: 999px; background: var(--accent-soft); font-size: 12px; }
  .body { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: auto; }
  .modal { position: fixed; inset: 0; display: grid; place-items: center; background: rgba(0, 0, 0, 0.5); z-index: 60; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 18px 22px; box-shadow: var(--shadow); min-width: 380px; }
  .card h3 { margin: 0 0 10px; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 16px; margin: 0; }
  dd { margin: 0; color: var(--muted); }
</style>
