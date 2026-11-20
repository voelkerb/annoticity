import express from "express";
import multer from "multer";
import os from "node:os";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "./config.js";
import { listDatasets, provider, meterInfo, dayFile, waveform } from "./datasets/index.js";
import { decodeMedia } from "./media.js";
import { withCacheLease } from "./cache.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const BINARY = "application/octet-stream";
const WINDOW_MS = 60_000;
const IP_LIMIT = 100;
const GLOBAL_LIMIT = 300;
const MAX_IPS = 10_000;
const MAX_ACTIVE = 4;

/**
 * The server only does what a browser cannot: fetch dataset files (FIRED over basic auth without
 * CORS, BLOND over FTP, REDD/UK-DALE/ECO from local folders) and decode WavPack/Matroska/HDF5. Everything else (downsampling, auto labeling,
 * CSV parsing, labels) runs in the browser on the returned float32 channels.
 */
export function createApp({ publicMode = config.publicMode, trustProxy = config.trustProxy } = {}) {
  const app = express();
  const upload = multer({
    dest: path.join(os.tmpdir(), "annoticity-upload"),
    limits: { fileSize: publicMode ? config.publicMaxUploadBytes : config.maxUploadBytes, files: 1, fields: 0 },
  }).single("file");
  let active = 0;
  let uploading = false;
  const wrap = (fn) => async (req, res, next) => {
    if (publicMode && active >= MAX_ACTIVE) {
      res.set("Retry-After", "5").status(503).json({ error: "Server busy; please try again later." });
      return;
    }
    active++;
    try { await withCacheLease(() => fn(req, res)); } catch (e) { next(e); } finally { active--; }
  };

  if (publicMode) {
    let global = { count: 0, reset: Date.now() + WINDOW_MS };
    const clients = new Map();
    app.disable("x-powered-by");
    if (trustProxy) app.set("trust proxy", "loopback");
    app.use((req, res, next) => {
      res.set({
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
      });
      const now = Date.now();
      if (now >= global.reset) global = { count: 0, reset: now + WINDOW_MS };
      global.count++;
      let client = clients.get(req.ip);
      if (!client || now >= client.reset) {
        if (!client && clients.size >= MAX_IPS) {
          for (const [ip, entry] of clients) if (now >= entry.reset) clients.delete(ip);
        }
        if (!client && clients.size >= MAX_IPS) {
          res.set("Retry-After", "60").status(429).json({ error: "Too many requests; please try again later." });
          return;
        }
        client = { count: 0, reset: now + WINDOW_MS };
        clients.set(req.ip, client);
      }
      client.count++;
      if (global.count > GLOBAL_LIMIT || client.count > IP_LIMIT) {
        const reset = global.count > GLOBAL_LIMIT ? global.reset : client.reset;
        res.set("Retry-After", String(Math.max(1, Math.ceil((reset - now) / 1000))))
          .status(429).json({ error: "Too many requests; please try again later." });
        return;
      }
      next();
    });
  }

  const num = (v, name) => {
    const n = Number(v);
    if (!Number.isFinite(n)) throw Object.assign(new Error(`${name} must be a number`), { status: 400 });
    return n;
  };

  app.get("/api/health", (_req, res) => res.json({ ok: true }));

  app.get("/api/datasets", wrap(async (_req, res) => res.json(await listDatasets())));
  app.get("/api/datasets/:ds/meters", wrap(async (req, res) => res.json(await provider(req.params.ds).meters())));
  app.get("/api/datasets/:ds/meters/:meter/days", wrap(async (req, res) => {
    const p = provider(req.params.ds);
    await meterInfo(p, req.params.meter);
    res.json({ days: await p.days(req.params.meter) });
  }));

  app.get("/api/datasets/:ds/meters/:meter/days/:day", wrap(async (req, res) => {
    provider(req.params.ds);
    const file = await dayFile(req.params.ds, req.params.meter, req.params.day);
    await new Promise((resolve, reject) => res.type(BINARY).set("Cache-Control", publicMode ? "no-store" : "private, max-age=86400")
      .sendFile(file, { dotfiles: "allow" }, (err) => err ? reject(err) : resolve()));
  }));

  app.get("/api/datasets/:ds/meters/:meter/waveform", wrap(async (req, res) => {
    const start = num(req.query.start, "start"), stop = num(req.query.stop, "stop");
    if (!(stop > start)) throw Object.assign(new Error("stop must be after start"), { status: 400 });
    if (stop - start > 60) throw Object.assign(new Error("Zoom in to at most 60 seconds to load raw waveforms"), { status: 400 });
    if (Math.abs(start) > 8.63e12 || Math.abs(stop) > 8.63e12) throw Object.assign(new Error("Invalid waveform time range"), { status: 400 });
    await meterInfo(provider(req.params.ds), req.params.meter);
    res.type(BINARY).send(await waveform(req.params.ds, req.params.meter, start, stop));
  }));

  app.post("/api/decode", wrap(async (req, res) => {
    if (publicMode && uploading) throw Object.assign(new Error("Another upload is in progress; try again later."), { status: 503 });
    if (publicMode) uploading = true;
    try {
      await new Promise((resolve, reject) => upload(req, res, (err) => err ? reject(err) : resolve()));
      if (!req.file) throw Object.assign(new Error("No file received"), { status: 400 });
      const data = await decodeMedia(req.file.path, req.file.originalname);
      await fs.rm(req.file.path, { force: true });
      req.file = null;
      res.type(BINARY).send(data);
    } finally {
      try { if (req.file) await fs.rm(req.file.path, { force: true }); }
      finally { if (publicMode) uploading = false; }
    }
  }));

  const dist = path.resolve(here, "../../web/dist");
  app.use(express.static(dist));
  app.get(/^\/(?!api\/).*/, (_req, res, next) => res.sendFile(path.join(dist, "index.html"), (e) => e && next()));

  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    const status = err.status ?? (err.code === "LIMIT_FILE_SIZE" ? 413 : err instanceof multer.MulterError ? 400 : 500);
    if (status >= 500) console.error(err);
    res.status(status).json({ error: publicMode && status >= 500 ? "Server error" : err.message });
  });
  return app;
}
