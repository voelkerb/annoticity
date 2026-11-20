import fs from "node:fs/promises";
import path from "node:path";

const inflight = new Map();

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
  await fs.writeFile(tmp, data);
  await fs.rename(tmp, dest);
  return dest;
}

/** Return `dest`, producing it with `produce()` (Buffer) on first use. */
export function cachedFile(dest, produce) {
  return once("file:" + dest, async () => ((await exists(dest)) ? dest : writeAtomic(dest, await produce())));
}

export function httpError(status, message) {
  return Object.assign(new Error(message), { status });
}
