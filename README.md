# Annoticity v2

Browse and label electricity datasets. Version 2 is a rewrite with a **Svelte** frontend and a **Node.js** backend.
The original Django version lives on the `annoticitiy_v1` branch.

- **FIRED dataset**: pick a meter and a day; the server fetches the recording from the university server and caches it decoded.
- **Your own data**: drop a CSV (header + time column + numeric columns, parsed in the browser) or a FIRED-style MKV file.
- Wide plot with min/max envelopes (short spikes stay visible). Zooming and panning run locally on the full-resolution data;
  raw 2 kHz V/I at 30 s or less (FIRED).
- Y axis fits the visible data; scroll or drag on the axis (or Alt + scroll on the plot) to zoom and pan it, "Auto Y" or double-click to fit again.
- Labels: click to add, drag, rename, snap to edge, undo/redo, import/export (CSV, SRT, ASS, JSON).
- Auto-labeling: step detection with refined edges and state clustering, running in a Web Worker.

## Architecture

The browser does almost all the work. It holds a loaded day as `Float32Array`s and handles:

- downsampling, using a block min/max/sum pyramid so even full-day views avoid scanning every sample
- auto-labeling
- CSV parsing
- labels

The server (`server/`) only does what a browser cannot:

- download FIRED files, which sit behind Basic auth without CORS
- decode WavPack/Matroska with FFmpeg

It returns the decoded channels in a small binary format: a JSON header followed by float32 channels (see `server/src/binary.js`).

## Run

Requires Node 20+ and `ffmpeg`/`ffprobe` on the server machine.

```bash
npm run setup   # installs root, server and web dependencies
npm run dev     # API on :8787, UI on http://localhost:5173
```

Production: `npm run build && npm start` serves the built UI and the API on http://localhost:8787.

`npm test` runs the server and engine tests, `npm run check` type-checks the frontend.

## Configuration (environment)

`PORT` (8787), `FIRED_URL`, `FIRED_USER`, `FIRED_PASSWORD`, `VITE_API_URL` (frontend, if the API is hosted elsewhere).

## API

- `GET /api/fired/meters`: meters with appliance info.
- `GET /api/fired/meters/:meter/days`: days with data.
- `GET /api/fired/meters/:meter/days/:day`: binary 50 Hz channels of that day (decoded once, then served from the disk cache).
- `GET /api/fired/meters/:meter/waveform?start&stop`: binary raw voltage/current, at most 60 s.
- `POST /api/decode` (multipart `file`): decode an MKV/WAV/FLAC/WavPack upload to binary channels plus embedded SRT labels.

## Notes

REDD, UK-DALE, BLOND and ECO from v1 are not supported yet. A frontend-only build (e.g. GitHub Pages) would need the university server
to send CORS headers or a small proxy, since it requires Basic auth.
