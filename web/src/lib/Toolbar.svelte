<script lang="ts">
  import { app } from './state.svelte'
</script>

{#if app.dataset}
  <div class="bar">
    <div class="group" role="group" aria-label="Measures">
      {#each app.dataset.measures as m (m.id)}
        <button
          class="chip" class:off={!app.enabled.includes(m.id) || app.showingWaveform}
          style="--c:{m.color}" onclick={() => app.toggleMeasure(m.id)} disabled={app.showingWaveform}
          title="Show or hide {m.name}"
        ><i></i>{m.name}</button>
      {/each}
      {#if app.dataset.highFreq}
        <button
          class="btn sm" class:on={app.showingWaveform} disabled={!app.canWaveform && !app.waveform}
          onclick={() => app.setWaveform(!app.waveform)}
          title={app.canWaveform ? 'Show raw voltage and current' : 'Zoom in to 30 s or less to show raw voltage and current'}
        >∿ Raw V/I</button>
      {/if}
    </div>

    <div class="spacer"></div>
    {#if app.fetching}<span class="muted spin" title="Loading data">●</span>{/if}

    <div class="group">
      <button class="btn sm" class:on={app.addMode} onclick={() => (app.addMode = !app.addMode)} title="Click on the chart to add labels (A)">
        ＋ Label <span class="kbd">A</span>
      </button>
      <button class="btn sm" class:on={app.snap} onclick={() => (app.snap = !app.snap)} title="Snap new labels to the steepest edge nearby">Snap to edge</button>
    </div>
    <div class="group">
      <button class="btn sm ghost" onclick={() => app.undo()} disabled={!app.canUndo} title="Undo (Ctrl/⌘ Z)">↶</button>
      <button class="btn sm ghost" onclick={() => app.redo()} disabled={!app.canRedo} title="Redo (Ctrl/⌘ Shift Z)">↷</button>
    </div>
    <div class="group">
      <button class="btn sm ghost" onclick={() => app.setView(app.view[0] + app.span * 0.25, app.view[1] - app.span * 0.25, true)} title="Zoom in (+)">＋</button>
      <button class="btn sm ghost" onclick={() => app.setView(app.view[0] - app.span * 0.5, app.view[1] + app.span * 0.5, true)} title="Zoom out (−)">－</button>
      <button class="btn sm" onclick={() => app.resetView()} title="Show full range (0 or double-click)">Fit</button>
    </div>
  </div>
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .spacer { flex: 1; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px;
    border: 1px solid var(--c); background: color-mix(in srgb, var(--c) 16%, transparent);
  }
  .chip i { width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .chip.off { opacity: 0.45; border-color: var(--border); background: transparent; }
  .spin { animation: pulse 0.9s infinite alternate; font-size: 10px; }
  @keyframes pulse { to { opacity: 0.2; } }
</style>
