// `machine-god improve <cmd>` -> bun cli.ts <cmd>. Exit: 0 ok, 1 usage/not found, 2 backend failure, 3 refused (needs interactive yes).
import readline from "node:readline/promises";
import { type Db, T, openDb, dbPath, dataDir, getState, setState } from "./core.ts";
import { activeLessons, rollback } from "./learn.ts";
import { run, backendChain, BACKENDS } from "./reflect.ts";
import * as P from "./proposals.ts";
import { installHooks, removeHooks, settingsFile } from "./settings.ts";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const when = (ts: number | null) => (ts ? new Date(ts).toISOString().slice(0, 16).replace("T", " ") : "-");
const MIN_HALF = 10;

export function metrics(db: Db) {
  const rows = db.all<{ id: number; ts: number; outcome: string }>(`SELECT id, ts, outcome FROM ${T}tasks WHERE reflected=1 ORDER BY id`);
  const total = db.get<{ n: number }>(`SELECT COUNT(*) n FROM ${T}tasks`)!.n;
  const half = Math.floor(rows.length / 2), A = rows.slice(0, half), B = rows.slice(half);
  const ok = (r: typeof rows) => (r.length ? r.filter((x) => x.outcome === "success").length / r.length : 0);
  const repeat = (r: typeof rows) => {
    if (!r.length) return { calls: 0, rate: 0 };
    const ids = r.map((x) => x.id), q = ids.map(() => "?").join(",");
    const calls = db.get<{ n: number }>(`SELECT COUNT(*) n FROM ${T}events WHERE task_id IN (${q})`, ...ids)!.n;
    const rep = db.all<{ c: number }>(`SELECT COUNT(*) c FROM ${T}events WHERE ok=0 AND task_id IN (${q}) GROUP BY tool, COALESCE(sub,''), err_class HAVING c>=3`, ...ids).reduce((a, x) => a + x.c, 0);
    return { calls, rate: calls ? rep / calls : 0 };
  };
  const enough = A.length >= MIN_HALF && B.length >= MIN_HALF;
  const [ra, rb] = [repeat(A), repeat(B)];
  const verdict = (a: number, b: number, better: 1 | -1) => !enough ? `insufficient data (need >=${MIN_HALF} reflected tasks per half, have ${A.length}/${B.length})` : Math.abs(b - a) < 0.1 ? "flat (within noise)" : (b - a) * better > 0 ? "improving" : "worse";
  return { total, reflected: rows.length, outcomes: Object.fromEntries(["success", "partial", "fail"].map((o) => [o, rows.filter((r) => r.outcome === o).length])), early: { n: A.length, success: ok(A), repeated_error_rate: ra.rate }, late: { n: B.length, success: ok(B), repeated_error_rate: rb.rate }, success_trend: verdict(ok(A), ok(B), 1), repeated_error_trend: verdict(ra.rate, rb.rate, -1), enough };
}

