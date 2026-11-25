// Machine God self-improvement: shared core. Paths, redaction, small DB interface, schema, text helpers.
import { Database } from "bun:sqlite";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// ---------- locations ----------
export function dataDir(env: Record<string, string | undefined> = process.env, platform = process.platform): string {
  if (env.MG_DATA_DIR) return env.MG_DATA_DIR;
  const home = (platform === "win32" ? env.USERPROFILE : env.HOME) || os.homedir();
  if (platform === "darwin") return path.join(home, "Library", "Application Support", "machine-god");
  if (platform === "win32") return path.win32.join(env.LOCALAPPDATA || path.win32.join(home, "AppData", "Local"), "machine-god");
  return path.join(env.XDG_DATA_HOME || path.join(home, ".local", "share"), "machine-god");
}
export function configDir(env: Record<string, string | undefined> = process.env): string {
  if (env.MG_CONFIG_DIR) return env.MG_CONFIG_DIR;
  const home = env.HOME || env.USERPROFILE || os.homedir();
  return process.platform === "win32" ? path.join(env.APPDATA || path.join(home, "AppData", "Roaming"), "machine-god") : path.join(env.XDG_CONFIG_HOME || path.join(home, ".config"), "machine-god");
}
/** Install dir (where proposals may change files): MG_HOME or the parent of reflect/. */
export const installDir = (env = process.env) => env.MG_HOME || path.resolve(import.meta.dir, "..");

// ---------- state flag: "on" | "off" | missing (= capture + injection only, no reflection) ----------
export const stateFile = (dir = dataDir()) => path.join(dir, "reflect.state");
export function getState(dir = dataDir()): "on" | "off" | "unset" {
  try { const s = fs.readFileSync(stateFile(dir), "utf8").trim(); return s === "on" || s === "off" ? s : "unset"; } catch { return "unset"; }
}
export function setState(s: "on" | "off", dir = dataDir()) { fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(stateFile(dir), s + "\n"); }

// ---------- redaction + caps ----------
const RX: RegExp[] = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{5,}/g, // JWT
  /\b(?:sk|pk|rk|gsk|xai|nvapi|hf|glpat|ghp|gho|ghu|ghs|github_pat|xox[abprs]|AIza|AKIA|ASIA)[-_A-Za-z0-9]{12,}/g,
  /\bBearer\s+[A-Za-z0-9._~+\/=-]{12,}/gi,
  /\b(?:authorization|api[_-]?key|apikey|access[_-]?key|secret|token|passwd|password|pwd|credential)s?(["']?\s*[:=]\s*["']?)[^\s"',;&]{3,}/gi,
  /(:\/\/[^\s:@\/]+:)[^\s@\/]{3,}@/g, // user:pass@host
  /\b[A-Za-z0-9+\/_-]{32,}={0,2}(?![A-Za-z0-9])/g, // long opaque blobs
];
export function redact(t: string): string {
  let s = String(t ?? "");
  s = s.replace(RX[0], "[REDACTED]").replace(RX[1], "[REDACTED]").replace(RX[2], "[REDACTED]").replace(RX[3], "Bearer [REDACTED]");
  s = s.replace(RX[4], (_m, sep) => `[REDACTED-SECRET]${sep ? "" : ""}`).replace(RX[5], "$1[REDACTED]@");
  // long blobs: only if they mix letters and digits (skip plain long words / paths)
  s = s.replace(RX[6], (m) => (/[0-9]/.test(m) && /[A-Za-z]/.test(m) ? "[REDACTED]" : m));
  return s;
}
export const cap = (t: string, n: number) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
export const clean = (t: string, n: number) => cap(redact(t).replace(/\s+/g, " ").trim(), n);

