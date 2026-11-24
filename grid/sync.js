// Optional memory sync through your private GRID repo (the one `machine-god grid repo` set up): memory/<instance>.jsonl, one file per install,
// so two computers never write the same file and git never conflicts. OFF until you run `machine-god grid sync on` (and the repo exists).
//   export: new memories made on this computer (not imported ones, nothing that looks like a secret) are appended, committed and pushed.
//   import: every other memory/*.jsonl is read on start, each line validated, duplicates ignored (memory_id = hash of kind+value).
// Imported memories are DATA: they can come from anyone who can push to the repo, so they are marked source "sync" and are shown to the AIs as data, never as instructions.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { resolvePaths } from "../firstrun/mg-common.js";
import * as U from "./udb.js";

const KINDS = new Set(["fact", "note", "research", "preference"]);
const MAX_FILE = 2 * 1024 * 1024;
const MAX_LINE = 4096;
const MAX_LINES = 20_000;
const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,60}\.jsonl$/;

export function repoDir(env = process.env, paths = resolvePaths({ env })) {
  if (env.MG_GRID_DIR) return env.MG_GRID_DIR;
  try {
    const g = JSON.parse(fs.readFileSync(path.join(paths.configDir, "grid.json"), "utf8"));
    if (g.dir) return g.dir;
  } catch {}
  return path.join(paths.dataDir, "grid");
}
export const repoReady = (dir) => fs.existsSync(path.join(dir, ".git"));

function git(dir, args, { ident = false, timeout = 60_000 } = {}) {
  const pre = ident ? ["-c", "user.name=Machine God", "-c", "user.email=machine-god@users.noreply.github.com"] : [];
  const r = spawnSync("git", [...pre, "-C", dir, ...args], { encoding: "utf8", timeout, env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } });
  return { code: r.status ?? -1, out: ((r.stdout || "") + (r.stderr || "")).trim() };
}
const branch = (dir) => git(dir, ["symbolic-ref", "--short", "HEAD"]).out || "main";

export const syncMode = (db) => U.confGet(db, "mg.sync", "off");
export function setSync(db, on) {
  U.confSet(db, "mg.sync", on ? "on" : "off");
}

/** One memory -> one JSON line (no secrets). */
const toLine = (m, by) => JSON.stringify({ id: m.memory_id, kind: m.kind, subject: m.subject, value: m.value, ts: m.ts, by });

export function exportMemories(db, dir) {
  const inst = U.instanceId(db);
  const cursor = Number(U.metaGet(db, "mg_sync_cursor") || 0);
  const rows = db.query("SELECT rowid AS rid, * FROM durable_memory WHERE rowid > ? ORDER BY rowid").all(cursor);
  const lines = [];
  let last = cursor;
  for (const r of rows) {
    last = Math.max(last, r.rid);
    const prov = U.safeJson(r.provenance, {});
    if (prov.source === "sync") continue;
    if (U.looksSecret(r.value) || U.looksSecret(r.subject)) continue;
    lines.push(toLine(r, prov.ai || prov.by || "user"));
  }
  if (lines.length) {
    fs.mkdirSync(path.join(dir, "memory"), { recursive: true });
    fs.appendFileSync(path.join(dir, "memory", `mg-${inst}.jsonl`), lines.join("\n") + "\n");
  }
  U.metaSet(db, "mg_sync_cursor", last);
  return { exported: lines.length };
}

export function importMemories(db, dir) {
  const own = `mg-${U.instanceId(db)}.jsonl`;
  const mdir = path.join(dir, "memory");
  let added = 0;
  let seen = 0;
  let skipped = 0;
  if (!fs.existsSync(mdir)) return { added, seen, skipped };
  for (const name of fs.readdirSync(mdir).sort()) {
    if (name === own || !SAFE_FILE.test(name)) continue;
    const file = path.join(mdir, name);
    let raw;
    try {
      const st = fs.lstatSync(file);
      if (!st.isFile() || st.size > MAX_FILE) {
        skipped++;
        continue;
      }
      raw = fs.readFileSync(file, "utf8");
    } catch {
      skipped++;
      continue;
    }
    for (const line of raw.split("\n").slice(0, MAX_LINES)) {
      if (!line.trim()) continue;
      seen++;
      if (line.length > MAX_LINE) {
        skipped++;
        continue;
      }
      let j;
      try {
        j = JSON.parse(line);
      } catch {
        skipped++;
        continue;
      }
      if (!j || typeof j !== "object" || typeof j.value !== "string") {
        skipped++;
        continue;
      }
      const kind = KINDS.has(j.kind) ? j.kind : "note";
      const ts = Number.isFinite(j.ts) && j.ts > 0 && j.ts < 4e9 ? j.ts : Date.now() / 1000;
      const r = U.addMemory(db, { kind, subject: typeof j.subject === "string" ? j.subject : "", value: j.value, by: String(j.by || "sync").slice(0, 40), source: "sync", ts, extra: { file: name } });
      if (r.added) added++;
      else if (r.refused) skipped++;
    }
  }
  return { added, seen, skipped };
}

/** Pull, import, export, push. -> { ok, imported, exported, detail } ; never throws. */
export function syncNow(db, { env = process.env, paths, push = true } = {}) {
  const dir = repoDir(env, paths);
  if (!repoReady(dir)) return { ok: false, detail: `no GRID repo clone at ${dir} (run: machine-god grid repo)` };
  const br = branch(dir);
  const remote = git(dir, ["ls-remote", "--heads", "origin", br]);
  if (remote.code === 0 && remote.out) {
    const p = git(dir, ["pull", "--rebase", "--autostash", "--quiet", "origin", br], { ident: true });
    if (p.code !== 0) return { ok: false, detail: `git pull failed: ${p.out.slice(0, 160)}` };
  }
  const imp = importMemories(db, dir);
  const exp = exportMemories(db, dir);
  let detail = `imported ${imp.added} new (${imp.seen} lines, ${imp.skipped} skipped), exported ${exp.exported}`;
  if (push && exp.exported) {
    git(dir, ["add", "memory"]);
    const hasIdent = git(dir, ["config", "user.name"]).out && git(dir, ["config", "user.email"]).out;
    const c = git(dir, ["commit", "-q", "-m", `memory: ${exp.exported} new`], { ident: !hasIdent });
    if (c.code !== 0 && !/nothing to commit/.test(c.out)) return { ok: false, imported: imp.added, exported: exp.exported, detail: `${detail}; commit failed: ${c.out.slice(0, 120)}` };
    let p = git(dir, ["push", "-q", "origin", `HEAD:${br}`]);
    if (p.code !== 0) {
      git(dir, ["pull", "--rebase", "--autostash", "--quiet", "origin", br], { ident: true });
      p = git(dir, ["push", "-q", "origin", `HEAD:${br}`]);
    }
    if (p.code !== 0) return { ok: false, imported: imp.added, exported: exp.exported, detail: `${detail}; push failed: ${p.out.slice(0, 120)}` };
  }
  return { ok: true, imported: imp.added, exported: exp.exported, detail };
}

/** Best-effort wrapper used on start and after writes: only when sync is on and the repo exists. */
export function autoSync(db, { env = process.env, paths } = {}) {
  try {
    if (syncMode(db) !== "on") return null;
    return syncNow(db, { env, paths });
  } catch (e) {
    return { ok: false, detail: String(e.message || e).slice(0, 160) };
  }
}
