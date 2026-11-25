// Machine God shared memory: ONE unified.db (the frankenstein3 schema) on this computer, used by every connected AI.
//
// Tables used (all exist in plugins/frankenstein3/scripts/star/data/schema_empty.sql; no table is added, none is altered):
//   users            one row 'owner' (the human) and one 'machine-god' (the entity)
//   sessions         one session per asker ('machine-god:<asker>', e.g. cli, mcp:claude-code, fusion, mailbox:chatgpt, interest)
//   turns            every request (role 'user') and every answer (role 'assistant'); provenance JSON holds who asked, which AI answered,
//                    how it was routed and the engine frame; causal_refs of an answer = [turn_id of its request]; resource_refs = ["ai:<id>"]
//   durable_memory   facts, notes and research results (kind, subject, value); memory_id = hash of kind+value, so the same fact is stored once
//   entityos_profil  the persona override (user 'machine-god', field 'persona')
//   star_konfig      settings (sync on/off, ...)
//   meta             engine state, instance id, sync cursor
// A separate mg_grid_turn table was NOT needed: turns + provenance + causal_refs carry "who asked / which AI answered / prompt / answer / ts".
import { Database } from "bun:sqlite";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

// ---------- locations ----------
/** ~/.local/share/machine-god | macOS ~/Library/Application Support/machine-god | Windows %LOCALAPPDATA%\machine-god | MG_DATA_DIR overrides. */
export function gridDataDir(env = process.env, platform = process.platform) {
  if (env.MG_DATA_DIR) return env.MG_DATA_DIR;
  const home = (platform === "win32" ? env.USERPROFILE : env.HOME) || os.homedir();
  if (platform === "darwin") return path.join(home, "Library", "Application Support", "machine-god");
  if (platform === "win32") return path.win32.join(env.LOCALAPPDATA || path.win32.join(home, "AppData", "Local"), "machine-god");
  return path.join(env.XDG_DATA_HOME || path.join(home, ".local", "share"), "machine-god");
}
export const dbFile = (env = process.env, platform = process.platform) => path.join(gridDataDir(env, platform), "unified.db");

/** The schema ships inside the repository (plugin) and is copied next to this file in the install archive. */
export function schemaFile(env = process.env) {
  const candidates = [
    env.MG_GRID_SCHEMA,
    path.join(here, "schema_empty.sql"),
    path.join(here, "..", "plugins", "frankenstein3", "scripts", "star", "data", "schema_empty.sql"),
  ].filter(Boolean);
  for (const c of candidates) if (fs.existsSync(c)) return c;
  throw new Error(`unified.db schema (schema_empty.sql) not found; looked in: ${candidates.join(", ")}`);
}

export const REQUIRED_TABLES = ["users", "sessions", "turns", "durable_memory", "entityos_profil", "star_konfig", "meta"];

// ---------- secrets: nothing that looks like a key is ever stored or sent ----------
const SECRET_SOURCES = [
  "\\bsk-[A-Za-z0-9_-]{16,}", "\\bnv" + "api-[A-Za-z0-9_-]{16,}", "\\bgs" + "k_[A-Za-z0-9]{16,}", "\\bgh[pousr]_[A-Za-z0-9]{20,}", "\\bgithub_pat_[A-Za-z0-9_]{20,}",
  "\\bAK" + "IA[0-9A-Z]{16}\\b", "\\bAI" + "za[0-9A-Za-z_-]{20,}", "\\bxai-[A-Za-z0-9]{20,}", "\\bpplx-[A-Za-z0-9]{20,}",
  "-----BEGIN [A-Z ]*PRIVATE KEY-----", "\\b(?:password|passwort|passphrase|secret|api[_ -]?key|token)\\s*[:=]\\s*\\S{8,}",
];
const SECRET_RE = new RegExp(SECRET_SOURCES.join("|"), "i");
export const looksSecret = (text) => SECRET_RE.test(String(text ?? ""));

// ---------- open / create ----------
function execSchema(db, sql) {
  try {
    db.exec(sql);
    return;
  } catch (e) {
    // an SQLite build without FTS5: skip only the virtual (full-text) tables, everything else is required
    if (!/fts5|no such module/i.test(String(e.message))) throw e;
  }
  for (const stmt of sql.split(/;\s*\n/)) {
    const s = stmt.replace(/^(\s*--.*\n)+/g, "").trim();
    if (!s) continue;
    try {
      db.exec(s);
    } catch (e) {
      if (!/^CREATE VIRTUAL TABLE/i.test(s)) throw e;
    }
  }
}

