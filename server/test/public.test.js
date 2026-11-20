import test from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { providers } from "../src/datasets/index.js";

async function withServer(options, fn) {
  const server = createApp(options).listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  try {
    await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve, reject) => server.close((err) => err ? reject(err) : resolve()));
  }
}

test("public mode exposes datasets and hides server errors", async () => {
  const original = providers.fired;
  providers.fired = { ...original, meters: async () => { throw new Error("private server detail"); } };
  try {
    await withServer({ publicMode: true }, async (url) => {
      const datasets = await (await fetch(`${url}/api/datasets`)).json();
      assert.deepEqual(datasets.map((d) => d.id), ["fired", "blond", "redd", "ukdale", "eco"]);
      assert.equal((await fetch(`${url}/api/decode`, { method: "POST" })).status, 400);
      const response = await fetch(`${url}/api/datasets/fired/meters`);
      assert.equal(response.status, 500);
      assert.deepEqual(await response.json(), { error: "Server error" });
      assert.equal(response.headers.get("x-content-type-options"), "nosniff");
      assert.equal(response.headers.get("x-powered-by"), null);
    });
  } finally {
    providers.fired = original;
  }
  await withServer({ publicMode: false }, async (url) => {
    assert.equal((await fetch(`${url}/api/decode`, { method: "POST" })).status, 400);
    assert.equal((await fetch(`${url}/api/datasets/__proto__/meters`)).status, 404);
  });
});

test("public rate limit ignores spoofed forwarding headers by default", async () => {
  await withServer({ publicMode: true, trustProxy: false }, async (url) => {
    for (let i = 0; i < 100; i++) {
      const response = await fetch(`${url}/api/health`, { headers: { "X-Forwarded-For": `192.0.2.${i}` } });
      assert.equal(response.status, 200);
    }
    const response = await fetch(`${url}/api/health`, { headers: { "X-Forwarded-For": "192.0.2.200" } });
    assert.equal(response.status, 429);
    assert.ok(Number(response.headers.get("retry-after")) > 0);
  });
});

test("dataset operations are bounded until work finishes, even after disconnect", async () => {
  const original = providers.fired;
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  let started = 0;
  let allStarted;
  const ready = new Promise((resolve) => { allStarted = resolve; });
  providers.fired = {
    ...original,
    meters: async () => [{ id: "meter" }],
    days: async () => {
      if (++started === 4) allStarted();
      await pending;
      return [];
    },
  };
  try {
    await withServer({ publicMode: true }, async (url) => {
      const endpoint = `${url}/api/datasets/fired/meters/meter/days`;
      const controller = new AbortController();
      const requests = Array.from({ length: 4 }, (_, i) =>
        fetch(endpoint, i === 0 ? { signal: controller.signal } : {}).catch((e) => e));
      try {
        await ready;
        controller.abort();
        assert.equal((await fetch(endpoint)).status, 503);
      } finally {
        release();
        await Promise.all(requests);
      }
      assert.equal((await fetch(endpoint)).status, 200);
    });
  } finally {
    release();
    providers.fired = original;
  }
});

test("meter IDs are checked before provider requests and extreme waveform times are rejected", async () => {
  const original = providers.fired;
  let calls = 0;
  providers.fired = {
    ...original,
    meters: async () => [{ id: "meter" }],
    days: async () => { calls++; return []; },
    waveform: async () => { calls++; return null; },
  };
  try {
    await withServer({ publicMode: false }, async (url) => {
      assert.equal((await fetch(`${url}/api/datasets/fired/meters/..%2Fsecret/days`)).status, 404);
      assert.equal((await fetch(`${url}/api/datasets/fired/meters/not-a-meter/waveform?start=1&stop=2`)).status, 404);
      assert.equal((await fetch(`${url}/api/datasets/fired/meters/meter/waveform?start=1e16&stop=10000000000000002`)).status, 400);
      assert.equal(calls, 0);
      assert.equal((await fetch(`${url}/api/datasets/fired/meters/meter/days`)).status, 200);
      assert.equal(calls, 1);
    });
  } finally {
    providers.fired = original;
  }
});
