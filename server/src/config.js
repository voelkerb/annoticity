import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Local dataset paths and overrides can live in server/.env (or the repository root .env)
const here = path.dirname(fileURLToPath(import.meta.url));
for (const file of [path.resolve(here, "../.env"), path.resolve(here, "../../.env")]) {
  try { process.loadEnvFile(file); } catch { /* optional */ }
}

const expand = (p) => (p ? path.resolve(p.replace(/^~(?=$|\/)/, os.homedir())) : null);

export const config = {
  port: Number(process.env.PORT ?? 8787),
  host: process.env.ANNOTICITY_HOST,
  publicMode: process.env.ANNOTICITY_PUBLIC === "true",
  trustProxy: process.env.ANNOTICITY_TRUST_PROXY === "true",
  cacheTtlMs: process.env.ANNOTICITY_PUBLIC === "true" ? 60_000 : 0,
  cacheDir: expand(process.env.ANNOTICITY_CACHE) ?? path.join(os.homedir(), ".cache", "annoticity"),
  fired: {
    baseUrl: process.env.FIRED_URL ?? "https://ira.informatik.uni-freiburg.de/~voelkerb/FIRED/",
    // Public credentials documented in the FIRED dataset README
    user: process.env.FIRED_USER ?? "FIRED",
    password: process.env.FIRED_PASSWORD ?? "nobodyGetsFIRED",
    path: expand(process.env.FIRED_PATH),
    tz: "Europe/Berlin",
  },
  blond: {
    // Public anonymous-style account published with BLOND on mediaTUM
    host: process.env.BLOND_FTP_HOST ?? "dataserv.ub.tum.de",
    user: process.env.BLOND_FTP_USER ?? "m1375836",
    password: process.env.BLOND_FTP_PASSWORD ?? "m1375836",
    root: "/FD_Share_Kriechbaumer/BLOND/",
    path: expand(process.env.BLOND_PATH),
    tz: "Europe/Berlin",
  },
  redd: { path: expand(process.env.REDD_PATH), tz: "America/New_York" },
  ukdale: { path: expand(process.env.UKDALE_PATH), tz: "Europe/London" },
  eco: { path: expand(process.env.ECO_PATH), tz: "Europe/Zurich" },
  maxUploadBytes: 2 * 1024 ** 3,
  publicMaxUploadBytes: 128 * 1024 ** 2,
};
