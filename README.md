# Annoticity v2

Browse and label electricity datasets. Version 2 is a rewrite with a **Svelte** frontend and a **Node.js** backend.
The original Django version lives on the `annoticitiy_v1` branch.

- **FIRED dataset**: pick a meter and a day; the server fetches and caches the recording from the university server.
- **Your own data**: drop a CSV (header + time column + numeric columns) or a FIRED-style MKV file.
- Wide, zoomable plot with min/max envelopes (short spikes stay visible), refetching more detail as you zoom; raw 2 kHz V/I at 30 s or less (FIRED).
- Labels: click to add, drag, rename, snap to edge, undo/redo, import/export (CSV, SRT, ASS, JSON).
- Auto-labeling: step detection with refined edges and state clustering.

## Run

Requires Node 20+ and `ffmpeg`/`ffprobe` on the server machine.

```bash
npm run setup   # installs root, server and web dependencies
npm run dev     # API on :8787, UI on http://localhost:5173
```

Production: `npm run build && npm start` serves the built UI and the API on http://localhost:8787.

`npm test` runs the server tests, `npm run check` type-checks the frontend.

## Configuration (environment)

`PORT` (8787), `FIRED_URL`, `FIRED_USER`, `FIRED_PASSWORD`, `VITE_API_URL` (frontend, if the API is hosted elsewhere).

## API

`GET /api/fired/meters` · `GET /api/fired/meters/:meter/days` · `POST /api/datasets/fired` · `POST /api/datasets/upload` ·
`GET /api/datasets/:id/data` · `GET /api/datasets/:id/waveform` · `POST /api/datasets/:id/autolabel`

## Notes

REDD, UK-DALE, BLOND and ECO from v1 are not supported yet. A frontend-only build (e.g. GitHub Pages) would need the university server
to send CORS headers or a small proxy, since it requires Basic auth.