/** Create a fresh unified.db from the schema (atomic: temp file, then rename). */
export function createDb(file, env = process.env) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const sql = fs.readFileSync(schemaFile(env), "utf8");
  const tmp = `${file}.neu.${process.pid}`;
  fs.rmSync(tmp, { force: true });
  const db = new Database(tmp, { create: true });
  try {
    db.exec("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF"); // a half-written temp file is simply discarded; the real file appears only by rename
    execSchema(db, sql);
    const bad = db.query("PRAGMA integrity_check").get();
    if (bad && Object.values(bad)[0] !== "ok") throw new Error("integrity check failed on the new unified.db");
  } finally {
    db.close();
  }
  fs.renameSync(tmp, file);
  if (process.platform !== "win32") fs.chmodSync(file, 0o600);
}

export const tableCount = (db) => db.query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").get().n;

/** Open (and create on first use) the unified.db. Throws when an existing file lacks the tables Machine God needs. */
export function openDb({ env = process.env, create = true } = {}) {
  const file = dbFile(env);
  if (!fs.existsSync(file)) {
    if (!create) throw new Error(`no unified.db at ${file} (run: machine-god grid init)`);
    createDb(file, env);
  }
  const db = new Database(file);
  db.exec("PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL; PRAGMA foreign_keys=OFF;");
  const have = new Set(db.query("SELECT name FROM sqlite_master WHERE type='table'").all().map((r) => r.name));
  const missing = REQUIRED_TABLES.filter((t) => !have.has(t));
  if (missing.length) {
    db.close();
    throw new Error(`${file} is not a frankenstein3 unified.db (missing tables: ${missing.join(", ")})`);
  }
  const now = Date.now() / 1000;
  db.query("INSERT OR IGNORE INTO users(user_id, display_name) VALUES ('owner', 'Owner')").run();
  db.query("INSERT OR IGNORE INTO users(user_id, display_name) VALUES ('machine-god', 'Machine God')").run();
  if (!db.query("SELECT 1 FROM meta WHERE key='mg_instance'").get()) {
    db.query("INSERT OR IGNORE INTO meta(key, value) VALUES ('mg_instance', ?)").run(crypto.randomBytes(4).toString("hex"));
    db.query("INSERT OR IGNORE INTO meta(key, value) VALUES ('mg_created', ?)").run(String(now));
  }
  return db;
}

