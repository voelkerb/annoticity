import path from "node:path";
import { config } from "../config.js";
import { datFolderProvider } from "./datfolder.js";

/** REDD low_freq: mains legs at 1 s and circuits at ~3 s, all apparent power. */
export default datFolderProvider({
  id: "redd",
  name: "REDD",
  description: "Reference Energy Disaggregation Data Set · 6 US houses, mains legs and circuits (low_freq)",
  url: "http://redd.csail.mit.edu",
  tz: config.redd.tz,
  base: config.redd.path,
  env: "REDD_PATH",
  measureOf: () => "s",
  extraMeters({ house, dir, meters }) {
    const mains = meters.filter((m) => m.aggregate);
    if (mains.length < 2) return [];
    return [{
      id: `h${house}-mains`, label: "Mains (both legs)", group: `House ${house}`,
      details: mains.map((m) => m.details[0]), aggregate: true, short: `H${house} mains`, highFreq: false,
      sources: mains.map((m, i) => ({ file: path.join(dir, path.basename(m.sources[0].file)), measures: [`s_l${i + 1}`] })),
    }];
  },
});
