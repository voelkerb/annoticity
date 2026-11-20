import path from "node:path";
import fs from "node:fs/promises";
import { config } from "../config.js";
import { datFolderProvider } from "./datfolder.js";
import { ukdaleHdfProvider } from "./ukdale_hdf.js";

/** UK-DALE: 6 s appliance active power, 6 s whole-house apparent power and (houses 1, 2, 5) 1 s mains.dat. */
const dat = datFolderProvider({
  id: "ukdale",
  name: "UK-DALE",
  description: "UK Domestic Appliance-Level Electricity · 5 UK houses, 6 s appliance and 1 s mains data",
  url: "https://data.ukedc.rl.ac.uk/browse/edc/efficiency/residential/EnergyConsumption/Domestic/UK-DALE-2017/ReadMe_DALE-2017.html",
  tz: config.ukdale.tz,
  base: config.ukdale.path,
  env: "UKDALE_PATH",
  measureOf: (label) => (/^(aggregate|mains)$/i.test(label) ? "s" : "p"),
  extraMeters({ house, dir, files }) {
    if (!files.includes("mains.dat")) return [];
    return [{
      id: `h${house}-mains`, label: "Mains (1 s, active / apparent / voltage)", group: `House ${house}`,
      details: ["mains.dat"], aggregate: true, short: `H${house} mains`, highFreq: false,
      sources: [{ file: path.join(dir, "mains.dat"), measures: ["p", "s", "v_rms"] }],
    }];
  },
});

const hdf = config.ukdale.path ? ukdaleHdfProvider(config.ukdale.path, config.ukdale.tz) : null;
async function selected() {
  if (!hdf) return dat;
  try { await fs.access(path.join(config.ukdale.path, "ukdale.h5")); return hdf; }
  catch (e) { if (e.code === "ENOENT") return dat; throw e; }
}

export default {
  ...dat,
  status: async () => (await selected()).status(),
  meters: async () => (await selected()).meters(),
  days: async (id) => (await selected()).days(id),
  day: async (id, day, info) => (await selected()).day(id, day, info),
};
