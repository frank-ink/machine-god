// Research backends: claude (local CLI), chatgpt (bridge), dry (deterministic fake).
import { tmpdir } from "node:os";
export interface Round { note: string; reward: number; subtopics: string[] }
export type Backend = "claude" | "chatgpt" | "dry";

export const buildPrompt = (topic: string) =>
  `Write a short research note (max 250 words) on this topic: ${JSON.stringify(topic)}.\n` +
  `Answer from your own knowledge, no tools. After the note, end with exactly one JSON block:\n` +
  `{"reward": <0..1, honest: how surprising/useful was this topic to research>, "subtopics": [<max 3 short follow-up topics>]}`;

const clean = (s: string) => s.replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);

/** Robust parse: finds the last {...} containing "reward". Malformed -> reward 0.3, no subtopics. */
export function parseResult(text: string): Round {
  const fail = { note: text.trim(), reward: 0.3, subtopics: [] as string[] };
  const at = text.lastIndexOf('"reward"');
  if (at < 0) return fail;
  const start = text.lastIndexOf("{", at);
  if (start < 0) return fail;
  let depth = 0, end = -1;
  for (let k = start; k < text.length; k++) {
    if (text[k] === "{") depth++;
    else if (text[k] === "}" && --depth === 0) { end = k; break; }
  }
  if (end < 0) return fail;
  try {
    const j = JSON.parse(text.slice(start, end + 1));
    const r = Number(j.reward);
    if (!Number.isFinite(r)) return fail;
    const subs = (Array.isArray(j.subtopics) ? j.subtopics : [])
      .filter((s: unknown) => typeof s === "string").map(clean).filter(Boolean).slice(0, 3);
    const note = (text.slice(0, start) + text.slice(end + 1)).replace(/```(json)?/g, "").trim();
    return { note, reward: Math.min(1, Math.max(0, r)), subtopics: subs };
  } catch { return fail; }
}

const SUFFIX = ["origins", "limits", "applications", "critiques", "history", "open problems", "tools", "analogies"];
function fnv(s: string) { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h; }

/** Deterministic fake: reward and subtopics depend only on the topic string. */
export function dry(topic: string): Round {
  const base = SUFFIX.reduce((t, s) => (t.endsWith(" " + s) ? t.slice(0, -s.length - 1) : t), topic);
  const h = fnv(topic);
  return {
    note: `[dry] simulated note on ${topic}.`,
    reward: (h % 100) / 100,
    subtopics: [`${base} ${SUFFIX[(h >>> 3) % 8]}`, `${base} ${SUFFIX[(h >>> 7) % 8]}`],
  };
}

async function claude(prompt: string): Promise<string> {
  const p = Bun.spawn(["claude", "-p", "--output-format", "json", prompt], {
    stdin: "ignore", stdout: "pipe", stderr: "pipe", cwd: tmpdir(), timeout: 120_000,
  });
  const [out, code] = await Promise.all([new Response(p.stdout).text(), p.exited]);
  let j: any = null;
  try { j = JSON.parse(out); } catch {}
  if (code !== 0 || !j || j.is_error) throw new Error(`claude failed (exit ${code}): ${String(j?.result ?? "no output").slice(0, 120)}`);
  return String(j.result ?? "");
}

export async function research(topic: string, backend: Backend): Promise<Round> {
  if (backend === "dry") return dry(topic);
  const prompt = buildPrompt(topic); // only the topic leaves the machine
  if (backend === "claude") {
    if (!Bun.which("claude")) throw new Error("`claude` not on PATH");
    return parseResult(await claude(prompt));
  }
  return parseResult(await (await import("./backend_chatgpt.ts")).send(prompt));
}
