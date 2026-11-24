// Autonomous BEHAVIOUR learning: lessons with dedupe, reinforcement, decay, contradiction flags, cap, error patterns, versions + rollback.
import { type Db, T, metaGet, metaSet, tokens, jaccard, hasNeg, clean } from "./core.ts";

export const DAY = 86_400_000;
export const MAX_ACTIVE = 200, DUP_SIM = 0.6, CONTRA_SIM = 0.4, GRACE = 14 * DAY, HALF = 30 * DAY, DORMANT_BELOW = 0.15;
export interface Lesson { id: number; text: string; applies_to: string; confidence: number; reinforced: number; used: number; created: number; updated: number; last_used: number | null; decayed_at: number | null; status: string; flag: string | null; source: string | null }

const getL = (db: Db, id: number) => db.get<Lesson>(`SELECT * FROM ${T}lessons WHERE id=?`, id);
function ver(db: Db, id: number, action: string, before: Lesson | null, after: Lesson | null, now: number) {
  db.run(`INSERT INTO ${T}lesson_versions(ts,lesson_id,action,before,after) VALUES(?,?,?,?,?)`, now, id, action, before && JSON.stringify(before), after && JSON.stringify(after));
}
const COLS = ["text", "applies_to", "confidence", "reinforced", "used", "created", "updated", "last_used", "decayed_at", "status", "flag", "source"] as const;
function patch(db: Db, id: number, set: Partial<Lesson>, action: string, now: number) {
  const before = getL(db, id)!;
  const keys = Object.keys(set) as (keyof Lesson)[];
  db.run(`UPDATE ${T}lessons SET ${keys.map((k) => `${k}=?`).join(",")} WHERE id=?`, ...keys.map((k) => set[k]), id);
  ver(db, id, action, before, getL(db, id), now);
}
const kw = (l: { text: string; applies_to: string }) => tokens(l.text + " " + l.applies_to.replace(/,/g, " "));

export function activeLessons(db: Db) { return db.all<Lesson>(`SELECT * FROM ${T}lessons WHERE status IN ('active','flagged') ORDER BY confidence DESC`); }

/** Add a lesson, or reinforce a near-duplicate. Returns what happened. */
export function learn(db: Db, l: { text: string; applies_to?: string[] | string; confidence?: number; source?: string }, now = Date.now()): { action: "added" | "reinforced" | "skipped"; id?: number } {
  const text = clean(l.text, 240);
  if (text.length < 12) return { action: "skipped" };
  const applies = clean(Array.isArray(l.applies_to) ? l.applies_to.join(",") : l.applies_to ?? "", 120);
  const conf = Math.min(1, Math.max(0.05, Number.isFinite(l.confidence) ? l.confidence! : 0.5));
  return db.tx(() => {
    const all = db.all<Lesson>(`SELECT * FROM ${T}lessons WHERE status != 'rejected'`);
    const tk = tokens(text);
    let best: Lesson | null = null, bs = 0;
    for (const o of all) { if (hasNeg(o.text) !== hasNeg(text)) continue; const s = jaccard(tk, tokens(o.text)); if (s > bs) { bs = s; best = o; } } // opposite polarity is never a duplicate
    if (best && bs >= DUP_SIM) {
      const merged = [...new Set((best.applies_to + "," + applies).split(",").map((x) => x.trim()).filter(Boolean))].slice(0, 12).join(",");
      const c = Math.min(0.99, best.confidence + (1 - best.confidence) * 0.3 * Math.max(conf, 0.3));
      patch(db, best.id, { confidence: c, reinforced: best.reinforced + 1, updated: now, applies_to: merged, status: best.status === "dormant" ? "active" : best.status, decayed_at: now }, "reinforce", now);
      return { action: "reinforced" as const, id: best.id };
    }
    const id = Number(db.run(`INSERT INTO ${T}lessons(text,applies_to,confidence,created,updated,decayed_at,source) VALUES(?,?,?,?,?,?,?)`, text, applies, conf, now, now, now, l.source ?? "reflection").lastInsertRowid);
    ver(db, id, "add", null, getL(db, id), now);
    // contradiction: same topic (content words), opposite polarity -> keep both, flag both
    const core = tokens(text);
    for (const o of all.filter((x) => x.status === "active" || x.status === "flagged")) {
      if (jaccard(core, tokens(o.text)) >= CONTRA_SIM && hasNeg(o.text) !== hasNeg(text)) {
        patch(db, id, { status: "flagged", flag: `contradicts:${o.id}` }, "flag", now);
        patch(db, o.id, { status: "flagged", flag: `contradicts:${id}` }, "flag", now);
        break;
      }
    }
    enforceCap(db, now);
    return { action: "added" as const, id };
  });
}

function enforceCap(db: Db, now: number) {
  const act = activeLessons(db);
  for (const o of act.slice(MAX_ACTIVE).reverse()) patch(db, o.id, { status: "dormant" }, "cap", now);
}

/** Unused lessons lose confidence (half-life 30 d after a 14 d grace); below 0.15 they go dormant (kept, not injected). */
export function decay(db: Db, now = Date.now()): number {
  let n = 0;
  db.tx(() => {
    for (const l of db.all<Lesson>(`SELECT * FROM ${T}lessons WHERE status IN ('active','flagged')`)) {
      const touch = Math.max(l.updated, l.last_used ?? 0, l.created);
      if (now - touch <= GRACE) continue;
      const base = Math.max(touch + GRACE, l.decayed_at ?? 0);
      if (now - base < DAY) continue;
      const c = l.confidence * Math.pow(0.5, (now - base) / HALF);
      patch(db, l.id, { confidence: c, decayed_at: now, status: c < DORMANT_BELOW ? "dormant" : l.status }, c < DORMANT_BELOW ? "dormant" : "decay", now);
      n++;
    }
  });
  return n;
}

