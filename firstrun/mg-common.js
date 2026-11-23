// Shared by the first-run companion, the GitHub step, the fusion step and the CLIs (no side effects on import).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { spawn } from "node:child_process";

// ---------- paths ----------
export function resolvePaths({ platform = process.platform, env = process.env, home = os.homedir() } = {}) {
  let configDir;
  let dataDir;
  if (platform === "win32") {
    configDir = path.win32.join(env.APPDATA || path.win32.join(home, "AppData", "Roaming"), "machine-god");
    dataDir = path.win32.join(env.LOCALAPPDATA || path.win32.join(home, "AppData", "Local"), "machine-god");
  } else {
    configDir = path.join(env.XDG_CONFIG_HOME || path.join(home, ".config"), "machine-god");
    dataDir = path.join(env.XDG_DATA_HOME || path.join(home, ".local", "share"), "machine-god");
  }
  if (env.MG_CONFIG_DIR) configDir = env.MG_CONFIG_DIR;
  if (env.MG_DATA_DIR) dataDir = env.MG_DATA_DIR;
  const j = platform === "win32" && !env.MG_CONFIG_DIR ? path.win32.join : path.join;
  return { configDir, dataDir, stateFile: j(configDir, "firstrun.json") };
}

/** The user's home directory (HOME on Unix, USERPROFILE on Windows); tests point HOME at a temp dir. */
export function homeDir(env = process.env, platform = process.platform) {
  return (platform === "win32" ? env.USERPROFILE : env.HOME) || os.homedir();
}

// ---------- questions ----------
export function isYes(s) {
  return /^\s*(y|yes|j|ja|ok|sure)\s*$/i.test(s || "");
}

const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;

/**
 * ask(q) -> bool (yes/no); ask.text(q) -> string; ask.secret(q) -> string (hidden input, never echoed);
 * scripted with MG_FIRSTRUN_ANSWERS=a,b,c (shared queue; exhausted -> "no" / ""). Secrets are scripted only for tests with mock values.
 */
export function makeAsker({ env = process.env, input = process.stdin, output = process.stdout } = {}) {
  const scripted = env.MG_FIRSTRUN_ANSWERS ? env.MG_FIRSTRUN_ANSWERS.split(",").map((s) => s.trim()) : null;
  let rl = null;
  const queue = [];
  const waiters = [];
  let closed = false;
  const open = () => {
    if (rl) return;
    rl = readline.createInterface({ input, output, terminal: false });
    closed = false;
    rl.on("line", (l) => (waiters.length ? waiters.shift()(l) : queue.push(l)));
    rl.on("close", () => {
      closed = true;
      while (waiters.length) waiters.shift()("");
    });
  };
  const line = () => {
    open();
    if (queue.length) return Promise.resolve(queue.shift());
    if (closed) return Promise.resolve("");
    return new Promise((r) => waiters.push(r));
  };
  const next = (shown) => {
    const a = scripted.length ? scripted.shift() : "";
    output.write(shown ? `${a}\n` : "(hidden)\n");
    return a;
  };
  const ask = async (q) => {
    output.write(q + " ");
    if (scripted) return isYes(next(true));
    return isYes(await line());
  };
  ask.text = async (q) => {
    output.write(q + " ");
    return scripted ? next(true) : (await line()).trim();
  };
  ask.secret = async (q) => {
    output.write(q + " ");
    if (scripted) return next(false);
    if (!input.isTTY || typeof input.setRawMode !== "function") {
      output.write("(no terminal, not reading a secret)\n");
      return "";
    }
    if (rl) {
      rl.close();
      rl = null;
    }
    return await new Promise((resolve) => {
      let buf = "";
      let esc = "";
      input.setRawMode(true);
      input.resume();
      input.setEncoding("utf8");
      const end = (v) => {
        input.off("data", onData);
        input.setRawMode(false);
        input.pause();
        output.write("\n");
        resolve(v);
      };
      const onData = (chunk) => {
        for (const ch of (esc + chunk).replace(ANSI, "")) {
          if (ch === "\r" || ch === "\n") return end(buf);
          if (ch === "\u0003" || ch === "\u0004") return end("");
          if (ch === "\u007f" || ch === "\b") buf = buf.slice(0, -1);
          else if (ch >= " " && ch !== "\u007f") buf += ch;
        }
        esc = "";
      };
      input.on("data", onData);
    });
  };
  // call before a child process that reads the terminal itself (passphrase, login): we stop listening on stdin
  ask.suspend = () => {
    if (rl) {
      rl.close();
      rl = null;
    }
  };
  ask.close = () => rl && rl.close();
  return ask;
}

// ---------- processes ----------
export function whichSync(name, env = process.env, platform = process.platform) {
  const win = platform === "win32";
  const exts = win ? (env.PATHEXT || ".EXE;.CMD").split(";") : [""];
  for (const dir of (env.PATH || "").split(win ? ";" : ":")) {
    if (!dir) continue;
    for (const ext of exts) {
      const p = path.join(dir, name + ext);
      try {
        if (fs.statSync(p).isFile()) return p;
      } catch {}
    }
  }
  return null;
}

/** Run a program. opts.stdio "inherit" lets the user see and answer prompts (passphrases, logins) themselves; otherwise output is captured. */
export function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: opts.stdio || [opts.input ? "pipe" : "ignore", "pipe", "pipe"], env: { ...process.env, ...(opts.env || {}) }, windowsHide: true, cwd: opts.cwd });
    let out = "";
    child.stdout?.on("data", (d) => (out += d));
    child.stderr?.on("data", (d) => (out += d));
    if (opts.input) child.stdin.end(opts.input);
    child.on("error", (e) => resolve({ code: -1, out: String(e) }));
    child.on("close", (code) => resolve({ code, out }));
  });
}
