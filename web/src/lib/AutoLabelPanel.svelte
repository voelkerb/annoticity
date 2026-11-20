<script lang="ts">
  import { app } from './state.svelte'

  let advanced = $state(false)
  const rates = $derived([0.1, 0.5, 1, 2, 5, 10, 50].filter((r) => !app.dataset || r <= app.dataset.sampleRate))
  const a = app.auto
</script>

{#if app.dataset}
  <section>
    <p class="muted intro">Detects step changes in the signal, clusters the power levels into states and adds a label at every transition.</p>

    <div class="grid">
      <label>Channel
        <select bind:value={a.measure}>
          {#each app.dataset.measures as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
        </select>
      </label>
      <label>Analysis rate
        <select bind:value={a.rate}>
          {#each rates as r}<option value={r}>{r} Hz</option>{/each}
        </select>
      </label>
      <label>Min. change (W)
        <input type="number" min="0.1" step="1" bind:value={a.thres} />
      </label>
      <label>Scope
        <select bind:value={a.scope}>
          <option value="all">Whole recording</option>
          <option value="view">Visible range</option>
        </select>
      </label>
    </div>

    <button class="link" onclick={() => (advanced = !advanced)}>{advanced ? '▾' : '▸'} Advanced</button>
    {#if advanced}
      <div class="grid">
        <label>Relative threshold<input type="number" min="0" step="0.001" bind:value={a.linearCoeff} /></label>
        <label>Min. distance (s)<input type="number" min="0.02" step="0.5" bind:value={a.minDist} /></label>
        <label>Window before (s)<input type="number" min="0.02" step="0.5" bind:value={a.pre} /></label>
        <label>Window after (s)<input type="number" min="0.02" step="0.5" bind:value={a.post} /></label>
      </div>
    {/if}

    <label class="check"><input type="checkbox" bind:checked={a.replace} /> Replace previous auto labels</label>
    <button class="btn primary run" onclick={() => app.runAutoLabel()} disabled={app.autoRunning}>
      {app.autoRunning ? 'Analyzing…' : 'Find events'}
    </button>

    {#if app.autoResult}
      {@const r = app.autoResult}
      <div class="result">
        <b>{r.labels.length} events</b> <span class="muted">· {r.rate} Hz · {r.ms} ms</span>
        {#if r.states.length}
          <table>
            <thead><tr><th>State</th><th>Level</th><th>Time</th></tr></thead>
            <tbody>
              {#each r.states as s (s.id)}
                <tr><td>S{s.id}</td><td>{s.mean} W</td><td>{s.seconds >= 3600 ? (s.seconds / 3600).toFixed(1) + ' h' : Math.round(s.seconds / 60) + ' min'}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    {/if}
  </section>
{/if}

<style>
  section { padding: 4px 12px 12px; display: flex; flex-wrap: wrap; gap: 10px 20px; align-items: flex-start; overflow: auto; }
  .intro { margin: 0; font-size: 13px; flex-basis: 100%; }
  .grid { display: grid; grid-template-columns: repeat(4, minmax(120px, 180px)); gap: 8px; }
  label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text); }
  .link { background: none; border: 0; color: var(--muted); text-align: left; padding: 0; }
  .run { justify-content: center; padding: 9px; }
  .result { min-width: 240px; border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; background: var(--panel-2); font-size: 13px; }
  table { width: 100%; margin-top: 6px; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; color: var(--muted); font-weight: 500; }
  td, th { padding: 2px 4px; }
</style>
