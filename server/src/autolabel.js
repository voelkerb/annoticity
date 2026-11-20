/**
 * Step-change (event) detection for power signals.
 *
 * Pipeline: median filter -> windowed mean comparison (Welch t-statistic, gated by an
 * absolute + relative power threshold) -> peak picking with minimum distance ->
 * edge refinement by two-segment least squares -> steady-state clustering.
 * All window statistics are O(1) via prefix sums, so a full day at 50 Hz takes well under a second.
 */

export const DEFAULTS = {
  thres: 5,          // minimum power step in watts
  linearCoeff: 0.005, // additional threshold relative to the signal level
  pre: 1,            // seconds of signal before the candidate used as reference
  post: 1,           // seconds of signal after the candidate
  minDist: 1,        // minimum seconds between two events
  medianKernel: 5,   // samples
  minScore: 4,       // minimum t-statistic of the mean change
  maxEvents: 2000,
};

export function medianFilter(x, k) {
  if (k < 3 || x.length < k) return Float64Array.from(x);
  const half = k >> 1;
  const out = new Float64Array(x.length);
  const win = [];
  const insert = (v) => {
    let lo = 0, hi = win.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (win[m] < v) lo = m + 1; else hi = m; }
    win.splice(lo, 0, v);
  };
  const remove = (v) => {
    let lo = 0, hi = win.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (win[m] < v) lo = m + 1; else hi = m; }
    win.splice(lo, 1);
  };
  for (let i = 0; i < Math.min(x.length, half); i++) insert(x[i]);
  for (let i = 0; i < x.length; i++) {
    if (i + half < x.length) insert(x[i + half]);
    if (i - half - 1 >= 0) remove(x[i - half - 1]);
    out[i] = win[win.length >> 1];
  }
  return out;
}

function median(values) {
  const a = Float64Array.from(values).sort();
  return a.length ? a[a.length >> 1] : 0;
}

/** Evenly subsample to keep per-segment medians cheap. */
function sample(y, a, b, max = 4000) {
  const len = b - a;
  if (len <= max) return y.subarray(a, b);
  const out = new Float64Array(max);
  for (let i = 0; i < max; i++) out[i] = y[a + Math.floor((i * len) / max)];
  return out;
}

/**
 * @param {ArrayLike<number>} x evenly sampled signal
 * @param {number} sr sample rate in Hz
 * @returns {{events: object[], states: object[]}} event indices refer to samples of `x`
 */
export function detectEvents(x, sr, options = {}) {
  const p = { ...DEFAULTS, ...options };
  const n = x.length;
  const pre = Math.max(2, Math.round(p.pre * sr));
  const post = Math.max(2, Math.round(p.post * sr));
  const minDist = Math.max(1, Math.round(p.minDist * sr));
  if (n < pre + post + 2) return { events: [], states: [] };

  const y = medianFilter(x, Math.min(p.medianKernel, 9) | 1);
  let offset = 0;
  for (let i = 0; i < n; i++) offset += y[i];
  offset /= n;
  const S1 = new Float64Array(n + 1), S2 = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) {
    const v = y[i] - offset;
    S1[i + 1] = S1[i] + v;
    S2[i + 1] = S2[i] + v * v;
  }
  const mean = (a, b) => (S1[b] - S1[a]) / (b - a) + offset;
  const variance = (a, b) => {
    const len = b - a, m = (S1[b] - S1[a]) / len;
    return Math.max(0, (S2[b] - S2[a]) / len - m * m);
  };

  const score = new Float64Array(n);
  const gate = new Uint8Array(n);
  for (let i = pre; i <= n - post; i++) {
    const m0 = mean(i - pre, i), m1 = mean(i, i + post);
    const delta = Math.abs(m1 - m0);
    if (delta < p.thres + p.linearCoeff * Math.max(Math.abs(m0), Math.abs(m1))) continue;
    const v0 = Math.max(variance(i - pre, i), 0.01), v1 = Math.max(variance(i, i + post), 0.01);
    const t = delta / Math.sqrt(v0 / pre + v1 / post);
    if (t < p.minScore) continue;
    score[i] = t;
    gate[i] = 1;
  }

  // One candidate (the strongest) per run of gated samples
  let candidates = [];
  for (let i = 0; i < n; ) {
    if (!gate[i]) { i++; continue; }
    let best = i, j = i;
    while (j < n && gate[j]) { if (score[j] > score[best]) best = j; j++; }
    candidates.push(best);
    i = j;
  }
  // Non-maximum suppression with minimum distance
  candidates.sort((a, b) => score[b] - score[a]);
  const accepted = [];
  for (const c of candidates) {
    if (accepted.every((a) => Math.abs(a - c) >= minDist)) accepted.push(c);
  }
  accepted.sort((a, b) => a - b);

  // Refine each edge: split point with the lowest two-segment squared error
  const sse = (a, b) => (b > a ? S2[b] - S2[a] - ((S1[b] - S1[a]) ** 2) / (b - a) : 0);
  const refined = accepted.map((c, k) => {
    const lo = Math.max(k ? accepted[k - 1] + 1 : 1, c - pre), hi = Math.min(k + 1 < accepted.length ? accepted[k + 1] - 1 : n - 1, c + post);
    const a = Math.max(0, c - 2 * pre), b = Math.min(n, c + 2 * post);
    let best = c, cost = Infinity;
    for (let s = lo; s <= hi; s++) {
      const e = sse(a, s) + sse(s, b);
      if (e < cost) { cost = e; best = s; }
    }
    return best;
  });
  const unique = [...new Set(refined)].sort((a, b) => a - b);

  // Segments between events and their robust steady-state level
  const bounds = [0, ...unique, n];
  let levels = [];
  for (let s = 0; s < bounds.length - 1; s++) {
    const a = bounds[s], b = bounds[s + 1];
    const margin = Math.min(minDist, Math.floor((b - a) / 4));
    levels.push(median(sample(y, a + margin, Math.max(a + margin + 1, b - margin))));
  }

  // Leader clustering on sorted levels, tolerance grows with the level
  const order = levels.map((_, i) => i).sort((a, b) => levels[a] - levels[b]);
  const stateOf = new Array(levels.length);
  const clusters = [];
  for (const i of order) {
    const last = clusters[clusters.length - 1];
    const tol = p.thres + p.linearCoeff * Math.abs(levels[i]);
    if (last && Math.abs(levels[i] - last.sum / last.members.length) <= tol) {
      last.sum += levels[i];
      last.members.push(i);
    } else clusters.push({ sum: levels[i], members: [i] });
    stateOf[i] = clusters.length - 1;
  }

  // An event between two segments of the same state is no real change
  const events = [];
  for (let k = 0; k < unique.length; k++) {
    if (stateOf[k] === stateOf[k + 1]) continue;
    events.push({
      index: unique[k],
      before: levels[k],
      after: levels[k + 1],
      delta: levels[k + 1] - levels[k],
      fromState: stateOf[k],
      toState: stateOf[k + 1],
      score: score[unique[k]] || 0,
    });
  }

  const states = clusters.map((c, id) => ({
    id,
    mean: c.sum / c.members.length,
    segments: c.members.length,
    seconds: c.members.reduce((t, s) => t + (bounds[s + 1] - bounds[s]) / sr, 0),
  }));
  return { events, states };
}
