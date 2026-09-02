// Deterministic statistics on the plotted points, computed in the browser for every
// visitor — deliberately not an LLM feature (ideas.md, Kim 2026-09-01). Each language
// is one observation whatever its corpus size; the caveats that come with that
// (family non-independence above all) are spelled out next to the numbers in
// PlotStatistics.vue, not hidden here.

/** Average ranks, 1-based; ties share the mean of the ranks they occupy. */
function ranks(values) {
  const order = values.map((value, index) => [value, index]).sort((a, b) => a[0] - b[0])
  const out = new Array(values.length)
  let i = 0
  while (i < order.length) {
    let j = i
    while (j + 1 < order.length && order[j + 1][0] === order[i][0]) j++
    const shared = (i + j) / 2 + 1
    for (let k = i; k <= j; k++) out[order[k][1]] = shared
    i = j + 1
  }
  return out
}

function pearson(xs, ys) {
  const n = xs.length
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let sxy = 0
  let sxx = 0
  let syy = 0
  for (let i = 0; i < n; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my)
    sxx += (xs[i] - mx) ** 2
    syy += (ys[i] - my) ** 2
  }
  if (!sxx || !syy) return { r: null, sxx, sxy, mx, my }
  return { r: sxy / Math.sqrt(sxx * syy), sxx, sxy, mx, my }
}

// ---------------------------------------------------------------- t-distribution CDF
//
// The two-sided p of a correlation is I_x(df/2, 1/2) with x = df/(df + t²) and
// t = r·√(df/(1−r²)), df = n−2 — the regularised incomplete beta function. Continued
// fraction from Numerical Recipes (betacf); verified against scipy in
// scripts/stats_check.py. Spearman uses the same t approximation scipy defaults to.

function gammaln(z) {
  const g = [
    676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
    12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
  ]
  let x = 0.99999999999980993
  for (let i = 0; i < g.length; i++) x += g[i] / (z + i + 1)
  const t = z + g.length - 0.5
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x) - Math.log(z)
}

function betacf(a, b, x) {
  const FPMIN = 1e-300
  const qab = a + b
  const qap = a + 1
  const qam = a - 1
  let c = 1
  let d = 1 - (qab * x) / qap
  if (Math.abs(d) < FPMIN) d = FPMIN
  d = 1 / d
  let h = d
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2))
    d = 1 + aa * d
    if (Math.abs(d) < FPMIN) d = FPMIN
    c = 1 + aa / c
    if (Math.abs(c) < FPMIN) c = FPMIN
    d = 1 / d
    h *= d * c
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2))
    d = 1 + aa * d
    if (Math.abs(d) < FPMIN) d = FPMIN
    c = 1 + aa / c
    if (Math.abs(c) < FPMIN) c = FPMIN
    d = 1 / d
    const delta = d * c
    h *= delta
    if (Math.abs(delta - 1) < 3e-12) break
  }
  return h
}

function betai(a, b, x) {
  if (x <= 0) return 0
  if (x >= 1) return 1
  const front = Math.exp(
    gammaln(a + b) - gammaln(a) - gammaln(b) + a * Math.log(x) + b * Math.log(1 - x),
  )
  return x < (a + 1) / (a + b + 2)
    ? (front * betacf(a, b, x)) / a
    : 1 - (front * betacf(b, a, 1 - x)) / b
}

/** Two-sided p of a correlation coefficient on n points (t test, df = n−2). */
export function correlationP(r, n) {
  if (r == null || n < 3) return null
  if (Math.abs(r) >= 1) return 0
  const df = n - 2
  const t2 = (r * r * df) / (1 - r * r)
  return betai(df / 2, 0.5, df / (df + t2))
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = sorted.length >> 1
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

function describe(values) {
  const n = values.length
  const mean = values.reduce((a, b) => a + b, 0) / n
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)
  return { mean, median: median(values), sd: Math.sqrt(variance) }
}

/**
 * Median-split quadrant counts, the cheap cloud-shape diagnostic: under independence
 * each corner holds about a quarter of the languages, and a (nearly) empty corner is
 * the signature of a one-way implication rather than a symmetric correlation. Points
 * sitting exactly on a median belong to neither side and are left out of the count.
 */
function quadrants(xs, ys) {
  const mx = median(xs)
  const my = median(ys)
  const counts = { hh: 0, hl: 0, lh: 0, ll: 0 }
  let used = 0
  for (let i = 0; i < xs.length; i++) {
    if (xs[i] === mx || ys[i] === my) continue
    used++
    counts[(xs[i] > mx ? 'h' : 'l') + (ys[i] > my ? 'h' : 'l')]++
  }
  return { mx, my, counts, used }
}

/**
 * One point per family (the group medians), then Pearson over those. Related languages
 * inherit their patterns together (Galton's problem), so the per-language r overstates
 * the evidence; this is the number that survives the objection. Computed only when
 * there are enough distinct families for it to mean anything.
 */
function familyAggregated(points) {
  const groups = new Map()
  for (const point of points) {
    const key = point.label || '?'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(point)
  }
  if (groups.size < 5) return null
  const xs = []
  const ys = []
  for (const members of groups.values()) {
    xs.push(median(members.map((p) => p.x)))
    ys.push(median(members.map((p) => p.y)))
  }
  const r = pearson(xs, ys).r
  if (r == null) return null
  return { r, n: groups.size, p: correlationP(r, groups.size) }
}

/**
 * Everything the statistics dialog shows, from the plotted points of a 2-D scatter.
 * Returns null when there is nothing meaningful to compute (fewer than 3 points, or a
 * degenerate axis where every language has the same value).
 */
export function scatterStats(points) {
  if (points.length < 3) return null
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const n = xs.length

  const { r, sxx, sxy, mx, my } = pearson(xs, ys)
  if (r == null) return null
  const rho = pearson(ranks(xs), ranks(ys)).r

  const slope = sxy / sxx
  return {
    n,
    x: describe(xs),
    y: describe(ys),
    pearson: { r, p: correlationP(r, n) },
    spearman: { rho, p: correlationP(rho, n) },
    family: familyAggregated(points),
    regression: { slope, intercept: my - slope * mx, r2: r * r },
    quadrants: quadrants(xs, ys),
  }
}
