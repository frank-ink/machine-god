// Machine God GitHub mailbox: other AIs (e.g. ChatGPT through its GitHub connector) leave requests in YOUR private GRID repo,
// this program picks them up and answers. Policy: READ-ONLY + ASK.
//   - a fixed allowlist of read-only commands runs automatically (inside folders you approved);
//   - everything else is shown in your terminal and runs only after you type "yes" (and never when stdin is not a terminal);
//   - a short deny list is refused even if you would say yes.
// Foreground only: no daemon, no autostart. Every request and decision is appended to <data dir>/mailbox.log.
//
// Repo layout (the GRID repo): control/<id>.json  {"cmd": "..."} or {"question": "..."}, plus {"from": "name"}
//                              results/<id>.json  written by this program
//   machine-god mailbox            run the loop (polls git every 30 s)
//   machine-god mailbox once       one round, then exit
//   machine-god mailbox approve <dir> | revoke <dir> | status
//   machine-god mailbox questions confirm|auto|off   how {"question"} requests are answered once your AIs are fused (machine-god grid fuse):
//       confirm (default) = the GRID drafts an answer from the shared memory and an AI, you see it and type yes (or your own answer); auto = it is sent without asking
//       (text only, it can never run anything; the answer may contain things from your memory, so only enable it for a repo only you can write to); off = old behaviour, you type the answer.
// Test switches: MG_GRID_DIR (clone to use), MG_MAILBOX_POLL_S, MG_CONFIG_DIR / MG_DATA_DIR.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { spawnSync } from "node:child_process";
import { resolvePaths } from "../firstrun/mg-common.js";

export const MAX_REQUEST_BYTES = 16 * 1024;
export const MAX_OUTPUT = 64 * 1024;
export const SHELL_TIMEOUT_MS = 120_000;
export const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;

