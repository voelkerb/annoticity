import os from "node:os";
import path from "node:path";

export const config = {
  port: Number(process.env.PORT ?? 8787),
  cacheDir: process.env.ANNOTICITY_CACHE ?? path.join(os.homedir(), ".cache", "annoticity"),
  fired: {
    baseUrl: process.env.FIRED_URL ?? "https://ira.informatik.uni-freiburg.de/~voelkerb/FIRED/",
    // Public credentials documented in the FIRED dataset README
    user: process.env.FIRED_USER ?? "FIRED",
    password: process.env.FIRED_PASSWORD ?? "nobodyGetsFIRED",
    tz: "Europe/Berlin",
  },
  maxUploadBytes: 2 * 1024 ** 3,
};