// ---------- small helpers ----------
export const metaGet = (db, key) => db.query("SELECT value FROM meta WHERE key=?").get(key)?.value ?? null;
export const metaSet = (db, key, value) => db.query("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(key, String(value));
export const instanceId = (db) => metaGet(db, "mg_instance");

export function confGet(db, key, fallback = null) {
  const r = db.query("SELECT wert FROM star_konfig WHERE schluessel=?").get(key);
  return r ? r.wert : fallback;
}
export function confSet(db, key, value, type = "string") {
  db.query(
    "INSERT INTO star_konfig(schluessel, wert, typ, quelle, geaendert) VALUES (?, ?, ?, 'machine-god', ?) ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, geaendert=excluded.geaendert",
  ).run(key, String(value), type, Date.now() / 1000);
}

export const getPersonaOverride = (db) => db.query("SELECT wert FROM entityos_profil WHERE user_id='machine-god' AND feld='persona'").get()?.wert ?? null;
export function setPersonaOverride(db, text) {
  if (text === null) return db.query("DELETE FROM entityos_profil WHERE user_id='machine-god' AND feld='persona'").run();
  db.query(
    "INSERT INTO entityos_profil(user_id, feld, wert, herkunft, beleg, erfasst) VALUES ('machine-god', 'persona', ?, 'eigner', 'machine-god grid persona set', ?) " +
      "ON CONFLICT(user_id, feld) DO UPDATE SET wert=excluded.wert, erfasst=excluded.erfasst",
  ).run(text, Date.now() / 1000);
}

// ---------- turns ----------
const sessionIdFor = (asker) => `machine-god:${asker}`;

export function ensureSession(db, asker) {
  const id = sessionIdFor(asker);
  const now = Date.now() / 1000;
  db.query("INSERT OR IGNORE INTO sessions(session_id, user_id, created_at, updated_at, terminal_name) VALUES (?, 'owner', ?, ?, ?)").run(id, now, now, id);
  return id;
}

/** Append one turn. role: user | assistant | system | tool. The ordinal is allocated inside the transaction, so parallel processes never collide. -> turn_id */
export function addTurn(db, { asker, role, content, provenance = {}, causal = [], resources = [] }) {
  const sid = ensureSession(db, asker);
  const turnId = `t_${crypto.randomBytes(8).toString("hex")}`;
  const ts = Date.now() / 1000;
  db.transaction(() => {
    const ord = (db.query("SELECT COALESCE(MAX(ordinal), 0) + 1 AS n FROM turns WHERE session_id=?").get(sid)).n;
    db.query(
      "INSERT INTO turns(turn_id, session_id, user_id, ordinal, ts, role, content, resource_refs, causal_refs, provenance) VALUES (?, ?, 'owner', ?, ?, ?, ?, ?, ?, ?)",
    ).run(turnId, sid, ord, ts, role, content, JSON.stringify(resources), JSON.stringify(causal), JSON.stringify({ asker, ...provenance }));
    db.query("UPDATE sessions SET updated_at=? WHERE session_id=?").run(ts, sid);
  }).immediate();
  return turnId;
}

export function recentUserPrompts(db, n = 8) {
  return db.query("SELECT content FROM turns WHERE role='user' ORDER BY ts DESC LIMIT ?").all(n).map((r) => r.content);
}

/** Last n answered requests: [{ ts, asker, ai, prompt, answer, turn_id }] newest first. */
export function history(db, n = 10) {
  const rows = db.query("SELECT turn_id, ts, content, causal_refs, provenance FROM turns WHERE role='assistant' ORDER BY ts DESC, rowid DESC LIMIT ?").all(Math.max(1, Math.min(200, n)));
  return rows.map((r) => {
    const prov = safeJson(r.provenance, {});
    const q = safeJson(r.causal_refs, [])[0];
    const prompt = q ? db.query("SELECT content FROM turns WHERE turn_id=?").get(q)?.content ?? "" : "";
    return { turn_id: r.turn_id, ts: r.ts, asker: prov.asker, ai: prov.ai, prompt, answer: r.content };
  });
}

export function safeJson(text, fallback) {
  try {
    const j = JSON.parse(text);
    return j ?? fallback;
  } catch {
    return fallback;
  }
}

// ---------- memories ----------
const norm = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
export const memoryId = (kind, value) => "m_" + crypto.createHash("sha256").update(`${kind}\n${norm(value).toLowerCase()}`).digest("hex").slice(0, 20);
const MAX_VALUE = 1500;

/** Store one memory. Refuses secrets and empty text. -> { id, added, refused? } (added=false: the same fact was already there) */
export function addMemory(db, { kind = "note", subject = "", value, by = "user", ai = null, sourceTurn = null, source = "remember", ts = null, extra = {} }) {
  const v = norm(value).slice(0, MAX_VALUE);
  if (!v) return { id: null, added: false, refused: "empty" };
  if (looksSecret(v) || looksSecret(subject)) return { id: null, added: false, refused: "looks like a secret" };
  const id = memoryId(kind, v);
  const prov = JSON.stringify({ source, by, ...(ai ? { ai } : {}), ...extra });
  const r = db.query(
    "INSERT OR IGNORE INTO durable_memory(memory_id, kind, subject, value, source_turn_id, user_id, ts, provenance) VALUES (?, ?, ?, ?, ?, 'owner', ?, ?)",
  ).run(id, kind, norm(subject).slice(0, 120), v, sourceTurn, ts ?? Date.now() / 1000, prov);
  return { id, added: r.changes > 0 };
}

export const STOP = new Set(
  ("the and for with that this from have has had are was were you your what when where which who how why not but can could would should will about into onto over than then them they their there here " +
    "ein eine einen einem einer der die das den dem des und oder nicht mit von für auf ist sind war wie was wer wo wann warum ich du er sie wir ihr mein dein").split(" "),
);
export const tokenize = (t) => [...new Set((String(t || "").toLowerCase().match(/[\p{L}\p{N}_]{2,}/gu) || []).filter((w) => !STOP.has(w)))];
const stemOf = (t) => (t.length > 5 ? t.slice(0, -2) : t);
const likeEsc = (s) => s.replace(/[\\%_]/g, (m) => "\\" + m);

/** Rank memories for a query: LIKE prefilter in SQLite, then idf-weighted token score with prefix matching, phrase bonus and a small recency term. */
export function recall(db, query, { k = 5, kinds = null } = {}) {
  const toks = tokenize(query).slice(0, 12);
  const kindSql = kinds?.length ? ` AND kind IN (${kinds.map(() => "?").join(",")})` : "";
  const kindArgs = kinds?.length ? kinds : [];
  const pack = (r, score) => ({ id: r.memory_id, kind: r.kind, subject: r.subject, value: r.value, ts: r.ts, by: safeJson(r.provenance, {}).by, ai: safeJson(r.provenance, {}).ai, source: safeJson(r.provenance, {}).source, score: Math.round(score * 1000) / 1000 });
  if (!toks.length) {
    return db.query(`SELECT * FROM durable_memory WHERE 1=1${kindSql} ORDER BY ts DESC LIMIT ?`).all(...kindArgs, k).map((r) => pack(r, 0));
  }
  const stems = toks.map(stemOf);
  const where = stems.map(() => "(lower(value) LIKE ? ESCAPE '\\' OR lower(subject) LIKE ? ESCAPE '\\')").join(" OR ");
  const args = stems.flatMap((s) => [`%${likeEsc(s)}%`, `%${likeEsc(s)}%`]);
  const rows = db.query(`SELECT * FROM durable_memory WHERE (${where})${kindSql} ORDER BY ts DESC LIMIT 500`).all(...args, ...kindArgs);
  if (!rows.length) return [];
  const total = db.query("SELECT COUNT(*) AS n FROM durable_memory").get().n;
  const df = stems.map((s) => db.query("SELECT COUNT(*) AS n FROM durable_memory WHERE lower(value) LIKE ? ESCAPE '\\' OR lower(subject) LIKE ? ESCAPE '\\'").get(`%${likeEsc(s)}%`, `%${likeEsc(s)}%`).n);
  const idf = df.map((d) => Math.log(1 + (total - d + 0.5) / (d + 0.5)));
  const now = Date.now() / 1000;
  const phrase = norm(query).toLowerCase();
  const scored = [];
  for (const r of rows) {
    const text = `${r.subject} ${r.value}`.toLowerCase();
    const words = text.match(/[\p{L}\p{N}_]{2,}/gu) || [];
    let s = 0;
    toks.forEach((t, i) => {
      let exact = 0;
      let pre = 0;
      for (const w of words) {
        if (w === t) exact++;
        else if (stems[i].length >= 4 && w.startsWith(stems[i])) pre++;
      }
      if (exact || pre) s += idf[i] * (1 + Math.log(1 + exact + 0.6 * pre));
    });
    if (s <= 0) continue;
    s /= 1 + 0.15 * Math.log(1 + text.length / 80);
    if (phrase.length > 6 && text.includes(phrase)) s += 1;
    s += 0.2 * Math.exp(-Math.max(0, now - r.ts) / 86400 / 90);
    scored.push([s, r]);
  }
  scored.sort((a, b) => b[0] - a[0] || b[1].ts - a[1].ts);
  return scored.slice(0, k).map(([s, r]) => pack(r, s));
}

export function forget(db, idOrPrefix) {
  const rows = db.query("SELECT memory_id FROM durable_memory WHERE memory_id LIKE ? ESCAPE '\\'").all(`${likeEsc(idOrPrefix)}%`);
  if (rows.length !== 1) return { removed: 0, matches: rows.length };
  db.query("DELETE FROM durable_memory WHERE memory_id=?").run(rows[0].memory_id);
  return { removed: 1, id: rows[0].memory_id };
}

export function stats(db) {
  const n = (sql) => db.query(sql).get().n;
  return {
    file: db.filename,
    tables: tableCount(db),
    instance: instanceId(db),
    memories: n("SELECT COUNT(*) AS n FROM durable_memory"),
    turns: n("SELECT COUNT(*) AS n FROM turns"),
    answers: n("SELECT COUNT(*) AS n FROM turns WHERE role='assistant'"),
    askers: db.query("SELECT DISTINCT json_extract(provenance,'$.asker') AS a FROM turns WHERE role='user'").all().map((r) => r.a).filter(Boolean),
    answered_by: db.query("SELECT json_extract(provenance,'$.ai') AS a, COUNT(*) AS n FROM turns WHERE role='assistant' GROUP BY a").all().filter((r) => r.a),
  };
}
