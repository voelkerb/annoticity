import { Client } from "basic-ftp";
import { Writable } from "node:stream";
import { httpError } from "./cache.js";

/**
 * Minimal FTP access with one reused connection; operations are serialised because an FTP
 * control connection can only run one command at a time.
 */
export function ftpSource({ host, user, password, root = "/" }) {
  let client = null;
  let queue = Promise.resolve();

  async function connected() {
    if (client && !client.closed) return client;
    client = new Client(30_000);
    await client.access({ host, user, password, secure: false });
    return client;
  }

  function run(fn) {
    const job = queue.then(async () => {
      try {
        return await fn(await connected());
      } catch (e) {
        client?.close();
        client = null;
        if (e.code === 550) throw httpError(404, `Not found on ${host}`);
        throw Object.assign(e, { status: e.status ?? 502 });
      }
    });
    queue = job.catch(() => {});
    return job;
  }

  return {
    list: (dir) => run(async (c) => (await c.list(root + dir)).map((f) => f.name)),
    download: (file) => run(async (c) => {
      const chunks = [];
      await c.downloadTo(new Writable({ write(chunk, _enc, cb) { chunks.push(chunk); cb(); } }), root + file);
      return Buffer.concat(chunks);
    }),
  };
}
