import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { toGrid } from "../src/datasets/common.js";
import { datFolderProvider } from "../src/datasets/datfolder.js";
import { classifyEcoFolder, parseEcoDay } from "../src/datasets/eco.js";
import { rawFileStart } from "../src/datasets/blond.js";
import { zonedDayStart } from "../src/tz.js";

test("toGrid averages bins, holds short gaps and marks long gaps as NaN", () => {
  const ts = Float64Array.of(0, 1, 1.5, 3, 100);
  const { t0, channels: [v] } = toGrid(ts, [Float32Array.of(1, 2, 4, 5, 9)], 1, 10);
  assert.equal(t0, 0);
  assert.equal(v.length, 101);
  assert.deepEqual([...v.subarray(0, 5)], [1, 3, 3, 5, 5]);
  assert.ok(Number.isNaN(v[50]));
  assert.equal(v[100], 9);
});

test("dat folder provider indexes days and loads one local day on a regular grid", async () => {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), "annoticity-redd-"));
  const house = path.join(base, "low_freq", "house_1");
  await fs.mkdir(house, { recursive: true });
  await fs.writeFile(path.join(house, "labels.dat"), "1 mains\n2 kitchen_outlets\n");
  const tz = "America/New_York";
  const d1 = zonedDayStart("2011-04-18", tz), d2 = zonedDayStart("2011-04-19", tz);
  const lines = (from, n, step, v) => Array.from({ length: n }, (_, i) => `${from + i * step} ${v + i}.5`).join("\n");
  await fs.writeFile(path.join(house, "channel_2.dat"), `${lines(d1 + 3600, 10, 3, 0)}\n${lines(d2, 5, 3, 100)}\n`);
  await fs.writeFile(path.join(house, "channel_1.dat"), `${lines(d1, 3, 1, 0)}\n`);

  const p = datFolderProvider({ id: "fixture", name: "Fixture", tz, base, env: "X", measureOf: () => "s" });
  assert.deepEqual(await p.status(), { available: true });
  const meters = await p.meters();
  assert.deepEqual(meters.map((m) => [m.id, m.label, m.aggregate]), [["h1-c1", "mains", true], ["h1-c2", "kitchen outlets", false]]);
  assert.deepEqual(await p.days("h1-c2"), ["2011-04-18", "2011-04-19"]);

  const { header, channels } = await p.day("h1-c2", "2011-04-19", meters[1]);
  assert.equal(header.sampleRate, 1 / 3);
  assert.equal(header.t0, d2);
  assert.deepEqual(header.measures, ["s"]);
  assert.deepEqual([...channels[0]], [100.5, 101.5, 102.5, 103.5, 104.5]);
  await fs.rm(base, { recursive: true, force: true });
});

test("ECO folders are classified for the official and the flat layout", () => {
  assert.deepEqual(classifyEcoFolder("01_sm_csv/01"), { house: 1, plug: 0 });
  assert.deepEqual(classifyEcoFolder("02_plugs_csv/02/05"), { house: 2, plug: 5 });
  assert.deepEqual(classifyEcoFolder("03_plugs_csv/04"), { house: 3, plug: 4 });
  assert.deepEqual(classifyEcoFolder("04/00"), { house: 4, plug: 0 });
  assert.equal(classifyEcoFolder("docs"), null);
});

test("ECO day files map -1 to gaps and smart meter columns to phases", () => {
  assert.deepEqual([...parseEcoDay("12.5\n-1\n3\n", false).p].map((v) => (Number.isNaN(v) ? null : v)), [12.5, null, 3]);
  const sm = parseEcoDay("300,100,120,80,0.1,0.5,0.6,0.4,230,231,229,0,0,0,0,0\n", true);
  assert.equal(sm.p[0], 300);
  assert.equal(sm.p_l2[0], 120);
  assert.equal(sm.i_rms_l3[0], Math.fround(0.4));
  assert.equal(sm.v_rms_l1[0], 230);
});

test("BLOND raw file names carry their local start time", () => {
  assert.equal(rawFileStart("medal-3-2016-10-02T00-15-04.928023T+0200-0000149.hdf5"), Date.parse("2016-10-01T22:15:04Z") / 1000 + 0.928023);
  assert.equal(rawFileStart("summary-2016-10-02-medal-3.hdf5"), null);
});
