#!/usr/bin/env bash
# Builds a self-contained Annoticity bundle (built UI + server with production dependencies) as a zip.
# Usage: scripts/package-offline.sh [version]   ->  release/annoticity-<version>-offline.zip
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
version="${1:-v$(node -p "require('$root/package.json').version")}"
name="annoticity-$version-offline"
out="$root/release"
stage="$out/$name"

rm -rf "$stage" "$out/$name.zip"
mkdir -p "$stage/server" "$stage/web"

npm --prefix "$root/web" run build >/dev/null
cp -R "$root/web/dist" "$stage/web/dist"
cp -R "$root/server/src" "$stage/server/src"
cp "$root/server/package.json" "$root/server/package-lock.json" "$root/server/.env.example" "$stage/server/"
npm --prefix "$stage/server" ci --omit=dev --no-audit --no-fund >/dev/null
cp "$root/LICENSE" "$stage/"

cat > "$stage/start.sh" <<'SH'
#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v node >/dev/null || { echo "Node.js 20+ is required: https://nodejs.org"; exit 1; }
port="${PORT:-8787}"
( sleep 1.5; (open "http://localhost:$port" || xdg-open "http://localhost:$port") >/dev/null 2>&1 ) &
PORT="$port" node server/src/index.js
SH
cp "$stage/start.sh" "$stage/start.command"
chmod +x "$stage/start.sh" "$stage/start.command"

cat > "$stage/start.bat" <<'BAT'
@echo off
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js 20+ is required: https://nodejs.org & pause & exit /b 1)
if "%PORT%"=="" set PORT=8787
start "" http://localhost:%PORT%
node server\src\index.js
BAT

cat > "$stage/README.txt" <<TXT
Annoticity $version (offline bundle)

Requirements
  - Node.js 20 or newer (https://nodejs.org)
  - ffmpeg/ffprobe on the PATH, only for FIRED data and MKV/WAV/FLAC uploads
  - Python 3, PyTables and NumPy, only for UK-DALE ukdale.h5 files

Start
  macOS:   double-click start.command (first time: right-click > Open)
  Linux:   ./start.sh
  Windows: double-click start.bat
  Then open http://localhost:8787 (opened automatically).

Works without internet: your own CSV/MKV files and local REDD, UK-DALE and ECO copies.
FIRED and BLOND use local copies when configured and download missing data if needed.

Local datasets: copy server/.env.example to server/.env and set the dataset paths.
Decoded days are cached in ~/.cache/annoticity (change with ANNOTICITY_CACHE).

Source and docs: https://github.com/voelkerb/annoticity
TXT

(cd "$out" && rm -f "$name.zip" && zip -qry "$name.zip" "$name")
rm -rf "$stage"
echo "$out/$name.zip"
