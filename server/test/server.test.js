import test from "node:test";
import assert from "node:assert/strict";
import { detectEvents } from "../src/autolabel.js";
import { Dataset } from "../src/dataset.js";
import { parseCsv, parseTime } from "../src/upload.js";
import { zonedDayStart } from "../src/tz.js";

function noisy(n, fn, sigma = 0.3) {
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 2 * sigma;
  return Float32Array.from({ length: n }, (_, i) => fn(i) + rnd());
}

test("detectEvents finds step changes close to the true edge and clusters states", () => {
  const x = noisy(600, (i) => (i < 100 ? 0 : i < 300 ? 200 : i < 450 ? 50 : 200));
  const { events, states } = detectEvents(x, 1, { thres: 10 });
  assert.deepEqual(events.map((e) => Math.round(e.index / 10) * 10), [100, 300, 450]);
  events.forEach((e, k) => assert.ok(Math.abs(e.index - [100, 300, 450][k]) <= 2));
  assert.equal(states.length, 3);
  assert.equal(events[2].toState, events[1].fromState);
});

test("detectEvents ignores noise and steps below the threshold", () => {
  const x = noisy(500, (i) => (i < 250 ? 100 : 103), 1);
  assert.equal(detectEvents(x, 1, { thres: 10 }).events.length, 0);
});

test("query keeps short spikes when bucketing", () => {
  const data = new Float32Array(10000).fill(1);
  data[5001] = 500;
  const ds = new Dataset({ title: "t", t0: 0, sampleRate: 10, measures: ["p"], data: { p: data }, source: "test" });
  const r = ds.query(0, 1000, 100);
  assert.equal(Math.max(...r.series.p.max), 500);
  assert.equal(r.t.length, 100);
});

test("parseCsv handles delimiters, date strings and unsorted rows", () => {
  const ds = parseCsv("Date;P;Q\n2021-01-01 00:00:02;3;1\n2021-01-01 00:00:00;1;1\n2021-01-01 00:00:01;2;1\n");
  assert.deepEqual(ds.measureIds, ["p", "q"]);
  assert.deepEqual([...ds.data.p], [1, 2, 3]);
  assert.equal(ds.ts, null);
  assert.equal(ds.sampleRate, 1);
  assert.throws(() => parseCsv("1,2\n3,4\n5,6"), /header/);
});

test("parseTime detects units and zonedDayStart handles DST", () => {
  assert.equal(parseTime("1596405600"), 1596405600);
  assert.equal(parseTime("1596405600000"), 1596405600);
  assert.equal(zonedDayStart("2020-08-03", "Europe/Berlin"), 1596405600);
  assert.equal(zonedDayStart("2020-03-30", "Europe/Berlin") - zonedDayStart("2020-03-29", "Europe/Berlin"), 23 * 3600);
});