// ---------- deny list (ported from the original bridge daemon, plus a few more catastrophic or secret-reading ones) ----------
export const DENY_PATTERNS = [
  /rm\s+-rf\s+\/(\s|$)/,
  /rm\s+-rf\s+\/\*/,
  /mkfs\./,
  /dd\s+.*of=\/dev\//,
  /:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:/, // fork bomb
  /chmod\s+-R\s+000\s+\//,
  />\s*\/dev\/sd[a-z]/,
  /rm\s+-[a-z]*r[a-z]*f?\s+(~|\$HOME|\/home|\/Users)(\/\*?)?(\s|$)/i,
  /\b(format\s+[a-z]:|del\s+\/[sq].*[a-z]:\\|rd\s+\/s\s+\/q\s+[a-z]:\\)/i,
  /(^|[;&|]\s*|sudo\s+)(shutdown|reboot|poweroff|halt)(\s|$)/,
  /(curl|wget|iwr|Invoke-WebRequest)[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b/,
  // secrets stay local: no command may touch private keys, API keys or tokens
  /(\.ssh[\\/]|id_(rsa|ed25519|ecdsa|dsa)|keys\.json|bridge\.token|\.netrc|\.aws[\\/]credentials|\.gnupg)/,
];
export const deniedBy = (cmd) => {
  for (const p of DENY_PATTERNS) if (p.test(cmd)) return String(p);
  return null;
};

const SENSITIVE_NAME = /^(\.env(\..*)?|keys\.json|bridge\.token|\.netrc|id_(rsa|ed25519|ecdsa|dsa).*|.*\.pem|.*\.key)$/i;
const SENSITIVE_DIR = new Set([".ssh", ".gnupg", ".aws"]);
export function isSensitivePath(p, protectedDirs = []) {
  const parts = p.split(/[\\/]+/).filter(Boolean);
  if (parts.some((s) => SENSITIVE_DIR.has(s))) return true;
  if (SENSITIVE_NAME.test(parts[parts.length - 1] || "")) return true;
  return protectedDirs.some((d) => d && (p === d || p.startsWith(d + path.sep)));
}

// ---------- paths and workspaces ----------
const realOrNull = (p) => {
  try {
    return fs.realpathSync(p);
  } catch {
    return null;
  }
};
export function isInside(child, parent) {
  const rel = path.relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}
/** Resolve p (relative to cwd) to a real path inside one of the approved workspaces. -> {real} | {error} */
export function resolveInWorkspace(p, cwd, workspaces, protectedDirs = []) {
  if (!workspaces.length) return { error: "no approved workspace (run: machine-god mailbox approve <dir>)", code: "no-workspace" };
  const real = realOrNull(path.resolve(cwd, p));
  if (!real) return { error: `no such path: ${p}`, code: "missing" };
  const roots = workspaces.map(realOrNull).filter(Boolean);
  if (!roots.some((r) => isInside(real, r))) return { error: `outside the approved workspaces: ${p}`, code: "outside-workspace" };
  if (isSensitivePath(real, protectedDirs)) return { error: `refusing sensitive path: ${p}`, code: "sensitive" };
  return { real };
}

export const configFile = (configDir) => path.join(configDir, "mailbox.json");
export function loadConfig(configDir) {
  try {
    const c = JSON.parse(fs.readFileSync(configFile(configDir), "utf8"));
    return {
      workspaces: Array.isArray(c.workspaces) ? c.workspaces.filter((x) => typeof x === "string") : [],
      gridQuestions: ["confirm", "auto", "off"].includes(c.gridQuestions) ? c.gridQuestions : "confirm",
    };
  } catch {
    return { workspaces: [], gridQuestions: "confirm" };
  }
}
export function saveConfig(configDir, cfg) {
  fs.mkdirSync(configDir, { recursive: true });
  const f = configFile(configDir);
  const tmp = `${f}.tmp.${process.pid}`;
  fs.writeFileSync(tmp, JSON.stringify({ workspaces: cfg.workspaces, gridQuestions: cfg.gridQuestions || "confirm" }, null, 2) + "\n", { mode: 0o600 });
  fs.renameSync(tmp, f);
}
export function approveWorkspace(configDir, dir, home = os.homedir()) {
  const real = realOrNull(dir);
  if (!real || !fs.statSync(real).isDirectory()) throw new Error(`not a directory: ${dir}`);
  if (real === path.parse(real).root || real === realOrNull(home)) throw new Error("refusing to approve the filesystem root or your whole home directory; pick a project folder");
  if (isSensitivePath(real)) throw new Error("refusing a sensitive directory");
  const cfg = loadConfig(configDir);
  if (!cfg.workspaces.includes(real)) cfg.workspaces.push(real);
  saveConfig(configDir, cfg);
  return real;
}
export function revokeWorkspace(configDir, dir) {
  const cfg = loadConfig(configDir);
  const real = realOrNull(dir) || dir;
  const before = cfg.workspaces.length;
  cfg.workspaces = cfg.workspaces.filter((w) => w !== real && w !== dir);
  saveConfig(configDir, cfg);
  return before - cfg.workspaces.length;
}

// ---------- classification ----------
const UNSAFE_CHARS = /[;&|<>$`(){}\\\n\r*?~!"'#\0]/;
const LS_FLAGS = new Set(["-l", "-a", "-la", "-al", "-1", "-h", "-lh", "-hl", "-lah", "-alh"]);

/**
 * -> { verdict: "deny"|"allow"|"ask", reason, plan? }
 * allow = on the read-only allowlist AND every path is inside an approved workspace; it carries a native plan, no shell is used.
 */
export function classify(cmd, { workspaces = [], cwd = null, protectedDirs = [], platform = process.platform } = {}) {
  if (typeof cmd !== "string" || !cmd.trim()) return { verdict: "deny", reason: "empty-command" };
  if (cmd.length > 1000 || cmd.includes("\0")) return { verdict: "deny", reason: "too-long-or-binary" };
  const d = deniedBy(cmd);
  if (d) return { verdict: "deny", reason: `deny-pattern ${d}` };
  if (UNSAFE_CHARS.test(cmd)) return { verdict: "ask", reason: "not-allowlisted (shell syntax)" };
  const t = cmd.trim().split(/\s+/);
  const [name, ...a] = t;
  const base = workspaces[0];
  const wd = cwd || base || process.cwd();
  const inWs = (p) => resolveInWorkspace(p, wd, workspaces, protectedDirs);
  const askWith = (reason) => ({ verdict: "ask", reason });
  const needPath = (p) => {
    const r = inWs(p);
    return r.error ? { fail: r } : { real: r.real };
  };

  if (name === "uname") {
    if (a.length > 1 || (a[0] && !["-a", "-s", "-r", "-m"].includes(a[0]))) return askWith("not-allowlisted (uname args)");
    return { verdict: "allow", reason: "allowlist uname", plan: { kind: "uname", flag: a[0] || "-s" } };
  }
  if (name === "df") {
    if (platform === "win32") return askWith("not-allowlisted (df on Windows)");
    if (a.length === 0 || (a.length === 1 && a[0] === "-h")) return { verdict: "allow", reason: "allowlist df", plan: { kind: "df" } };
    return askWith("not-allowlisted (df args)");
  }
  if (name === "ls") {
    const flags = a.filter((x) => x.startsWith("-"));
    const paths = a.filter((x) => !x.startsWith("-"));
    if (flags.some((f) => !LS_FLAGS.has(f)) || paths.length > 1) return askWith("not-allowlisted (ls args)");
    const r = needPath(paths[0] || ".");
    if (r.fail) return r.fail.code === "outside-workspace" || r.fail.code === "no-workspace" ? askWith(r.fail.error) : { verdict: "deny", reason: r.fail.error };
    return { verdict: "allow", reason: "allowlist ls", plan: { kind: "ls", real: r.real, long: flags.some((f) => f.includes("l")), all: flags.some((f) => f.includes("a")) } };
  }
  if (name === "cat" || name === "head") {
    let n = 10;
    let rest = a;
    if (name === "head" && a[0] === "-n") {
      n = Number(a[1]);
      if (!Number.isInteger(n) || n < 1 || n > 500) return askWith("not-allowlisted (head -n)");
      rest = a.slice(2);
    }
    if (rest.length !== 1 || rest[0].startsWith("-")) return askWith(`not-allowlisted (${name} args)`);
    const r = needPath(rest[0]);
    if (r.fail) return r.fail.code === "outside-workspace" || r.fail.code === "no-workspace" ? askWith(r.fail.error) : { verdict: "deny", reason: r.fail.error };
    return { verdict: "allow", reason: `allowlist ${name}`, plan: { kind: name, real: r.real, lines: name === "head" ? n : null } };
  }
  if (name === "git") {
    const sub = a[0];
    let args = null;
    if (sub === "status" && a.slice(1).every((x) => ["-s", "--short", "-b", "--branch", "--porcelain"].includes(x))) args = ["status", ...a.slice(1)];
    if (sub === "log") {
      const rest = a.slice(1);
      const ok = rest.every((x, i) => x === "--oneline" || /^-\d{1,3}$/.test(x) || (x === "-n" && /^\d{1,3}$/.test(rest[i + 1] || "")) || (i > 0 && rest[i - 1] === "-n" && /^\d{1,3}$/.test(x)));
      if (ok) args = ["log", ...rest];
    }
    if (!args) return askWith("not-allowlisted (git args)");
    const r = needPath(".");
    if (r.fail) return r.fail.code === "outside-workspace" || r.fail.code === "no-workspace" ? askWith(r.fail.error) : { verdict: "deny", reason: r.fail.error };
    return { verdict: "allow", reason: `allowlist git ${sub}`, plan: { kind: "git", real: r.real, args } };
  }
  return askWith("not-allowlisted");
}

// ---------- execution ----------
const cap = (s) => (s.length > MAX_OUTPUT ? s.slice(0, MAX_OUTPUT) : s);
const ok = (stdout) => ({ exit_code: 0, stdout: cap(stdout), stderr: "", truncated: stdout.length > MAX_OUTPUT });
const fail = (msg, code = 1) => ({ exit_code: code, stdout: "", stderr: msg, truncated: false });

export function runPlan(plan) {
  try {
    switch (plan.kind) {
      case "uname": {
        const f = plan.flag;
        const parts = { "-s": os.type(), "-r": os.release(), "-m": os.arch() };
        if (f === "-a") return ok(`${os.type()} ${os.hostname()} ${os.release()} ${os.arch()}\n`);
        return ok(parts[f] + "\n");
      }
      case "df": {
        const r = spawnSync("df", ["-h"], { encoding: "utf8", timeout: 10_000 });
        return r.status === 0 ? ok(r.stdout) : fail(r.stderr || "df failed", r.status ?? 1);
      }
      case "ls": {
        const st = fs.statSync(plan.real);
        if (!st.isDirectory()) return ok(path.basename(plan.real) + "\n");
        let names = fs.readdirSync(plan.real, { withFileTypes: true });
        if (!plan.all) names = names.filter((d) => !d.name.startsWith("."));
        names.sort((x, y) => x.name.localeCompare(y.name));
        const shown = names.slice(0, 500).map((d) => {
          const nm = d.name + (d.isDirectory() ? "/" : "");
          if (!plan.long) return nm;
          let size = 0;
          let m = "";
          try {
            const s = fs.statSync(path.join(plan.real, d.name));
            size = s.size;
            m = s.mtime.toISOString().slice(0, 16).replace("T", " ");
          } catch {}
          return `${String(size).padStart(10)} ${m} ${nm}`;
        });
        return ok(shown.join("\n") + (names.length > 500 ? `\n... ${names.length - 500} more` : "") + "\n");
      }
      case "cat":
      case "head": {
        const st = fs.statSync(plan.real);
        if (!st.isFile()) return fail("not a regular file");
        const fd = fs.openSync(plan.real, "r");
        const buf = Buffer.alloc(Math.min(st.size, MAX_OUTPUT + 1));
        fs.readSync(fd, buf, 0, buf.length, 0);
        fs.closeSync(fd);
        if (buf.includes(0)) return fail("binary file, not shown");
        let text = buf.toString("utf8");
        if (plan.lines) text = text.split("\n").slice(0, plan.lines).join("\n") + "\n";
        return { exit_code: 0, stdout: cap(text), stderr: "", truncated: text.length > MAX_OUTPUT || st.size > MAX_OUTPUT };
      }
      case "git": {
        const r = spawnSync("git", ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.pager=cat", "-C", plan.real, ...plan.args], {
          encoding: "utf8", timeout: 15_000, env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_OPTIONAL_LOCKS: "0" },
        });
        if (r.error) return fail(String(r.error.message || r.error));
        return { exit_code: r.status ?? 1, stdout: cap(r.stdout || ""), stderr: cap(r.stderr || ""), truncated: (r.stdout || "").length > MAX_OUTPUT };
      }
    }
  } catch (e) {
    return fail(String(e.message || e).slice(0, 300));
  }
  return fail("unknown plan");
}

/** Only called after the user typed yes. Runs the command in a shell, in cwd. */
export function runShell(cmd, cwd) {
  const win = process.platform === "win32";
  const r = spawnSync(win ? "cmd.exe" : "sh", win ? ["/d", "/s", "/c", cmd] : ["-c", cmd], {
    cwd, encoding: "utf8", timeout: SHELL_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024, windowsHide: true,
  });
  if (r.error && r.error.code === "ETIMEDOUT") return { exit_code: 124, stdout: cap(r.stdout || ""), stderr: "timeout after 120 s", truncated: false };
  if (r.error) return fail(String(r.error.message || r.error).slice(0, 300));
  return { exit_code: r.status ?? 1, stdout: cap(r.stdout || ""), stderr: cap(r.stderr || ""), truncated: (r.stdout || "").length > MAX_OUTPUT };
}

// ---------- one request ----------
const clean = (s, max = 2000) => String(s).replace(/\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b./g, "").replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "?").slice(0, max);

export function parseRequest(raw, fileId) {
  if (raw.length > MAX_REQUEST_BYTES) return { error: "request file too large" };
  let j;
  try {
    j = JSON.parse(raw);
  } catch {
    return { error: "not valid JSON" };
  }
  if (!j || typeof j !== "object" || Array.isArray(j)) return { error: "not a JSON object" };
  if (j.id !== undefined && String(j.id) !== fileId) return { error: "id does not match the file name" };
  const from = typeof j.from === "string" && j.from.trim() ? clean(j.from, 60) : "unknown";
  const hasCmd = typeof j.cmd === "string" && !!j.cmd.trim();
  const hasQ = typeof j.question === "string" && !!j.question.trim();
  if (hasCmd === hasQ) return { error: "needs exactly one of cmd or question" };
  const cwd = typeof j.cwd === "string" ? j.cwd : null;
  return hasCmd ? { id: fileId, from, kind: "cmd", cmd: j.cmd, cwd } : { id: fileId, from, kind: "question", question: j.question };
}

/**
 * -> result object (written to results/<id>.json). interactive + askUser(kind, text, meta) -> string|null are the only way anything
 * outside the allowlist can run. runShellFn is injectable for tests.
 */
export async function handleRequest(req, { cfg, protectedDirs = [], interactive, askUser, runShellFn = runShell, log = () => {}, now = () => new Date().toISOString(), gridAnswer = null }) {
  const base = { id: req.id, from: req.from, kind: req.kind };
  const done = (r, decision, reason) => {
    const res = { ...base, status: r.status, decision, ...(reason ? { reason } : {}), ...(r.exit_code !== undefined ? { exit_code: r.exit_code, stdout: r.stdout, stderr: r.stderr, truncated: r.truncated } : {}), ...(r.answer !== undefined ? { answer: r.answer } : {}), finished_at: now() };
    log({ id: req.id, from: req.from, kind: req.kind, text: clean(req.cmd ?? req.question, 300), decision, reason: reason || "", status: r.status, exit: r.exit_code });
    return res;
  };
  if (req.kind === "question") {
    // fused AIs: the GRID drafts the answer (shared memory + the best-fitting AI). Text only; confirm = you decide, auto = you opted in, off = old behaviour
    const mode = cfg.gridQuestions || "confirm";
    if (gridAnswer && mode !== "off") {
      let draft = "";
      let failed = "";
      try {
        draft = String((await gridAnswer(clean(req.question), req.from)) || "").trim();
      } catch (e) {
        failed = String(e.message || e).slice(0, 160);
      }
      if (draft) {
        if (mode === "auto") return done({ status: "answered", answer: clean(draft, 4000) }, "grid-auto");
        if (!interactive) return done({ status: "rejected" }, "no-tty", "questions need a person at the terminal (or: machine-god mailbox questions auto)");
        const ans = await askUser("draft", clean(req.question), { from: req.from, id: req.id, draft: clean(draft, 4000) });
        if (ans && ans.trim().toLowerCase() === "yes") return done({ status: "answered", answer: clean(draft, 4000) }, "grid-confirmed");
        if (ans && ans.trim()) return done({ status: "answered", answer: clean(ans, 4000) }, "user-answered");
        return done({ status: "declined" }, "user-declined");
      }
      log({ id: req.id, decision: "grid-failed", reason: failed || "empty draft" });
    }
    if (!interactive) return done({ status: "rejected" }, "no-tty", "questions need a person at the terminal");
    const ans = await askUser("question", clean(req.question), { from: req.from, id: req.id });
    if (ans && ans.trim()) return done({ status: "answered", answer: clean(ans, 4000) }, "user-answered");
    return done({ status: "declined" }, "user-declined");
  }
  let cwd = null;
  if (req.cwd) {
    const r = resolveInWorkspace(req.cwd, cfg.workspaces[0] || process.cwd(), cfg.workspaces, protectedDirs);
    if (r.error) return done({ status: "rejected" }, "bad-cwd", r.error);
    cwd = r.real;
  }
  const c = classify(req.cmd, { workspaces: cfg.workspaces, cwd, protectedDirs });
  if (c.verdict === "deny") return done({ status: "denied" }, "denied", c.reason);
  if (c.verdict === "allow") {
    const out = runPlan(c.plan);
    return done({ status: out.exit_code === 0 ? "ok" : "failed", ...out }, "allowlist", c.reason);
  }
  if (!interactive) return done({ status: "rejected" }, "no-tty", `${c.reason}; nothing outside the allowlist runs without a terminal and your yes`);
  const ans = await askUser("cmd", clean(req.cmd), { from: req.from, id: req.id, reason: c.reason, cwd: cwd || cfg.workspaces[0] || process.cwd() });
  if (!ans || ans.trim().toLowerCase() !== "yes") return done({ status: "declined" }, "user-no", c.reason);
  const out = runShellFn(req.cmd, cwd || cfg.workspaces[0] || os.homedir());
  return done({ status: out.exit_code === 0 ? "ok" : "failed", ...out }, "user-yes", c.reason);
}

// ---------- git transport ----------
function git(dir, args, { timeout = 120_000, ident = false } = {}) {
  const pre = ident ? ["-c", "user.name=Machine God", "-c", "user.email=machine-god@users.noreply.github.com"] : [];
  const r = spawnSync("git", [...pre, "-C", dir, ...args], { encoding: "utf8", timeout, env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } });
  return { code: r.status ?? -1, out: (r.stdout || "") + (r.stderr || "") };
}
export const currentBranch = (dir) => git(dir, ["symbolic-ref", "--short", "HEAD"]).out.trim() || "main";
export function gitIdentArgs(dir) {
  const has = (k) => git(dir, ["config", k]).out.trim();
  return has("user.name") && has("user.email");
}

export function syncDown(dir) {
  const br = currentBranch(dir);
  const remote = git(dir, ["ls-remote", "--heads", "origin", br]);
  if (remote.code !== 0) return { ok: false, detail: remote.out.trim().slice(0, 200) };
  if (!remote.out.trim()) return { ok: true, detail: "remote branch empty" };
  const r = git(dir, ["pull", "--rebase", "--autostash", "--quiet", "origin", br], { ident: true });
  return { ok: r.code === 0, detail: r.out.trim().slice(0, 200) };
}
export function pushResults(dir, message) {
  const br = currentBranch(dir);
  git(dir, ["add", "results"]);
  if (git(dir, ["diff", "--cached", "--quiet"]).code === 0) return { ok: true, detail: "nothing to push" };
  const c = git(dir, ["commit", "-q", "-m", message], { ident: !gitIdentArgs(dir) });
  if (c.code !== 0) return { ok: false, detail: c.out.trim().slice(0, 200) };
  let p = git(dir, ["push", "-q", "origin", `HEAD:${br}`]);
  if (p.code !== 0) {
    git(dir, ["pull", "--rebase", "--autostash", "--quiet", "origin", br], { ident: true });
    p = git(dir, ["push", "-q", "origin", `HEAD:${br}`]);
  }
  return { ok: p.code === 0, detail: p.out.trim().slice(0, 200) };
}

/** One round: pull, answer every control/<id>.json without results/<id>.json, push. -> { handled, results, error? } */
export async function pollOnce({ dir, cfg, protectedDirs = [], interactive, askUser, runShellFn, log = () => {}, push = true, now, gridAnswer = null }) {
  const sync = syncDown(dir);
  if (!sync.ok) return { handled: 0, results: [], error: `git pull failed: ${sync.detail}` };
  const cdir = path.join(dir, "control");
  const rdir = path.join(dir, "results");
  if (!fs.existsSync(cdir)) return { handled: 0, results: [] };
  fs.mkdirSync(rdir, { recursive: true });
  const results = [];
  for (const name of fs.readdirSync(cdir).sort()) {
    if (!name.endsWith(".json")) continue;
    const id = name.slice(0, -5);
    if (!ID_RE.test(id)) continue;
    const out = path.join(rdir, `${id}.json`);
    if (fs.existsSync(out)) continue;
    const file = path.join(cdir, name);
    let raw;
    try {
      if (fs.lstatSync(file).isSymbolicLink()) throw new Error("symlink");
      raw = fs.readFileSync(file, "utf8");
    } catch (e) {
      raw = "";
    }
    const req = parseRequest(raw, id);
    const result = req.error
      ? (log({ id, decision: "bad-request", reason: req.error }), { id, status: "rejected", decision: "bad-request", reason: req.error, finished_at: (now || (() => new Date().toISOString()))() })
      : await handleRequest(req, { cfg, protectedDirs, interactive, askUser, runShellFn, log, now, gridAnswer });
    fs.writeFileSync(out, JSON.stringify(result, null, 2) + "\n");
    results.push(result);
  }
  if (results.length && push) {
    const p = pushResults(dir, `mailbox: ${results.length} result(s)`);
    if (!p.ok) return { handled: results.length, results, error: `git push failed: ${p.detail}` };
  }
  return { handled: results.length, results };
}

// ---------- terminal ----------
export function makeUserPrompt({ input = process.stdin, output = process.stdout } = {}) {
  let rl = null;
  return async (kind, text, meta) => {
    rl ||= readline.createInterface({ input, output, terminal: false });
    const w = (s) => output.write(s + "\n");
    w("");
    w(`[mailbox] request ${meta.id} from "${meta.from}"`);
    if (kind === "cmd") {
      w(`  wants to run: ${text}`);
      w(`  in: ${meta.cwd}`);
      w(`  why you are asked: ${meta.reason}`);
      output.write("  Type yes to run it (anything else rejects): ");
    } else if (kind === "draft") {
      w(`  asks you: ${text}`);
      w(`  the GRID drafted this answer (shared memory + ${"the best-fitting connected AI"}):`);
      for (const l of String(meta.draft).split("\n")) w(`    | ${l}`);
      output.write("  Type yes to send it, type your own answer instead, or press Enter to decline: ");
    } else {
      w(`  asks you: ${text}`);
      output.write("  Your answer (empty = decline): ");
    }
    return await new Promise((resolve) => {
      rl.once("line", resolve);
      rl.once("close", () => resolve(""));
    });
  };
}

export function gridDirFor(env = process.env, paths = resolvePaths({ env })) {
  if (env.MG_GRID_DIR) return env.MG_GRID_DIR;
  try {
    const g = JSON.parse(fs.readFileSync(path.join(paths.configDir, "grid.json"), "utf8"));
    if (g.dir) return g.dir;
  } catch {}
  return path.join(paths.dataDir, "grid");
}

export function makeLogger(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  const f = path.join(dataDir, "mailbox.log");
  return (entry) => {
    try {
      fs.appendFileSync(f, JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n", { mode: 0o600 });
    } catch {}
  };
}

/** After `machine-god grid fuse`: a function (question, from) -> answer text that asks the GRID (memory + routing). Null when not fused. */
export async function makeGridAnswer(env = process.env, openOpts = {}) {
  try {
    const { gridEnabled, openGrid } = await import("../grid/core.js");
    if (!gridEnabled(env)) return null;
    return async (question, from) => {
      const g = openGrid({ env, ...openOpts });
      try {
        // learn:false = the requester cannot make Machine God save anything; the question and answer are still recorded as a turn
        const r = await g.ask(question, { asker: `mailbox:${String(from).slice(0, 30)}`, learn: false });
        return `${r.answer}\n\n(Machine God, answered by ${r.ai})`;
      } finally {
        g.close();
      }
    };
  } catch {
    return null;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function main(argv = process.argv.slice(2), env = process.env, out = process.stdout) {
  const w = (s = "") => out.write(s + "\n");
  const paths = resolvePaths({ env });
  const [cmd = "run", ...rest] = argv;
  const home = env.HOME || env.USERPROFILE || os.homedir();
  switch (cmd) {
    case "approve":
      try {
        w(`approved workspace: ${approveWorkspace(paths.configDir, rest[0] || "", home)}`);
        return 0;
      } catch (e) {
        w(`not approved: ${e.message}`);
        return 1;
      }
    case "revoke":
      w(revokeWorkspace(paths.configDir, rest[0] || "") ? "revoked" : "was not approved");
      return 0;
    case "status": {
      const dir = gridDirFor(env, paths);
      w(`GRID clone: ${dir} ${fs.existsSync(path.join(dir, ".git")) ? "(present)" : "(missing; run: machine-god grid repo)"}`);
      const cfg = loadConfig(paths.configDir);
      w(`approved workspaces: ${cfg.workspaces.length ? cfg.workspaces.join(", ") : "none (file and git commands will ask you; approve with: machine-god mailbox approve <dir>)"}`);
      w(`questions: ${cfg.gridQuestions} (GRID answers questions only after: machine-god grid fuse; change: machine-god mailbox questions confirm|auto|off)`);
      w(`log: ${path.join(paths.dataDir, "mailbox.log")}`);
      return 0;
    }
    case "questions": {
      const mode = rest[0];
      if (!["confirm", "auto", "off"].includes(mode)) {
        w(`question answers via the GRID: ${loadConfig(paths.configDir).gridQuestions} (change: machine-god mailbox questions confirm|auto|off)`);
        return rest.length ? 1 : 0;
      }
      saveConfig(paths.configDir, { ...loadConfig(paths.configDir), gridQuestions: mode });
      w(`question answers via the GRID: ${mode}`);
      return 0;
    }
    case "run":
    case "once":
      break;
    default:
      w("usage: machine-god mailbox [run|once|approve <dir>|revoke <dir>|questions confirm|auto|off|status]");
      return cmd === "help" || cmd === "--help" ? 0 : 1;
  }
  const dir = gridDirFor(env, paths);
  if (!fs.existsSync(path.join(dir, ".git"))) {
    w(`No GRID repo clone at ${dir}. Set it up first: machine-god grid repo`);
    return 1;
  }
  const interactive = !!(process.stdin.isTTY && process.stdout.isTTY);
  const log = makeLogger(paths.dataDir);
  const protectedDirs = [paths.configDir, paths.dataDir].map((d) => realOrNull(d) || d);
  const askUser = interactive ? makeUserPrompt() : null;
  const poll = Math.max(1, Number(env.MG_MAILBOX_POLL_S) || 30);
  const gridAnswer = await makeGridAnswer(env);
  w("Machine God mailbox (foreground). Policy: other AIs may only READ; everything else needs your yes here.");
  w(`GRID clone: ${dir}`);
  const cfg0 = loadConfig(paths.configDir);
  w(`approved workspaces: ${cfg0.workspaces.length ? cfg0.workspaces.join(", ") : "none"}`);
  w(interactive ? `Terminal detected: non-allowlisted requests will ask you. Polling every ${poll} s, Ctrl-C to stop.` : "No terminal on stdin: only allowlisted read-only requests run, everything else is rejected.");
  let stop = false;
  process.once("SIGINT", () => (stop = true));
  for (;;) {
    const cfg = loadConfig(paths.configDir); // re-read: approve/revoke apply without restart
    const r = await pollOnce({ dir, cfg, protectedDirs, interactive, askUser, log, gridAnswer });
    if (r.error) w(`[mailbox] ${r.error}`);
    for (const x of r.results) w(`[mailbox] ${x.id}: ${x.status} (${x.decision})`);
    if (cmd === "once" || stop) break;
    for (let i = 0; i < poll * 10 && !stop; i++) await sleep(100);
    if (stop) break;
  }
  return 0;
}

if (import.meta.main) {
  main().then((c) => process.exit(c), (e) => {
    process.stderr.write(`mailbox: ${String(e.message || e).slice(0, 300)}\n`);
    process.exit(1);
  });
}