export async function main(argv: string[], io = { out: (s: string) => console.log(s), err: (s: string) => console.error(s) }): Promise<number> {
  const [cmd = "status", ...rest] = argv, dir = dataDir(), flag = (k: string) => (rest.includes(k) ? rest[rest.indexOf(k) + 1] : undefined);
  const out = io.out;
  if (cmd === "enable" || cmd === "disable") {
    const on = cmd === "enable";
    setState(on ? "on" : "off", dir);
    try { const n = on ? installHooks() : removeHooks(); out(`${on ? "hooks registered" : "hooks removed"} in ${settingsFile()} (${n}; backup next to it)`); }
    catch (e) { io.err(`could not update ${settingsFile()}: ${(e as Error).message} (state is ${on ? "on" : "off"}; register the hooks by hand, see reflect/README.md)`); }
    out(on ? "self-improvement ON: capture, reflection (task summaries go to your chosen AI backend), lesson injection" : "self-improvement OFF: hooks do nothing; stored data kept");
    return 0;
  }
  const db = openDb(dbPath(dir));
  try {
    const id = Number(rest[0]);
    switch (cmd) {
      case "status": {
        const m = metrics(db), l = activeLessons(db), last = db.get<{ ts: number }>(`SELECT ts FROM ${T}tasks WHERE reflected=1 ORDER BY id DESC LIMIT 1`);
        out(`state: ${getState(dir)} (unset = capture + injection only, no reflection)  data: ${dir}`);
        out(`tasks: ${m.total} captured, ${m.reflected} reflected (success ${m.outcomes.success}, partial ${m.outcomes.partial}, fail ${m.outcomes.fail}); last reflection ${when(last?.ts ?? null)}`);
        out(`lessons: ${l.length} active (${l.filter((x) => x.flag).length} disputed); proposals pending: ${P.list(db, "pending").length}`);
        out(`success rate: early ${pct(m.early.success)} (n=${m.early.n}) -> late ${pct(m.late.success)} (n=${m.late.n}): ${m.success_trend}`);
        out(`repeated-error rate: early ${pct(m.early.repeated_error_rate)} -> late ${pct(m.late.repeated_error_rate)}: ${m.repeated_error_trend}`);
        if (!m.enough) out("note: small numbers, no trend claim is made until both halves have enough tasks");
        return 0;
      }
      case "lessons":
        for (const x of rest.includes("--all") ? db.all<any>(`SELECT * FROM ${T}lessons ORDER BY confidence DESC`) : activeLessons(db)) out(`#${x.id} [${x.status}] c=${x.confidence.toFixed(2)} x${x.reinforced} used ${x.used}${x.flag ? ` ${x.flag}` : ""}  ${x.text}  {${x.applies_to}}`);
        return 0;
      case "history":
        for (const t of db.all<any>(`SELECT * FROM ${T}tasks ORDER BY id DESC LIMIT ?`, Number(rest[0]) || 20)) out(`#${t.id} ${when(t.ts)} ${t.outcome ?? "unreflected"} tools=${t.tools_n} errs=${t.errs_n}  ${t.prompt.slice(0, 70)}`);
        return 0;
      case "versions":
        for (const v of db.all<any>(`SELECT * FROM ${T}lesson_versions ORDER BY version DESC LIMIT ?`, Number(rest[0]) || 30)) out(`v${v.version} ${when(v.ts)} lesson #${v.lesson_id} ${v.action}${v.undone ? " (undone)" : ""}`);
        return 0;
      case "run": {
        const b = flag("--backend") ?? process.env.MG_REFLECT_BACKEND ?? "auto";
        if (!BACKENDS.includes(b)) { io.err(`backend must be ${BACKENDS.join("|")}`); return 1; }
        const r = await run(db, { llm: backendChain(b), max: Number(flag("--max")) || 20 });
        out(JSON.stringify(r)); return r.skipped && !r.reflected ? 2 : 0;
      }
      case "rollback":
        if (!Number.isInteger(id) || id < 1) { io.err("usage: rollback <version>  (undoes that lesson change and every later one; see `versions`)"); return 1; }
        out(`undone ${rollback(db, id)} lesson change(s) from v${id} on`); return 0;
      case "proposals":
        for (const p of P.list(db)) out(`#${p.id} [${p.status}] ${p.kind} ${p.file}  ${p.why.slice(0, 80)}`);
        return 0;
      case "show": {
        const p = P.get(db, id); if (!p) { io.err("no such proposal"); return 1; }
        out(`#${p.id} [${p.status}] ${p.kind} -> ${p.file}\nwhy: ${p.why}\ntest: ${p.test || "(none: cannot be applied)"}\n--- change ---\n${p.change}${p.note ? `\nnote: ${p.note}` : ""}`); return 0;
      }
      case "reject": return P.reject(db, id) ? (out(`rejected #${id}`), 0) : (io.err("not a pending proposal"), 1);
      case "revert": return P.revert(db, id) ? (out(`reverted #${id} from backup`), 0) : (io.err("not an applied proposal"), 1);
      case "apply": {
        const p = P.get(db, id); if (!p) { io.err("no such proposal"); return 1; }
        if (!process.stdin.isTTY || !process.stdout.isTTY) { io.err("refused: `apply` needs an interactive terminal and your explicit yes"); return 3; }
        out(`#${p.id} ${p.kind} -> ${p.file}\nwhy: ${p.why}\ntest: ${p.test}\n--- change ---\n${p.change.slice(0, 3000)}\nA backup is made first; if the test fails the file is restored.`);
        const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
        const r = await P.apply(db, id, { confirm: async () => /^\s*(y|yes)\s*$/i.test(await rl.question("Apply this change? (yes/no) ")) });
        rl.close(); out(`${r.status}: ${r.note}`); return r.ok ? 0 : 1;
      }
      default: io.err("usage: improve status|lessons [--all]|history [n]|versions|run [--backend B]|enable|disable|rollback <v>|proposals|show <id>|apply <id>|reject <id>|revert <id>"); return 1;
    }
  } finally { db.close(); }
}
if (import.meta.main) process.exit(await main(process.argv.slice(2)));
