import fsp from "node:fs/promises";
import path from "node:path";
import { config } from "../config.js";
import { httpError } from "../cache.js";
import { zonedDayStart } from "../tz.js";
import { defaultMeasures, sortMeasures } from "./common.js";

const { tz, path: base } = config.eco;
const DAY_FILE = /^(\d{4}-\d{2}-\d{2})\.csv$/;

/** Plug appliances as documented by the ECO authors; a labels.json in ECO_PATH overrides them. */
const PLUGS = {
  1: ["Fridge", "Dryer", "Coffee machine", "Kettle", "Washing machine", "PC", "Freezer"],
  2: ["Tablet", "Dishwasher", "Air exhaust", "Fridge", "Entertainment", "Freezer", "Kettle", "Lamp", "Laptops", "Stove", "TV", "Stereo"],
  3: ["Tablet", "Freezer", "Coffee machine", "PC", "Fridge", "Kettle", "Entertainment"],
  4: ["Fridge", "Kitchen appliances", "Lamp", "Stereo and laptop", "Freezer", "Tablet", "Entertainment", "Microwave"],
  5: ["Tablet", "Coffee machine", "Fountain", "Microwave", "Fridge", "Entertainment", "PC", "Kettle"],
  6: ["Lamp", "Laptop", "Router", "Coffee machine", "Entertainment", "Fridge", "Kettle"],
};

/** Smart meter CSV columns (ECO *_sm_csv): total power, power per phase, neutral current, currents, voltages, ... */
const SM_COLUMNS = { p: 0, p_l1: 1, p_l2: 2, p_l3: 3, i_rms_l1: 5, i_rms_l2: 6, i_rms_l3: 7, v_rms_l1: 8, v_rms_l2: 9, v_rms_l3: 10 };

/**
 * Classify a folder holding YYYY-MM-DD.csv files by its path below ECO_PATH. Supports the official
 * layout (01_sm_csv/01, 01_plugs_csv/01/02 or 01_plugs_csv/02) and the flat HH/MM layout (MM 00 = smart meter).
 */
export function classifyEcoFolder(rel) {
  const segs = rel.split(/[\\/]/).filter(Boolean);
  const nums = segs.map((s) => /^(\d+)(?:_|$)/.exec(s)).filter(Boolean).map((m) => +m[1]);
  if (!nums.length) return null;
  const smart = segs.some((s) => /(^|_)sm(_|$)/i.test(s));
  if (smart) return { house: nums[0], plug: 0 };
  if (nums.length < 2) return null;
  return { house: nums.at(-2), plug: nums.at(-1) };
}

async function walk(dir, depth, out) {
  const entries = await fsp.readdir(dir, { withFileTypes: true }).catch(() => []);
  const days = entries.filter((e) => e.isFile() && DAY_FILE.test(e.name)).map((e) => DAY_FILE.exec(e.name)[1]);
  if (days.length) out.push({ dir, days: days.sort() });
  if (depth > 0) for (const e of entries) if (e.isDirectory() && !e.name.startsWith(".")) await walk(path.join(dir, e.name), depth - 1, out);
  return out;
}

let scanned = null;

function scan() {
  if (!scanned || Date.now() - scanned.at > 300e3) {
    scanned = { at: Date.now(), value: scanFolders().catch((e) => { scanned = null; throw e; }) };
  }
  return scanned.value;
}

async function scanFolders() {
  if (!base) throw httpError(503, "Set ECO_PATH in server/.env to the local ECO folder");
  const custom = JSON.parse(await fsp.readFile(path.join(base, "labels.json"), "utf8").catch(() => "{}"));
  const meters = new Map();
  for (const { dir, days } of await walk(base, 4, [])) {
    const c = classifyEcoFolder(path.relative(base, dir));
    if (!c) continue;
    const id = c.plug ? `h${c.house}-p${c.plug}` : `h${c.house}-sm`;
    const name = c.plug ? custom[c.house]?.[c.plug]?.name ?? PLUGS[c.house]?.[c.plug - 1] ?? `Plug ${c.plug}` : "Smart meter (all phases)";
    meters.set(id, {
      id, label: name, group: `House ${c.house}`, aggregate: !c.plug, short: c.plug ? `H${c.house} P${c.plug}` : `H${c.house} SM`,
      details: [custom[c.house]?.[c.plug]?.info].filter(Boolean), highFreq: false, dir, days,
    });
  }
  return [...meters.values()].sort((a, b) => a.group.localeCompare(b.group, undefined, { numeric: true }) || Number(b.aggregate) - Number(a.aggregate) || a.short.localeCompare(b.short, undefined, { numeric: true }));
}

async function find(id) {
  const m = (await scan()).find((x) => x.id === id);
  if (!m) throw httpError(404, `Unknown meter ${id}`);
  return m;
}

/** Parse one ECO day file; -1 marks missing samples. */
export function parseEcoDay(text, smart) {
  const lines = text.split("\n").filter((l) => l.trim());
  const ids = smart ? Object.keys(SM_COLUMNS) : ["p"];
  const out = Object.fromEntries(ids.map((id) => [id, new Float32Array(lines.length)]));
  lines.forEach((line, i) => {
    const cells = line.split(",");
    for (const id of ids) {
      const v = Number(cells[smart ? SM_COLUMNS[id] : 0]);
      out[id][i] = Number.isFinite(v) && v !== -1 ? v : NaN;
    }
  });
  return out;
}

export default {
  id: "eco",
  name: "ECO",
  description: "Electricity Consumption & Occupancy · 6 Swiss households, 1 Hz smart meter and plugs",
  url: "https://www.vs.inf.ethz.ch/res/show.html?what=eco-data",
  tz,
  async status() {
    if (!base) return { available: false, reason: "Set ECO_PATH in server/.env to the local ECO folder" };
    if (!(await scan()).length) return { available: false, reason: `No ECO day files (YYYY-MM-DD.csv) found in ECO_PATH=${base}` };
    return { available: true };
  },
  meters: async () => (await scan()).map(({ dir: _d, days: _days, ...m }) => m),
  days: async (id) => (await find(id)).days,
  async day(id, day, info) {
    const m = await find(id);
    if (!m.days.includes(day)) throw httpError(404, `No data for ${id} on ${day}`);
    const data = parseEcoDay(await fsp.readFile(path.join(m.dir, `${day}.csv`), "utf8"), m.aggregate);
    const measures = sortMeasures(Object.keys(data));
    return {
      header: {
        title: info.label, info: [m.group, ...m.details].join(" · "), tz,
        t0: zonedDayStart(day, tz), sampleRate: 1, measures,
        meta: { defaultMeasures: defaultMeasures(measures) },
      },
      channels: measures.map((x) => data[x]),
    };
  },
};
