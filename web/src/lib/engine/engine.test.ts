import test from "node:test";
import assert from "node:assert/strict";
import { detectEvents } from "./autolabel.ts";
import { Dataset } from "./dataset.ts";
import { parseCsv, parseTime } from "./csv.ts";

function noisy(n: number, fn: (i: number) => number, sigma = 0.3) {
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
  const ds = new Dataset({ title: "t", t0: 0, sampleRate: 10, measures: ["p"], data: { p: data }, source: "upload" });
  const r = ds.query(0, 1000, 100);
  assert.equal(Math.max(...(r.series.p.max as number[])), 500);
  assert.equal(r.t.length, 100);
});

test("query reads block summaries that match a full scan", () => {
  const n = 1_000_003;
  const data = Float32Array.from({ length: n }, (_, i) => Math.sin(i / 997) * 100 + (i % 7));
  data[123457] = NaN;
  const ds = new Dataset({ title: "t", t0: 0, sampleRate: 50, measures: ["p"], data: { p: data }, source: "upload" });
  const r = ds.query(3.3, 19000, 300);
  const i0 = ds.lowerBound(3.3), i1 = ds.lowerBound(19000), len = i1 - i0;
  for (const b of [0, 1, 150, 299]) {
    const a = i0 + Math.floor((b * len) / 300), e = i0 + Math.floor(((b + 1) * len) / 300);
    let mn = Infinity, mx = -Infinity, sum = 0, cnt = 0;
    for (let k = a; k < e; k++) { const v = data[k]; if (v !== v) continue; sum += v; cnt++; mn = Math.min(mn, v); mx = Math.max(mx, v); }
    assert.equal(r.series.p.min![b], mn);
    assert.equal(r.series.p.max![b], mx);
    assert.ok(Math.abs((r.series.p.avg[b] as number) - sum / cnt) < 1e-6);
  }
});

test("parseCsv handles delimiters, date strings and unsorted rows", () => {
  const ds = parseCsv("Date;P;Q\n2021-01-01 00:00:02;3;1\n2021-01-01 00:00:00;1;1\n2021-01-01 00:00:01;2;1\n");
  assert.deepEqual(ds.measureIds, ["p", "q"]);
  assert.deepEqual([...ds.data.p], [1, 2, 3]);
  assert.equal(ds.ts, null);
  assert.equal(ds.sampleRate, 1);
  assert.throws(() => parseCsv("1,2\n3,4\n5,6"), /header/);
});

test("parseTime detects units", () => {
  assert.equal(parseTime("1596405600"), 1596405600);
  assert.equal(parseTime("1596405600000"), 1596405600);
  assert.equal(parseTime("03.08.2020 00:00:00"), 1596412800);
});

test("regularSeries fills gaps of regular data with the previous value", () => {
  const data = Float32Array.of(NaN, 2, 3, NaN, NaN, 6);
  const ds = new Dataset({ title: "t", t0: 0, sampleRate: 1, measures: ["p"], data: { p: data }, source: "upload" });
  assert.deepEqual([...ds.regularSeries("p", 1).values], [2, 2, 3, 3, 3, 6]);
});
