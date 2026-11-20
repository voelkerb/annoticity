import fs from "node:fs/promises";
import path from "node:path";
import { AsyncLocalStorage } from "node:async_hooks";
import { config } from "./config.js";

const inflight = new Map();
const leases = new AsyncLocalStorage();
const entries = new Map();

function schedule(file) {
  if (!config.cacheTtlMs) return;
  const entry = entries.get(file) ?? { users: 0 };
  entries.set(file, entry);
  clearTimeout(entry.timer);
  entry.expires = Date.now() + config.cacheTtlMs;
  entry.timer = setTimeout(() => expire(file, entry), config.cacheTtlMs);
  entry.timer.unref();
}

async function expire(file, entry) {
  entry.timer = null;
  if (entry.users) return;
  if (inflight.has("file:" + file)) {
    entry.timer = setTimeout(() => expire(file, entry), 1000);
    entry.timer.unref();
    return;
  }
  entry.deleting = fs.rm(file, { force: true });
  try {
    await entry.deleting;
    if (entries.get(file) === entry) entries.delete(file);
  } catch (e) {
    console.error(`Failed to remove expired cache file: ${file}`, e);
    entry.deleting = null;
    entry.timer = setTimeout(() => expire(file, entry), 1000);
    entry.timer.unref();
  }
}

function use(file) {
  if (!config.cacheTtlMs) return;
  schedule(file);
  const held = leases.getStore();
  if (held && !held.has(file)) {
    held.add(file);
    entries.get(file).users++;
  }
}

/** Keep cached files alive until the request using them has finished. */
export async function withCacheLease(fn) {
  if (!config.cacheTtlMs) return fn();
  const held = new Set();
  return leases.run(held, async () => {
    try { return await fn(); } finally {
      for (const file of held) {
        const entry = entries.get(file);
        if (entry && --entry.users === 0 && !entry.timer) {
          if (Date.now() >= entry.expires) await expire(file, entry);
          else schedule(file);
        }
      }
    }
  });
}

/** Run `fn` once per key at a time; concurrent callers share the same promise. */
export function once(key, fn) {
  if (!inflight.has(key)) inflight.set(key, fn().finally(() => inflight.delete(key)));
  return inflight.get(key);
}

export async function exists(file) {
  try { await fs.access(file); return true; } catch { return false; }
}

/** Write a file atomically so concurrent readers never see partial content. */
export async function writeAtomic(dest, data) {
  await fs.mkdir(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.${process.pid}.${Math.random().toString(36).slice(2)}.part`;
  try {
    await fs.writeFile(tmp, data);
    await fs.rename(tmp, dest);
  } finally {
    await fs.rm(tmp, { force: true });
  }
  schedule(dest);
  return dest;
}

/** Return `dest`, producing it with `produce()` (Buffer) on first use. */
export async function cachedFile(dest, produce) {
  const deleting = entries.get(dest)?.deleting;
  if (deleting) await deleting;
  const file = await once("file:" + dest, async () => ((await exists(dest)) ? dest : writeAtomic(dest, await produce())));
  use(file);
  return file;
}

export function httpError(status, message) {
  return Object.assign(new Error(message), { status });
}