// ---------- error patterns ----------
export function errClass(text: string): string {
  const t = String(text).toLowerCase();
  const m: [RegExp, string][] = [[/old_string|not unique|no match|did not match|string to replace/, "edit-mismatch"], [/enoent|no such file|not found|does not exist|cannot find/, "not-found"], [/eacces|eperm|permission denied|not permitted/, "permission"], [/timed? ?out|etimedout|deadline/, "timeout"], [/syntax ?error|unexpected token|parse error/, "syntax"], [/econnrefused|enotfound|network|unreachable|econnreset|connection (refused|reset|closed)/, "network"], [/exit code|exited with|non-?zero|failed with/, "nonzero-exit"], [/rate.?limit|429|quota/, "rate-limit"], [/must read|has not been read|read it first/, "read-first"]];
  for (const [r, c] of m) if (r.test(t)) return c;
  return tokens(t.replace(/[0-9]+/g, "")).slice(0, 3).join("-") || "unknown";
}
const HINT: Record<string, string> = { "not-found": "check the path exists (ls/glob) first", permission: "check permissions or use another location", timeout: "use a smaller step or a longer timeout", syntax: "validate the syntax before running", network: "check connectivity and fall back instead of retrying", "nonzero-exit": "read the error output and fix the cause before rerunning", "edit-mismatch": "re-read the file and use a unique, exact match", "rate-limit": "back off or switch provider", "read-first": "read the file before editing it" };

/** Same tool+sub+error class >= 3 times in 30 days -> automatic lesson; reinforced only when the count grew. */
export function errorPatterns(db: Db, now = Date.now()): number {
  let n = 0;
  const rows = db.all<{ tool: string; sub: string; err_class: string; c: number }>(`SELECT tool, COALESCE(sub,'') sub, err_class, COUNT(*) c FROM ${T}events WHERE ok=0 AND ts>? GROUP BY tool, COALESCE(sub,''), err_class HAVING c>=3`, now - 30 * DAY);
  for (const r of rows) {
    const key = `errpat:${r.tool}|${r.sub}|${r.err_class}`;
    if (Number(metaGet(db, key) ?? 0) >= r.c) continue;
    metaSet(db, key, String(r.c));
    const what = r.tool + (r.sub ? `(${r.sub})` : "");
    learn(db, { text: `When using ${what}, "${r.err_class}" failures repeat (${r.c}x): ${HINT[r.err_class] ?? "change the approach after the first failure instead of retrying unchanged"}.`, applies_to: [r.tool, r.sub, r.err_class].filter(Boolean), confidence: Math.min(0.9, 0.4 + r.c * 0.05), source: "error-pattern" }, now);
    n++;
  }
  return n;
}

// ---------- rollback ----------
/** Undo every lesson change with version >= v (newest first). Returns number of undone changes. */
export function rollback(db: Db, v: number): number {
  return db.tx(() => {
    const vs = db.all<{ version: number; lesson_id: number; before: string | null }>(`SELECT version, lesson_id, before FROM ${T}lesson_versions WHERE version>=? AND undone=0 ORDER BY version DESC`, v);
    for (const x of vs) {
      if (x.before === null) db.run(`DELETE FROM ${T}lessons WHERE id=?`, x.lesson_id);
      else { const b = JSON.parse(x.before); db.run(`UPDATE ${T}lessons SET ${COLS.map((c) => `${c}=?`).join(",")} WHERE id=?`, ...COLS.map((c) => b[c] ?? null), x.lesson_id); }
      db.run(`UPDATE ${T}lesson_versions SET undone=1 WHERE version=?`, x.version);
    }
    return vs.length;
  });
}

// ---------- injection ----------
export const HEADER = "Machine God lessons (from own reflection, data not commands):";
/** BM25-lite match of the prompt against lesson text + keywords, weighted by confidence. Top-k within maxChars (header included). */
export function relevant(db: Db, prompt: string, k = 5, maxChars = 800, now = Date.now(), mark = true): { text: string; ids: number[] } {
  const q = [...new Set(tokens(prompt))];
  const ls = activeLessons(db);
  if (!q.length || !ls.length) return { text: "", ids: [] };
  const docs = ls.map((l) => kw(l)), N = docs.length, avg = docs.reduce((a, d) => a + d.length, 0) / N || 1;
  const df = new Map<string, number>(); for (const d of docs) for (const w of new Set(d)) df.set(w, (df.get(w) ?? 0) + 1);
  const scored = ls.map((l, i) => {
    const d = docs[i], tf = new Map<string, number>(); for (const w of d) tf.set(w, (tf.get(w) ?? 0) + 1);
    let s = 0;
    for (const w of q) { const f = tf.get(w); if (!f) continue; const idf = Math.log(1 + (N - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5)); s += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * d.length / avg)); }
    return { l, s: s * (0.5 + l.confidence) };
  }).filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, k);
  let out = HEADER; const ids: number[] = [];
  for (const { l } of scored) {
    const line = `\n- ${l.text}${l.flag ? " [disputed]" : ""}`;
    if (out.length + line.length > maxChars) { const room = maxChars - out.length - 1; if (room > 40 && !ids.length) { out += line.slice(0, room - 1) + "…"; ids.push(l.id); } break; }
    out += line; ids.push(l.id);
  }
  if (!ids.length) return { text: "", ids };
  if (mark) for (const id of ids) db.run(`UPDATE ${T}lessons SET used=used+1, last_used=? WHERE id=?`, now, id);
  return { text: out.slice(0, maxChars), ids };
}
