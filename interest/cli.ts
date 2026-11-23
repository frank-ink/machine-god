#!/usr/bin/env bun
// machine-god interests <cmd>   (see README.md)
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { C, mulberry32, score, normKey, type Rng } from "./model.ts";
import { research, BACKENDS, type Backend } from "./research.ts";
import { Store, dataDir, open } from "./store.ts";

const f = (x: number) => x.toFixed(2);
const NO_SEEDS = 'no interests yet. seed some first:\n  machine-god interests seed "topic one" "topic two"';

export function table(s: Store): string {
  const rows = s.sorted();
  if (!rows.length) return NO_SEEDS;
  const lines = [`${"topic".padEnd(36)} score    w    n    b  visits origin      status`];
  for (const i of rows)
    lines.push(`${i.topic.slice(0, 35).padEnd(36)} ${f(score(i)).padStart(5)} ${f(i.w)} ${f(i.n)} ${f(i.b)} ${String(i.visits).padStart(6)} ${i.origin.padEnd(10)} ${i.status}`);
  return lines.join("\n");
}

export function saveNote(dir: string, topic: string, note: string, reward: number): string {
  const nd = join(dir, "notes"); mkdirSync(nd, { recursive: true });
  const slug = normKey(topic).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "topic";
  const p = join(nd, `${new Date().toISOString().slice(0, 10)}-${slug}.md`);
  writeFileSync(p, `# ${topic}\n\nreward: ${reward.toFixed(2)}\n\n${note}\n`, { flag: "a" });
  return p;
}

export async function runRounds(s: Store, backend: Backend, rounds: number, rng: Rng, dir: string, out: (l: string) => void) {
  if (!s.all().length) { out(NO_SEEDS); return 1; }
  for (let k = 1; k <= rounds; k++) {
    const c = s.pick(rng);
    if (!c) { out("no active interests. seed or like a topic to revive one."); return 1; }
    const t = c.item.topic;
    try {
      const res = await research(t, backend);
      saveNote(dir, t, res.note, res.reward);
      const { added } = s.round(t, res.reward, res.subtopics);
      out(`round ${k}: ${t}${c.explored ? " (explore)" : ""} reward=${f(res.reward)}${added.length ? " new: " + added.join(" | ") : ""}`);
    } catch (e) { out(`round ${k}: ${t} failed: ${(e as Error).message}`); return 2; }
  }
  return 0;
}

function why(s: Store, rng: Rng) {
  const c = s.pick(rng);
  if (!c) return NO_SEEDS;
  const L = [`picked: ${c.item.topic}${c.explored ? "  (exploration: best unvisited discovered topic)" : ""}`,
    `choice = softmax(score/${C.TAU}), score = w + ${C.NOVELTY_COEF}*n - b; ${C.EPS * 100}% chance to explore. top ${C.TOP_SHOWN}:`];
  for (const p of c.probs.slice(0, C.TOP_SHOWN)) L.push(`  ${(p.p * 100).toFixed(1).padStart(5)}%  ${p.topic}`);
  return L.join("\n");
}

export async function main(argv: string[]): Promise<number> {
  const [cmd, ...a] = argv;
  const s = new Store(open());
  const rng = process.env.MG_SEED ? mulberry32(Number(process.env.MG_SEED)) : Math.random;
  const flag = (n: string) => { const k = a.indexOf(n); return k >= 0 ? a[k + 1] : undefined; };
  switch (cmd) {
    case "seed": if (!a.length) { console.log('usage: seed "topic" ["topic"...]'); return 1; } s.seed(a); console.log(table(s)); return 0;
    case "list": console.log(table(s)); return 0;
    case "pick": console.log(why(s, rng)); return 0;
    case "run": {
      const b = (flag("--backend") ?? "claude") as Backend;
      if (!BACKENDS.includes(b)) { console.log(`backend must be ${BACKENDS.join("|")}`); return 1; }
      const n = Number(flag("--rounds") ?? 1);
      if (!Number.isInteger(n) || n < 1) { console.log("--rounds must be a positive integer"); return 1; }
      return runRounds(s, b, n, rng, dataDir(), console.log);
    }
    case "like": case "dislike": {
      const t = a.join(" ").trim();
      if (!t) { console.log(`usage: ${cmd} <topic>`); return 1; }
      const u = s.feedback(t, cmd === "like");
      console.log(`${cmd}d "${u!.topic}": w=${f(u!.w)} status=${u!.status}`); return 0;
    }
    case "history": {
      for (const e of s.history(Number(a[0] ?? 30) || 30)) console.log(`${new Date(e.ts).toISOString().slice(0, 19)}  ${e.kind.padEnd(10)} ${e.topic}  ${e.delta}`);
      return 0;
    }
    case "reset": if (!a.includes("--yes")) { console.log("this deletes all interests and history. re-run with: reset --yes"); return 1; } s.reset(); console.log("reset done"); return 0;
    default:
      console.log("usage: machine-god interests <seed|list|pick|run|like|dislike|history|reset> ...\n  run [--backend claude|chatgpt|gemini|ollama|fusion|dry] [--rounds N]   history [N]   reset --yes"); return cmd ? 1 : 0;
  }
}

if (import.meta.main) process.exit(await main(process.argv.slice(2)));
