<script lang="ts">
  import { app } from './state.svelte'
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <div class="toast {t.kind}">{t.text}</div>
  {/each}
</div>

<style>
  .toasts { position: fixed; right: 16px; bottom: 16px; display: grid; gap: 8px; z-index: 50; max-width: 380px; }
  .toast { padding: 10px 14px; border-radius: 10px; background: var(--panel); border: 1px solid var(--border); box-shadow: var(--shadow); animation: in 0.18s ease-out; }
  .toast.error { border-color: var(--danger); }
  .toast.success { border-color: var(--ok); }
  @keyframes in { from { opacity: 0; transform: translateY(8px); } }
</style>
