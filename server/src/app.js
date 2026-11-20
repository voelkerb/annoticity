import express from "express";
import multer from "multer";
import os from "node:os";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "./config.js";
import { listDatasets, provider, dayFile, waveform } from "./datasets/index.js";
import { decodeMedia } from "./media.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res)).catch(next);
const BINARY = "application/octet-stream";

/**
 * The server only does what a browser cannot: fetch dataset files (FIRED over basic auth without
 * CORS, BLOND over FTP, REDD/UK-DALE/ECO from local folders) and decode WavPack/Matroska/HDF5. Everything else (downsampling, auto labeling,
 * CSV parsing, labels) runs in the browser on the returned float32 channels.
 */
export function createApp() {
  const app = express();
  const upload = multer({ dest: path.join(os.tmpdir(), "annoticity-upload"), limits: { fileSize: config.maxUploadBytes } });

  const num = (v, name) => {
    const n = Number(v);
    if (!Number.isFinite(n)) throw Object.assign(new Error(`${name} must be a number`), { status: 400 });
    return n;
  };

  app.get("/api/health", (_req, res) => res.json({ ok: true }));

  app.get("/api/datasets", wrap(async (_req, res) => res.json(await listDatasets())));
  app.get("/api/datasets/:ds/meters", wrap(async (req, res) => res.json(await provider(req.params.ds).meters())));
  app.get("/api/datasets/:ds/meters/:meter/days", wrap(async (req, res) => res.json({ days: await provider(req.params.ds).days(req.params.meter) })));

  app.get("/api/datasets/:ds/meters/:meter/days/:day", wrap(async (req, res) => {
    const file = await dayFile(req.params.ds, req.params.meter, req.params.day);
    res.type(BINARY).set("Cache-Control", "private, max-age=86400").sendFile(file, { dotfiles: "allow" });
  }));

  app.get("/api/datasets/:ds/meters/:meter/waveform", wrap(async (req, res) => {
    const start = num(req.query.start, "start"), stop = num(req.query.stop, "stop");
    if (!(stop > start)) throw Object.assign(new Error("stop must be after start"), { status: 400 });
    if (stop - start > 60) throw Object.assign(new Error("Zoom in to at most 60 seconds to load raw waveforms"), { status: 400 });
    res.type(BINARY).send(await waveform(req.params.ds, req.params.meter, start, stop));
  }));

  app.post("/api/decode", upload.single("file"), wrap(async (req, res) => {
    if (!req.file) throw Object.assign(new Error("No file received"), { status: 400 });
    try {
      res.type(BINARY).send(await decodeMedia(req.file.path, req.file.originalname));
    } finally {
      fs.rm(req.file.path, { force: true });
    }
  }));

  const dist = path.resolve(here, "../../web/dist");
  app.use(express.static(dist));
  app.get(/^\/(?!api\/).*/, (_req, res, next) => res.sendFile(path.join(dist, "index.html"), (e) => e && next()));

  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    const status = err.status ?? (err.code === "LIMIT_FILE_SIZE" ? 413 : 500);
    if (status >= 500) console.error(err);
    res.status(status).json({ error: err.message });
  });
  return app;
}
