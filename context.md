# Annoticity – working context

Status notes for continuing the work (last updated 2026-11-20). See [README.md](README.md) for usage.

## History

- **v1**: the original Django + Highcharts app. Preserved on branch `annoticitiy_v1` and in release `v1.0.0`
  (source zip attached).
- **v2**: a rewrite with a Svelte 5 + uPlot frontend (`web/`) and a thin Node/Express backend (`server/`). It is on
  `master` and in release `v2.0.0` (offline bundle attached).

## Architecture (v2)

The browser does the heavy lifting:

- A loaded day is held as `Float32Array`s with a block min/max/sum pyramid, so zooming and panning never re-fetch.
- Auto-labeling runs in a Web Worker (`web/src/lib/engine/`).
- CSV parsing, labels, undo/redo and import/export also run in the browser.

The server only does what a browser cannot:

- Fetch FIRED (Basic auth, no CORS) and BLOND (FTP, HDF5 via h5wasm).
- Read local dataset folders (REDD, UK-DALE, ECO).
- Decode WavPack/MKV with ffmpeg.

Each dataset is a provider in `server/src/datasets/` (registry in `index.js`). Decoded days are cached in
`~/.cache/annoticity`. Responses use a binary format: a JSON header followed by float32 channels (`server/src/binary.js`).

| Dataset | Source | Status |
| --- | --- | --- |
| FIRED | university HTTP server | working, raw V/I |
| BLOND-50 / BLOND-250 | TUM FTP `dataserv.ub.tum.de` | working, 1 Hz summaries plus raw V/I (≤12.5 kHz) |
| REDD | local `REDD_PATH` | implemented; tested on synthetic fixtures only |
| UK-DALE (.dat release) | local `UKDALE_PATH` | implemented; tested on synthetic fixtures only |
| ECO | local `ECO_PATH` | implemented; plug names are a best guess, override with `labels.json` |

## Features done in v2

- Top-down layout with a wide plot and min/max envelopes.
- Y axis: auto-fit, zoom and pan.
- Raw-waveform mode at ≤30 s.
- Themes:
  - dark: `#EFFF4F` on `#10131A`;
  - light: deep berry `#3E1B45`, white plot.
- Labels:
  - add by clicking, drag the flags, snap to edge (snapping skips existing labels and keeps a minimum distance);
  - undo/redo;
  - CSV/SRT/ASS/JSON import and export;
  - "New labels" preset text with a list of used names.
- Renaming a label offers to rename the other labels with the same text: earlier ones, later ones or all (as in v1).
  Names given to auto-label states (`S1`, …) are remembered per meter.
- Dataset picker with tabs (Datasets / Your data) and grouped meters.
- FIRED raw current is converted from mA to A on the server, matching BLOND.

## Screenshots and marketing

- README screenshots are in `docu/figures/v2-*.png`, taken with headless Chrome at 1440×900 (2×) against the dev server.
  - Labels: FIRED Fridge (PM 09), 2020-08-03.
  - Auto-label: FIRED smart meter, light theme.
  - Waveform: FIRED TV (PM 23) switching on at 20:46.
  - BLOND: CLEAR mains, 2016-10-04, light theme.
- App page: https://voelkerb.github.io/apps/annoticity/ (repo `voelkerb/apps`, folder `annoticity/`). It has the icon, framed
  screenshots and features; "Download" links to the latest release.
- Card on https://voelkerb.github.io/ (apps section) and on https://voelkerb.github.io/apps/.
- The README links to the hosted app; the app page can also link to it.

## Run and verify

```bash
npm run setup && npm run dev      # API :8787, UI http://localhost:5173
npm test && npm run check         # server + engine tests, svelte-check
scripts/package-offline.sh v2.x.y # release/annoticity-v2.x.y-offline.zip
```

## Deployment

For a home server, see the public-hosting precautions in [README.md](README.md#hosting-on-a-home-server).
`ANNOTICITY_PUBLIC=true` binds to loopback by default and limits requests, concurrent work and media uploads.
The Docker image listens inside the container on port 8000; Compose publishes it only on host loopback, mounts
the datasets read-only and uses ephemeral, one-minute cache files. All configured datasets are publicly readable.
It still requires a properly configured HTTPS reverse proxy and host isolation.

Other hosting options, e.g. GitHub Pages:

1. **Frontend-only (GitHub Pages)**
   - "Your data" CSV works fully in the browser.
   - MKV uploads would need ffmpeg.wasm.
   - FIRED needs CORS plus auth, so it requires a proxy or a CORS header on the university server.
   - BLOND is FTP-only, so it cannot be fetched from a browser and needs a proxy.
2. **Pages frontend + small hosted API** (Render, Fly.io, a university VM, …)
   - Set `VITE_API_URL` at build time.
   - The API needs ffmpeg and a disk cache.
3. **Single Node host** serving both (`npm run build && npm start`): simplest, the same as the offline bundle.

To prepare: a GitHub Actions workflow for build, test and the Pages deploy; a `base` path in the Vite config for
`/annoticity/`; an API URL switch in the UI when the API is unreachable.

## Conventions

- Commits carry no AI attribution or co-author trailers.
- Don't push, merge or deploy without approval.
