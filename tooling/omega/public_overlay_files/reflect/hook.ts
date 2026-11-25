// Claude Code hook entry. `bun hook.ts <post|stop|prompt>`; payload JSON on stdin. Fast, local only, NEVER fails or blocks the turn (exit 0 always).
// Registered for: PostToolUse + PostToolUseFailure (post), Stop (stop), UserPromptSubmit (prompt).
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { type Db, T, openDb, dbPath, getState, dataDir, metaGet, metaSet, clean } from "./core.ts";
import { errClass, relevant } from "./learn.ts";

type P = Record<string, any>;
export interface Opts { now?: number; spawnFn?: (dir: string) => void; everyMin?: number; env?: Record<string, string | undefined> }

export function onTool(db: Db, p: P, now = Date.now()) {
  const tool = String(p.tool_name ?? "");
  if (!tool) return;
  const r = p.tool_response;
  const errTxt = p.error ?? (r && typeof r === "object" ? r.error ?? (r.is_error || r.interrupted || r.success === false || (typeof r.exit_code === "number" && r.exit_code !== 0) ? r.stderr ?? r.content ?? "failed" : null) : null);
  const failed = p.hook_event_name === "PostToolUseFailure" || errTxt != null || (r && typeof r === "object" && r.is_error === true);
  const cmd = tool === "Bash" && typeof p.tool_input?.command === "string" ? (p.tool_input.command.trim().split(/\s+/)[0] ?? "").replace(/^.*\//, "").slice(0, 24) : "";
  const e = failed ? clean(typeof errTxt === "string" ? errTxt : JSON.stringify(errTxt ?? ""), 160) : "";
  db.run(`INSERT INTO ${T}events(ts,session,tool,sub,ok,err_class,err,dur_ms) VALUES(?,?,?,?,?,?,?,?)`, now, String(p.session_id ?? ""), tool, cmd, failed ? 0 : 1, failed ? errClass(e) : null, e || null, Number.isFinite(p.duration_ms) ? Math.round(p.duration_ms) : null);
}

const textOf = (c: any): string => (typeof c === "string" ? c : Array.isArray(c) ? c.filter((b) => b?.type === "text").map((b) => b.text).join("\n") : "");
/** Last real user prompt + final assistant text from the tail of the transcript JSONL. */
export function readTranscript(file: string): { prompt: string; answer: string } {
  let buf = "";
  const fd = fs.openSync(file, "r");
  try {
    const size = fs.fstatSync(fd).size, n = Math.min(size, 400_000), b = Buffer.alloc(n);
    fs.readSync(fd, b, 0, n, size - n); buf = b.toString("utf8");
    if (size > n) buf = buf.slice(buf.indexOf("\n") + 1);
  } finally { fs.closeSync(fd); }
  let prompt = "", answer = "";
  for (const line of buf.split("\n")) {
    let j: any; try { j = JSON.parse(line); } catch { continue; }
    const role = j.message?.role ?? j.type;
    if (j.isMeta || j.isSidechain) continue;
    const t = textOf(j.message?.content).trim();
    if (role === "user" && t && !/^<(system-reminder|command-|local-command)/.test(t)) { prompt = t; answer = ""; }
    else if (role === "assistant" && t && prompt) answer = t; // last assistant text after the last user prompt
  }
  return { prompt, answer };
}

export function onStop(db: Db, p: P, dir: string, o: Opts = {}) {
  const now = o.now ?? Date.now();
  if (p.stop_hook_active) return;
  let prompt = "", answer = "";
  if (p.transcript_path) { try { ({ prompt, answer } = readTranscript(p.transcript_path)); } catch {} }
  if (!prompt && !answer) return;
  const session = String(p.session_id ?? ""), pr = clean(prompt, 600), an = clean(answer, 800);
  if (db.get(`SELECT 1 FROM ${T}tasks WHERE session=? AND prompt=? AND answer=?`, session, pr, an)) return; // duplicate Stop
  db.tx(() => {
    const s = db.get<{ n: number; e: number }>(`SELECT COUNT(*) n, COALESCE(SUM(1-ok),0) e FROM ${T}events WHERE session=? AND task_id IS NULL`, session)!;
    const id = Number(db.run(`INSERT INTO ${T}tasks(ts,session,prompt,answer,tools_n,errs_n) VALUES(?,?,?,?,?,?)`, now, session, pr, an, s.n, s.e).lastInsertRowid);
    db.run(`UPDATE ${T}events SET task_id=? WHERE session=? AND task_id IS NULL`, id, session);
  });
  // async reflection: only when enabled, at most once per N minutes, detached
  if (getState(dir) === "on" && db.get(`SELECT 1 FROM ${T}tasks WHERE reflected=0`)) {
    const every = (o.everyMin ?? Number(o.env?.MG_REFLECT_EVERY_MIN ?? process.env.MG_REFLECT_EVERY_MIN ?? 10)) * 60_000;
    if (now - Number(metaGet(db, "last_run") ?? 0) >= every) {
      metaSet(db, "last_run", String(now));
      (o.spawnFn ?? ((d) => { spawn(process.execPath, [path.join(import.meta.dir, "reflect.ts"), "run", "--auto"], { detached: true, stdio: "ignore", env: { ...process.env, MG_DATA_DIR: d }, windowsHide: true }).unref(); }))(dir);
    }
  }
}

export function onPrompt(db: Db, p: P, now = Date.now()): string {
  const r = relevant(db, String(p.prompt ?? ""), 5, 800, now);
  return r.text ? JSON.stringify({ hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: r.text } }) : "";
}

/** Dispatch; returns stdout text. Never throws. */
export function handle(kind: string, payload: P, dir = dataDir(), o: Opts = {}): string {
  const env = o.env ?? process.env;
  if (env.MG_REFLECT_RUNNING || getState(dir) === "off") return "";
  let db: Db | null = null;
  try {
    db = openDb(dbPath(dir, env));
    if (kind === "post") onTool(db, payload, o.now);
    else if (kind === "stop") onStop(db, payload, dir, o);
    else if (kind === "prompt") return onPrompt(db, payload, o.now);
  } catch {} finally { try { db?.close(); } catch {} }
  return "";
}

if (import.meta.main) {
  setTimeout(() => process.exit(0), 2500).unref(); // hard stop: never hold the turn
  try {
    const raw = await Bun.stdin.text();
    let p: P = {}; try { p = JSON.parse(raw); } catch {}
    const kind = process.argv[2] ?? ({ PostToolUse: "post", PostToolUseFailure: "post", Stop: "stop", UserPromptSubmit: "prompt" } as P)[p.hook_event_name] ?? "";
    const out = handle(kind, p);
    if (out) process.stdout.write(out + "\n");
  } catch {}
  process.exit(0);
}
