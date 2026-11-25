// Pure interest math. No I/O, no clock, no randomness except the injected rng.
const DAY = 86_400_000;
export const C = {
  T_W_MS: 14 * DAY, // weight half-life-ish time constant
  T_B_MS: 2 * DAY, // boredom time constant
  DORMANT_W: 0.05, // w below this -> dormant
  NOVELTY_COEF: 0.3,
  TAU: 0.25, // softmax temperature
  EPS: 0.15, // exploration probability
  ALPHA: 0.3, // reward learning rate
  BORED_STEP: 0.35,
  NOVELTY_DECAY: 0.6,
  DISC_W0: 0.15,
  DISC_W_R: 0.2,
  SEED_W: 0.5,
  SEED_N: 0.5,
  CAP: 40, // max active interests
  TOP_SHOWN: 5,
} as const;

export type Origin = "seed" | "discovered" | "user";
export type Status = "active" | "dormant";
export interface Interest {
  key: string; topic: string; w: number; n: number; b: number;
  visits: number; last_visit: number; origin: Origin; status: Status;
  ts: number; // last time decay was applied (ms)
}
export type Rng = () => number;

export const clamp = (x: number) => Math.min(1, Math.max(0, x));
export const normKey = (s: string) => s.toLowerCase().trim().replace(/\s+/g, " ");
export const score = (i: Interest) => i.w + C.NOVELTY_COEF * i.n - i.b;

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Exponential time decay of w and b since i.ts. Active interests under the floor go dormant. */
export function decay(i: Interest, now: number): Interest {
  const dt = Math.max(0, now - i.ts);
  const w = i.w * Math.exp(-dt / C.T_W_MS);
  const b = i.b * Math.exp(-dt / C.T_B_MS);
  const status: Status = i.status === "active" && w < C.DORMANT_W ? "dormant" : i.status;
  return { ...i, w, b, status, ts: now };
}

export function softmax(scores: number[], tau = C.TAU): number[] {
  const m = Math.max(...scores);
  const e = scores.map((s) => Math.exp((s - m) / tau));
  const z = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / z);
}

export interface Choice { item: Interest; explored: boolean; probs: { key: string; topic: string; p: number }[] }

/** Pick among active interests: softmax(score/tau), or with prob eps the best unvisited discovered one. */
export function choose(items: Interest[], rng: Rng, eps = C.EPS, tau = C.TAU): Choice | null {
  const act = items.filter((i) => i.status === "active");
  if (!act.length) return null;
  const p = softmax(act.map(score), tau);
  const probs = act.map((i, k) => ({ key: i.key, topic: i.topic, p: p[k] })).sort((a, b) => b.p - a.p);
  const cands = act.filter((i) => i.origin === "discovered" && i.visits === 0);
  if (cands.length && rng() < eps) {
    const best = cands.reduce((a, b) => (score(b) > score(a) ? b : a));
    return { item: best, explored: true, probs };
  }
  let r = rng(), k = 0;
  for (; k < act.length - 1; k++) { r -= p[k]; if (r < 0) break; }
  return { item: act[k], explored: false, probs };
}

/** Research round (or like/dislike) with reward r in [0,1]. */
export function applyReward(i: Interest, r: number, now: number): Interest {
  r = clamp(r);
  const w = clamp(i.w + C.ALPHA * (r - i.w));
  return {
    ...i, w,
    b: clamp(i.b + C.BORED_STEP * (1 - i.b)),
    n: i.n * C.NOVELTY_DECAY,
    visits: i.visits + 1, last_visit: now,
    status: w < C.DORMANT_W ? "dormant" : "active",
  };
}

export function newInterest(topic: string, origin: Origin, now: number, w: number, n: number): Interest {
  return { key: normKey(topic), topic: topic.trim().replace(/\s+/g, " "), w, n, b: 0, visits: 0, last_visit: 0, origin, status: "active", ts: now };
}
export const discovered = (topic: string, r: number, now: number) =>
  newInterest(topic, "discovered", now, C.DISC_W0 + C.DISC_W_R * clamp(r), 1);

/** Keys of lowest-scored active interests that exceed the cap. */
export function overCap(items: Interest[], cap = C.CAP): string[] {
  const act = items.filter((i) => i.status === "active").sort((a, b) => score(a) - score(b));
  return act.slice(0, Math.max(0, act.length - cap)).map((i) => i.key);
}
