import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import http from "node:http";
import { createApp } from "../src/app.js";

test("public uploads decode audio and reject unsupported files", { skip: spawnSync("ffmpeg", ["-version"]).status !== 0 }, async () => {
  const app = createApp({ publicMode: true });
  const server = app.listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  const url = `http://127.0.0.1:${server.address().port}/api/decode`;
  try {
    const wav = Buffer.alloc(48);
    wav.write("RIFF", 0); wav.writeUInt32LE(40, 4); wav.write("WAVEfmt ", 8);
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(4, 40);
    const form = new FormData();
    form.set("file", new Blob([wav]), "test.wav");
    const res = await fetch(url, { method: "POST", body: form });
    assert.equal(res.status, 200);
    const binary = Buffer.from(await res.arrayBuffer());
    const header = JSON.parse(binary.subarray(4, 4 + binary.readUInt32LE(0)));
    assert.equal(header.length, 2);
    const invalid = new FormData();
    invalid.set("file", new Blob(["hello"]), "test.txt");
    assert.equal((await fetch(url, { method: "POST", body: invalid })).status, 400);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

test("uploaded playlists cannot make FFmpeg fetch network resources", { skip: spawnSync("ffmpeg", ["-version"]).status !== 0 }, async () => {
  let requests = 0;
  const target = http.createServer((_req, res) => { requests++; res.end(); }).listen(0, "127.0.0.1");
  const server = createApp({ publicMode: true }).listen(0, "127.0.0.1");
  await Promise.all([target, server].map((s) => new Promise((resolve) => s.once("listening", resolve))));
  try {
    const playlist = `#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:${target.address().port}/segment.ts\n#EXT-X-ENDLIST\n`;
    const form = new FormData();
    form.set("file", new Blob([playlist]), "playlist.mkv");
    const res = await fetch(`http://127.0.0.1:${server.address().port}/api/decode`, { method: "POST", body: form });
    assert.notEqual(res.status, 200);
    assert.equal(requests, 0);
  } finally {
    server.closeAllConnections();
    target.closeAllConnections();
    await Promise.all([server, target].map((s) => new Promise((resolve) => s.close(resolve))));
  }
});
