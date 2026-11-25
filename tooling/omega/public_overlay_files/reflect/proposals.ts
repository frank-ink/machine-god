// CODE / CONFIG proposals: stored as 'pending', NEVER applied automatically. Apply needs an explicit yes (TTY in the CLI), backup first,
// only inside the Machine God install dir or config dir, runs the proposal's test command, auto-rollback if it fails.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { type Db, T, dataDir, configDir, installDir } from "./core.ts";

export interface Proposal { id: number; ts: number; task_id: number; kind: string; file: string; change: string; why: string; test: string; status: string; backup: string | null; note: string | null }
export const list = (db: Db, status?: string) => db.all<Proposal>(`SELECT * FROM ${T}proposals ${status ? "WHERE status=?" : ""} ORDER BY id DESC`, ...(status ? [status] : []));
export const get = (db: Db, id: number) => db.get<Proposal>(`SELECT * FROM ${T}proposals WHERE id=?`, id);
export function reject(db: Db, id: number) { const p = get(db, id); if (!p || p.status !== "pending") return false; db.run(`UPDATE ${T}proposals SET status='rejected' WHERE id=?`, id); return true; }

/** Resolve the target; must stay inside an allowed root (install dir or config dir). Throws otherwise. */
export function resolveTarget(file: string, roots: string[]): string {
  const base = roots[0];
  const abs = path.resolve(base, file);
  const real = (p: string) => { try { return fs.realpathSync(p); } catch { return p; } };
  const dirReal = path.join(real(path.dirname(abs)), path.basename(abs));
  for (const r of roots) { const rr = real(path.resolve(r)); const rel = path.relative(rr, dirReal); if (rel && !rel.startsWith("..") && !path.isAbsolute(rel)) return dirReal; }
  throw new Error(`target outside the Machine God install/config dirs: ${file}`);
}

/** Minimal unified-diff applier (single file). Throws if context does not match. */
export function applyDiff(orig: string, diff: string): string {
  const src = orig.split("\n"), out: string[] = [], lines = diff.split("\n");
  let pos = 0, i = 0;
  while (i < lines.length && !lines[i].startsWith("@@")) i++;
  for (; i < lines.length; i++) {
    const h = lines[i].match(/^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@/);
    if (!h) { if (lines[i].startsWith("@@")) throw new Error("bad hunk header"); continue; }
    const start = Math.max(0, Number(h[1]) - 1);
    if (start < pos) throw new Error("overlapping hunks");
    out.push(...src.slice(pos, start)); pos = start;
    for (i++; i < lines.length && !lines[i].startsWith("@@"); i++) {
      const l = lines[i], c = l[0], t = l.slice(1);
      if (l.startsWith("\\") || (l === "" && i === lines.length - 1)) continue;
      if (c === " " || l === "") { if (src[pos] !== t) throw new Error(`context mismatch at line ${pos + 1}`); out.push(src[pos++]); }
      else if (c === "-") { if (src[pos] !== t) throw new Error(`removal mismatch at line ${pos + 1}`); pos++; }
      else if (c === "+") out.push(t);
      else break;
    }
    i--;
  }
  out.push(...src.slice(pos));
  return out.join("\n");
}
const isDiff = (c: string) => /^(diff --git|--- |@@ )/m.test(c) && /^@@ /m.test(c);

export interface ApplyOpts { confirm: () => boolean | Promise<boolean>; roots?: string[]; backupDir?: string; runTest?: (cmd: string, cwd: string) => { code: number; out: string }; now?: number }
const sh = (cmd: string, cwd: string) => { const r = spawnSync(cmd, { shell: true, cwd, encoding: "utf8", timeout: 120_000 }); return { code: r.status ?? 1, out: `${r.stdout ?? ""}${r.stderr ?? ""}`.slice(-400) }; };

export async function apply(db: Db, id: number, o: ApplyOpts): Promise<{ ok: boolean; status: string; note: string }> {
  const p = get(db, id);
  const fin = (status: string, note: string, ok = false) => { db.run(`UPDATE ${T}proposals SET status=?, note=? WHERE id=?`, status, note, id); return { ok, status, note }; };
  if (!p) return { ok: false, status: "missing", note: "no such proposal" };
  if (p.status !== "pending") return { ok: false, status: p.status, note: `proposal is ${p.status}` };
  if (!p.test.trim()) return { ok: false, status: "pending", note: "refused: proposal has no test command" };
  const roots = o.roots ?? [installDir(), configDir()];
  let target: string;
  try { target = resolveTarget(p.file, roots); } catch (e: any) { return { ok: false, status: "pending", note: `refused: ${e.message}` }; }
  if (!(await o.confirm())) return { ok: false, status: "pending", note: "not confirmed" };
  const existed = fs.existsSync(target), orig = existed ? fs.readFileSync(target, "utf8") : "";
  let next: string;
  try { next = isDiff(p.change) ? applyDiff(orig, p.change) : p.change; } catch (e: any) { return fin("failed", `diff did not apply: ${e.message}`); }
  const bdir = path.join(o.backupDir ?? path.join(dataDir(), "reflect-backups"), `${id}-${o.now ?? Date.now()}`);
  fs.mkdirSync(bdir, { recursive: true });
  const backup = path.join(bdir, path.basename(target) + (existed ? "" : ".absent"));
  if (existed) fs.copyFileSync(target, backup); else fs.writeFileSync(backup, "");
  db.run(`UPDATE ${T}proposals SET backup=? WHERE id=?`, `${backup}\t${target}\t${existed ? 1 : 0}`, id);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, next);
  const t = (o.runTest ?? sh)(p.test, roots[0]);
  if (t.code === 0) return fin("applied", `test passed; backup ${backup}`, true);
  restore(target, backup, existed);
  return fin("rolledback", `test failed (exit ${t.code}); restored from backup. ${t.out}`.slice(0, 500));
}
function restore(target: string, backup: string, existed: boolean) { if (existed) fs.copyFileSync(backup, target); else fs.rmSync(target, { force: true }); }
/** Undo an applied proposal from its backup. */
export function revert(db: Db, id: number): boolean {
  const p = get(db, id); if (!p || p.status !== "applied" || !p.backup) return false;
  const [backup, target, ex] = p.backup.split("\t");
  restore(target, backup, ex === "1");
  db.run(`UPDATE ${T}proposals SET status='reverted' WHERE id=?`, id);
  return true;
}