// ---------- DB interface: the only thing the rest of the code uses. unified.db later = another opener, same interface. ----------
export interface Db {
  run(sql: string, ...p: any[]): { lastInsertRowid: number | bigint; changes: number };
  all<T = any>(sql: string, ...p: any[]): T[];
  get<T = any>(sql: string, ...p: any[]): T | null;
  tx<T>(fn: () => T): T;
  close(): void;
}
export const T = "mgr_"; // table prefix: keeps these tables apart when they live inside unified.db
const SCHEMA = `
CREATE TABLE IF NOT EXISTS ${T}events(id INTEGER PRIMARY KEY, ts INTEGER, session TEXT, tool TEXT, sub TEXT, ok INTEGER, err_class TEXT, err TEXT, dur_ms INTEGER, task_id INTEGER);
CREATE INDEX IF NOT EXISTS ${T}ev_s ON ${T}events(session, task_id);
CREATE TABLE IF NOT EXISTS ${T}tasks(id INTEGER PRIMARY KEY, ts INTEGER, session TEXT, prompt TEXT, answer TEXT, tools_n INTEGER, errs_n INTEGER, reflected INTEGER DEFAULT 0, outcome TEXT, confidence REAL, reflection TEXT);
CREATE TABLE IF NOT EXISTS ${T}lessons(id INTEGER PRIMARY KEY, text TEXT, applies_to TEXT, confidence REAL, reinforced INTEGER DEFAULT 1, used INTEGER DEFAULT 0, created INTEGER, updated INTEGER, last_used INTEGER, decayed_at INTEGER, status TEXT DEFAULT 'active', flag TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS ${T}lesson_versions(version INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, lesson_id INTEGER, action TEXT, before TEXT, after TEXT, undone INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ${T}proposals(id INTEGER PRIMARY KEY, ts INTEGER, task_id INTEGER, kind TEXT, file TEXT, change TEXT, why TEXT, test TEXT, status TEXT DEFAULT 'pending', backup TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS ${T}meta(k TEXT PRIMARY KEY, v TEXT);
`;
/** Where the tables live. MG_REFLECT_DB points them into another SQLite file (e.g. the GRID unified.db) without code changes. */
/** One memory: once the GRID created unified.db (same data dir), reflection lives there too (tables `mgr_*`); before that reflect.db. */
export const dbPath = (dir = dataDir(), env: Record<string, string | undefined> = process.env) =>
  env.MG_REFLECT_DB || (fs.existsSync(path.join(dir, "unified.db")) ? path.join(dir, "unified.db") : path.join(dir, "reflect.db"));
export function openDb(file = dbPath()): Db {
  if (file !== ":memory:") fs.mkdirSync(path.dirname(file), { recursive: true });
  const d = new Database(file);
  d.exec("PRAGMA busy_timeout=300; PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;");
  d.exec(SCHEMA);
  return {
    run: (sql, ...p) => d.query(sql).run(...p) as any,
    all: (sql, ...p) => d.query(sql).all(...p) as any,
    get: (sql, ...p) => (d.query(sql).get(...p) as any) ?? null,
    tx: (fn) => d.transaction(fn)() as any,
    close: () => d.close(),
  };
}
export const metaGet = (db: Db, k: string) => db.get<{ v: string }>(`SELECT v FROM ${T}meta WHERE k=?`, k)?.v ?? null;
export const metaSet = (db: Db, k: string, v: string) => db.run(`INSERT INTO ${T}meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v`, k, v);

// ---------- text helpers ----------
const STOP = new Set("a an the and or but if then else of to in on at by for with from as is are was were be been being it its this that these those i you we they he she do does did not no can could should would will shall may might must have has had into over under than so very just also about up down out off any all each per via use using used before after when while always never avoid dont don't".split(" "));
export const NEG = new Set(["never", "not", "no", "dont", "don't", "avoid", "stop", "without", "cannot", "can't", "skip"]);
function stem(w: string) { return w.length > 5 ? w.replace(/(ing|ed|es|s)$/, "") : w.length > 3 ? w.replace(/s$/, "") : w; }
export function tokens(t: string, keepNeg = false): string[] {
  return (String(t).toLowerCase().match(/[a-z0-9_.\/-]{2,}|[a-z]{1}/g) ?? []).filter((w) => (keepNeg && NEG.has(w)) || !(STOP.has(w) || NEG.has(w))).map(stem);
}
export function jaccard(a: string[], b: string[]): number {
  const A = new Set(a), B = new Set(b); if (!A.size || !B.size) return 0;
  let i = 0; for (const x of A) if (B.has(x)) i++;
  return i / (A.size + B.size - i);
}
export const hasNeg = (t: string) => (String(t).toLowerCase().match(/[a-z']+/g) ?? []).some((w) => NEG.has(w));
