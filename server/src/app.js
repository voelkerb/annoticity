import express from "express";
import multer from "multer";
import os from "node:os";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "./config.js";
import { DatasetStore } from "./dataset.js";
import { listMeters, listDays, loadFiredDay, loadHighFreq } from "./fired.js";
import { loadUpload } from "./upload.js";
import { detectEvents, DEFAULTS } from "./autolabel.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res)).catch(next);

export function createApp() {
  const app = express();
  const store = new DatasetStore(8);
  const upload = multer({ dest: path.join(os.tmpdir(), "annoticity-upload"), limits: { fileSize: config.maxUploadBytes } });

  app.use(express.json({ limit: "1mb" }));

  const dataset = (req) => {
    const ds = store.get(req.params.id);
    if (!ds) throw Object.assign(new Error("Dataset expired, please load it again."), { status: 404 });
    return ds;
  };
  const num = (v, name) => {
    const n = Number(v);
    if (!Number.isFinite(n)) throw Object.assign(new Error(`${name} must be a number`), { status: 400 });
    return n;
  };

  app.get("/api/health", (_req, res) => res.json({ ok: true }));

  app.get("/api/fired/meters", wrap(async (_req, res) => res.json(await listMeters())));
  app.get("/api/fired/meters/:meter/days", wrap(async (req, res) => res.json({ days: await listDays(req.params.meter) })));

  app.post("/api/datasets/fired", wrap(async (req, res) => {
    const { meter, day } = req.body ?? {};
    const ds = store.add(await loadFiredDay(String(meter), String(day)));
    res.json({ dataset: ds.describe(), warnings: [], embeddedLabels: null });
  }));

  app.post("/api/datasets/upload", upload.single("file"), wrap(async (req, res) => {
    if (!req.file) throw Object.assign(new Error("No file received"), { status: 400 });
    try {
      const { dataset: ds, warnings, embeddedLabels } = await loadUpload(req.file.path, req.file.originalname);
      store.add(ds);
      res.json({ dataset: ds.describe(), warnings, embeddedLabels });
    } finally {
      fs.rm(req.file.path, { force: true });
    }
  }));

  app.get("/api/datasets/:id/data", wrap(async (req, res) => {
    const ds = dataset(req);
    const start = req.query.start === undefined ? ds.start : num(req.query.start, "start");
    const stop = req.query.stop === undefined ? ds.end : num(req.query.stop, "stop");
    const maxPoints = Math.min(5000, Math.max(50, Number(req.query.maxPoints) || 1500));
    const measures = req.query.measures ? String(req.query.measures).split(",") : undefined;
    res.json(ds.query(start, stop, maxPoints, measures));
  }));

  app.get("/api/datasets/:id/waveform", wrap(async (req, res) => {
    const ds = dataset(req);
    if (ds.source !== "fired") throw Object.assign(new Error("Raw waveforms are only available for FIRED"), { status: 400 });
    const start = num(req.query.start, "start"), stop = num(req.query.stop, "stop");
    if (stop - start > 30) throw Object.assign(new Error("Zoom in to at most 30 seconds to load raw waveforms"), { status: 400 });
    const hf = await loadHighFreq(ds, start, stop);
    res.json({ sampleRate: hf.sampleRate, measures: hf.describe().measures, ...hf.query(start, stop, Number(req.query.maxPoints) || 2000) });
  }));

  app.post("/api/datasets/:id/autolabel", wrap(async (req, res) => {
    const ds = dataset(req);
    const params = req.body ?? {};
    const measure = params.measure ?? ds.meta.defaultMeasures?.[0] ?? ds.measureIds[0];
    if (!ds.data[measure]) throw Object.assign(new Error(`Unknown measure ${measure}`), { status: 400 });
    const start = Number.isFinite(params.start) ? params.start : ds.start;
    const stop = Number.isFinite(params.stop) ? params.stop : ds.end;
    const rate = Math.min(ds.sampleRate, Math.max(0.01, Number(params.rate) || 1));

    const t = Date.now();
    const series = ds.regularSeries(measure, rate, start, stop);
    const options = Object.fromEntries(Object.keys(DEFAULTS).filter((k) => Number.isFinite(params[k])).map((k) => [k, params[k]]));
    const { events, states } = detectEvents(series.values, series.rate, options);
    const maxEvents = options.maxEvents ?? DEFAULTS.maxEvents;
    const limited = events.length > maxEvents;
    const labels = events.slice(0, maxEvents).map((e) => ({
      start: series.t0 + e.index / series.rate,
      text: `S${e.toState}`,
      delta: Math.round(e.delta * 10) / 10,
    }));
    res.json({
      labels,
      states: states.map((s) => ({ ...s, mean: Math.round(s.mean * 10) / 10, seconds: Math.round(s.seconds) })),
      rate: series.rate,
      measure,
      ms: Date.now() - t,
      warning: limited ? `Found ${events.length} events, showing the first ${maxEvents}. Increase the threshold.` : events.length === 0 ? "No changes found. Try a lower threshold." : null,
    });
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
