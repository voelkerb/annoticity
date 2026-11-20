<script lang="ts">
  import { labelColor } from './labels'
  import { app } from './state.svelte'

  const o = $derived(app.renameOffer)
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && app.renameOffer && app.dismissRename()} />

<div class="toasts" aria-live="polite">
  {#if o}
    <div class="toast rename" role="group" aria-label="Rename other labels">
      <div class="head">
        <span>Also rename the other <b>{o.before + o.after}</b>
          <span class="tag" style="--c:{labelColor(o.from)}">{o.from}</span> to
          <span class="tag" style="--c:{labelColor(o.to)}">{o.to || '(empty)'}</span>?</span>
        <button class="close" onclick={() => app.dismissRename()} aria-label="Keep the others" title="Only this one (Esc)">✕</button>
      </div>
      <div class="actions">
        <button class="btn sm" disabled={!o.before} onclick={() => app.applyRename('before')} title="Labels before this one">← Earlier <span class="n">{o.before}</span></button>
        <button class="btn sm primary" onclick={() => app.applyRename('all')}>All <span class="n">{o.before + o.after}</span></button>
        <button class="btn sm" disabled={!o.after} onclick={() => app.applyRename('after')} title="Labels after this one">Later <span class="n">{o.after}</span> →</button>
      </div>
    </div>
  {/if}
  {#each app.toasts as t (t.id)}
    <div class="toast {t.kind}">{t.text}</div>
  {/each}
</div>

<style>
  .toasts { position: fixed; right: 16px; bottom: 16px; display: grid; gap: 8px; z-index: 50; max-width: 400px; }
  .toast { padding: 10px 14px; border-radius: 10px; background: var(--panel); border: 1px solid var(--border); box-shadow: var(--shadow); animation: in 0.18s ease-out; }
  .toast.error { border-color: var(--danger); }
  .toast.success { border-color: var(--ok); }
  .rename { display: grid; gap: 10px; border-color: var(--accent); }
  .head { display: flex; align-items: flex-start; gap: 10px; line-height: 1.6; }
  .tag { display: inline-block; padding: 0 7px; border-radius: 6px; border-left: 3px solid var(--c); background: var(--panel-2); font-weight: 600; line-height: 1.5; }
  .close { margin-left: auto; padding: 0 4px; border: 0; background: transparent; color: var(--muted); }
  .close:hover { color: var(--text); }
  .actions { display: flex; gap: 6px; }
  .actions .btn { flex: 1; justify-content: center; }
  .n { opacity: 0.65; font-variant-numeric: tabular-nums; margin-left: 2px; }
  @keyframes in { from { opacity: 0; transform: translateY(8px); } }
</style>
