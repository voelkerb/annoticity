import fs from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { dayFormatter, dayRange, defaultMeasures, toGrid, typicalPeriod } from "./common.js";
import { zonedDayStart } from "../tz.js";
import { httpError } from "../cache.js";

const execFileAsync = promisify(execFile);
const reader = fileURLToPath(new URL("./ukdale_hdf.py", import.meta.url));

export function ukdaleHdfProvider(base, tz) {
  let metadata;
  const load = () => {
    if (!metadata) metadata = Promise.all(["mapping.json", "availability.json"].map(async (name) =>
      JSON.parse(await fs.readFile(path.join(base, name), "utf8")))).catch((e) => { metadata = null; throw e; });
    return metadata;
  };
  const parseMeter = (id) => {
    const m = /^h([1-5])-c(\d+)$/.exec(id);
    if (!m) throw httpError(404, `Unknown meter ${id}`);
    return { building: `building${m[1]}`, house: m[1], meter: m[2] };
  };
  const find = async (id) => {
    const parsed = parseMeter(id);
    const [mapping, availability] = await load();
    const ranges = availability[parsed.building]?.[parsed.meter];
    if (!ranges || !mapping[parsed.building]?.[parsed.meter]) throw httpError(404, `Unknown meter ${id}`);
    return { ...parsed, ranges, label: mapping[parsed.building][parsed.meter] };
  };
  const toDay = dayFormatter(tz);
  return {
    async status() {
      await Promise.all(["ukdale.h5", "mapping.json", "availability.json"].map((name) => fs.access(path.join(base, name))));
      return { available: true };
    },
    async meters() {
      const [mapping, availability] = await load();
      return Object.entries(availability).flatMap(([building, meters]) => {
        const house = /^building([1-5])$/.exec(building)?.[1];
        if (!house) return [];
        return Object.keys(meters).filter((meter) => /^\d+$/.test(meter) && mapping[building]?.[meter]).map((meter) => {
          const label = mapping[building][meter];
          return {
            id: `h${house}-c${meter}`, label, group: `House ${house}`, details: [`meter ${meter}`],
            aggregate: /^(mains|aggregate)$/i.test(label), short: `H${house} M${meter}`, highFreq: false,
          };
        });
      });
    },
    async days(id) {
      const { ranges } = await find(id);
      return [...new Set(ranges.flatMap(([start, stop]) => [...dayRange(toDay(start), toDay(stop))]))].sort();
    },
    async day(id, day, info) {
      const { house, meter } = await find(id);
      const nextDay = new Date(Date.parse(day + "T00:00:00Z") + 86400_000).toISOString().slice(0, 10);
      const start = zonedDayStart(day, tz), stop = zonedDayStart(nextDay, tz);
      const { stdout } = await execFileAsync("python3", [reader, path.join(base, "ukdale.h5"), house, meter, String(start), String(stop)],
        { maxBuffer: 32 * 1024 ** 2, timeout: 120_000 });
      const data = JSON.parse(stdout);
      if (!data.times.length) throw httpError(404, `No data for ${id} on ${day}`);
      const ts = Float64Array.from(data.times);
      const columns = data.columns.map((column) => Float32Array.from(column, (v) => v == null ? NaN : v));
      const period = typicalPeriod(ts);
      const grid = toGrid(ts, columns, period);
      return {
        header: {
          title: info.label, info: `${info.group} · meter ${meter} · ${period} s readings`,
          tz, t0: grid.t0, sampleRate: 1 / period, measures: data.measures,
          meta: { defaultMeasures: defaultMeasures(data.measures) },
        },
        channels: grid.channels,
      };
    },
  };
}
