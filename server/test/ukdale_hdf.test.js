import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { ukdaleHdfProvider } from "../src/datasets/ukdale_hdf.js";

test("UK-DALE HDF5 reads compressed multi-channel day data", {
  skip: spawnSync("python3", ["-c", "import tables, numpy"]).status !== 0,
}, async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "annoticity-ukdale-"));
  try {
    await fs.writeFile(path.join(dir, "mapping.json"), JSON.stringify({ building1: { 1: "mains" } }));
    await fs.writeFile(path.join(dir, "availability.json"), JSON.stringify({ building1: { 1: [[1577836800, 1577836812]] } }));
    const script = `
import sys, tables, numpy as np
class Row(tables.IsDescription):
    index = tables.Int64Col()
    values_block_0 = tables.Float32Col(shape=(2,))
with tables.open_file(sys.argv[1], "w") as f:
    g = f.create_group("/", "building1")
    g = f.create_group(g, "elec")
    g = f.create_group(g, "meter1")
    t = f.create_table(g, "table", Row, filters=tables.Filters(complevel=5, complib="blosc"))
    t.attrs.values_block_0_kind = [("power", "active"), ("voltage", "")]
    rows = np.zeros(3, dtype=t.dtype)
    rows["index"] = np.array([1577836800, 1577836806, 1577836812], dtype=np.int64) * 1000000000
    rows["values_block_0"] = [[10, 230], [20, 231], [30, 232]]
    t.append(rows)
`;
    const made = spawnSync("python3", ["-c", script, path.join(dir, "ukdale.h5")], { encoding: "utf8" });
    assert.equal(made.status, 0, made.stderr);
    const p = ukdaleHdfProvider(dir, "Europe/London");
    const [meter] = await p.meters();
    assert.equal(meter.id, "h1-c1");
    assert.deepEqual(await p.days(meter.id), ["2020-01-01"]);
    const { header, channels } = await p.day(meter.id, "2020-01-01", meter);
    assert.deepEqual(header.measures, ["p", "v_rms"]);
    assert.equal(header.sampleRate, 1 / 6);
    assert.deepEqual([...channels[0]], [10, 20, 30]);
    assert.deepEqual([...channels[1]], [230, 231, 232]);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
