import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { cachedFile, withCacheLease } from "../src/cache.js";
import { config } from "../src/config.js";

test("temporary cache expires after a minute-equivalent and never during an active request", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "annoticity-cache-test-"));
  const original = config.cacheTtlMs;
  config.cacheTtlMs = 50;
  const file = path.join(dir, "cache");
  try {
    await withCacheLease(async () => {
      await cachedFile(file, async () => Buffer.from("data"));
      await new Promise((resolve) => setTimeout(resolve, 100));
      assert.equal(await fs.readFile(file, "utf8"), "data");
    });
    await assert.rejects(fs.access(file), { code: "ENOENT" });
    await cachedFile(file, async () => Buffer.from("new"));
    await new Promise((resolve) => setTimeout(resolve, 100));
    await assert.rejects(fs.access(file), { code: "ENOENT" });
  } finally {
    config.cacheTtlMs = original;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
