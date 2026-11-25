// GRID engine: a small, deterministic salience engine (JavaScript port of the "GRID v2" core idea: divisive normalisation + fatigue + abstain).
// It does NOT think. For every request it takes ten measurable signals, compares each against its own slowly adapting baseline and noise,
// and reports which cell changed most (the "winner") or ABSTAIN when nothing changed beyond noise. Machine God records the frame with the turn
// so you can see which requests were unusual compared with your own history. No clock, no I/O: state in, state out (stored in unified.db meta).
export const CELLS = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"];
const CLAMP_MIN = -1.0;
const CLAMP_MAX = 4.0;
const DEFAULT = {
  alpha_base: 0.1, alpha_burst: 0.6, burst_k: 3.0, alpha_sigma: 0.02, z_floor: 0.03, offset_weight: 0.4, zabs: 4.0,
  goal_bias: 0.15, lam: 0.7, gain: 1.0, fatigue_alpha: 0.5, recency_rate: 0.1,
};
// meaning of the cells in Machine God (measured, not guessed): the rest stay 0 until something honest can feed them
export const CELL_MEANING = { G6: "code", G7: "goal", G8: "memory", G9: "novelty", G10: "length" };

const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
const zero = () => Object.fromEntries(CELLS.map((c) => [c, 0]));

export class Engine {
  constructor(cfg = {}) {
    this.c = { ...DEFAULT, ...cfg };
    this.init = false;
    this.base = zero();
    this.sigma = zero();
    this.cells = zero();
    this.recency = zero();
    this.steps = 0;
  }
  toJSON() {
    return { init: this.init, base: this.base, sigma: this.sigma, cells: this.cells, recency: this.recency, steps: this.steps };
  }
  static fromJSON(d, cfg) {
    const e = new Engine(cfg);
    if (d && typeof d === "object") {
      for (const k of ["base", "sigma", "cells", "recency"]) if (d[k] && typeof d[k] === "object") e[k] = { ...zero(), ...d[k] };
      e.init = !!d.init;
      e.steps = Number(d.steps) || 0;
    }
    return e;
  }
  /** signals: {G1..G10: 0..1} or null (autonomous tick: decay only). -> { winner, abstain, observed, max_score, thresh, score } */
  step(signals) {
    const c = this.c;
    this.steps++;
    const out = { winner: "", max_score: 0, thresh: 0, score: {}, abstain: false, observed: false };
    if (signals === null) {
      for (const i of CELLS) {
        this.cells[i] = clamp(c.lam * this.cells[i], CLAMP_MIN, CLAMP_MAX);
        this.recency[i] *= 1 - c.recency_rate;
      }
      out.abstain = true;
      return out;
    }
    out.observed = true;
    if (!this.init) {
      for (const i of CELLS) this.base[i] = clamp(signals[i] ?? 0, 0, 1);
      this.init = true;
      out.abstain = true; // the first observation only sets the baseline
      return out;
    }
    const x = Object.fromEntries(CELLS.map((i) => [i, clamp(signals[i] ?? 0, 0, 1)]));
    let best = "";
    let bestScore = 0;
    const drive = {};
    for (const i of CELLS) {
      const d = x[i] - this.base[i];
      const ad = Math.abs(d);
      const w = d < 0 ? c.offset_weight : 1.0;
      const sg = this.sigma[i] + c.z_floor;
      const sc = ((w * ad) / sg) * (1 - c.fatigue_alpha * this.recency[i]);
      out.score[i] = sc;
      drive[i] = w * ad;
      if (best === "" || sc > bestScore) {
        best = i;
        bestScore = sc;
      }
      const a = ad > c.burst_k * sg ? c.alpha_burst : c.alpha_base;
      this.base[i] += a * d;
      const capped = Math.min(ad, c.burst_k * sg);
      this.sigma[i] += c.alpha_sigma * (capped - this.sigma[i]);
    }
    const thresh = c.zabs * (1 - c.goal_bias * x.G7);
    out.max_score = bestScore;
    out.thresh = thresh;
    if (bestScore >= thresh) out.winner = best;
    else out.abstain = true;
    for (const i of CELLS) {
      this.cells[i] = clamp(c.lam * this.cells[i] + c.gain * drive[i], CLAMP_MIN, CLAMP_MAX);
      this.recency[i] += c.recency_rate * ((i === out.winner ? 1 : 0) - this.recency[i]);
    }
    return out;
  }
}

const CODE_CUE = /```|\b(def|class|import|function|const|git|pip|bash|python|sqlite|traceback|error|bug|compile|install|script|stack ?trace)\b|[\/~][\w.-]+\/[\w.-]+/i;
const WORD = /[\p{L}\p{N}_]{3,}/gu;
export const words = (t) => new Set((String(t || "").toLowerCase().match(WORD) || []));

/** Measurable signals for one request. recentPrompts: earlier user prompts; memoryHits: how many stored memories matched (0..). */
export function signalsFor(prompt, { recentPrompts = [], memoryHits = 0 } = {}) {
  const s = zero();
  const text = String(prompt || "");
  s.G10 = Math.min(1, text.length / 4 / 3000);
  s.G6 = CODE_CUE.test(text) ? 1 : 0;
  s.G7 = 1; // a request is always a goal
  s.G8 = Math.min(1, memoryHits / 5);
  const w = words(text);
  if (w.size && recentPrompts.length) {
    let maxSim = 0;
    for (const p of recentPrompts) {
      const v = words(p);
      const union = new Set([...w, ...v]).size;
      if (union) {
        let inter = 0;
        for (const t of w) if (v.has(t)) inter++;
        maxSim = Math.max(maxSim, inter / union);
      }
    }
    s.G9 = 1 - maxSim;
  } else if (w.size) s.G9 = 1;
  return s;
}
