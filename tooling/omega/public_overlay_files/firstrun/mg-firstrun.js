// Machine God first-run companion. Run by the `machine-god` launcher with the bundled Bun runtime, before machine-god-core.
//
// What it does, in order, and only when a person is at the terminal:
//   1. Looks for the ChatGPT desktop app (or an open window titled ChatGPT). Nothing else is inspected:
//      no browser cookies, history, profiles or logins. If nothing is found it asks once.
//   2. After an explicit yes it downloads a small local model (812 MB) and lets it greet you.
//   3. The greeting offers an optional ChatGPT bridge. The bridge is set up only after another explicit yes.
// Every answer is remembered in firstrun.json, so this runs at most once. It never blocks machine-god-core: any error
// or Ctrl-C ends the companion and Machine God starts normally.
//
// Test switches: MG_FIRSTRUN_FORCE=1 (ignore state and TTY check), MG_FIRSTRUN_ANSWERS=yes,no,... (scripted answers),
// MG_CONFIG_DIR / MG_DATA_DIR (relocate state and data), MG_FIRSTRUN_OFF=1 (skip entirely), MG_FIRSTRUN_LOGIN_WAIT_S (seconds to wait for the ChatGPT login).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import net from "node:net";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { runGithubStep } from "./mg-github.js";
import { runAisStep } from "../fusion/ais.js";
import { runGridStep } from "../grid/setup.js";

export const STATE_VERSION = 2;
export const RELEASE_BASE = "https://github.com/frank-ink/machine-god/releases/download/models-v1";
export const MODEL = {
  file: "Qwen3.5-0.8B-omega-organ-r4.Q8_0.gguf",
  size: 811842976,
  sha256: "ed390ddfdc44ad1cb4e00bcfa0592f4f36d182a83d7e68b6cabba09499c2cd0d",
};
export const LLAMA_TAG = "b12651";
const LLAMA_BASE = `https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_TAG}`;
// Official ggml-org/llama.cpp release assets, CPU builds. sha256 computed by downloading each asset once.
export const LLAMA_ASSETS = {
  "linux-x64": { name: `llama-${LLAMA_TAG}-bin-ubuntu-x64.tar.gz`, sha256: "17b242259181d5b1b1f7719aba27929700a8b0dab39bfaef1b971a992b397b38" },
  "linux-arm64": { name: `llama-${LLAMA_TAG}-bin-ubuntu-arm64.tar.gz`, sha256: "b4a8d17e16a1b42f6a1395dc5cd6967ec0d98005eb3be85b7eb893b082306ed4" },
  "darwin-arm64": { name: `llama-${LLAMA_TAG}-bin-macos-arm64.tar.gz`, sha256: "264fd872de61679c45ad57e1e21c2a2a54e29b35734ecf3d50f24166447ab8d2" },
  "darwin-x64": { name: `llama-${LLAMA_TAG}-bin-macos-x64.tar.gz`, sha256: "34c19771545479a783d3b68c446383ab703033890c052d3ff0b860a5c9f59e56" },
  "win32-x64": { name: `llama-${LLAMA_TAG}-bin-win-cpu-x64.zip`, sha256: "b2d794fa7587aba29f654d717ff9b73e31caeabf50a7766692903008bbe0855d" },
  "win32-arm64": { name: `llama-${LLAMA_TAG}-bin-win-cpu-arm64.zip`, sha256: "756a62761e476536f007c866d46fa14125f6ca32d98cee6af14685659bd9f244" },
};

export const RISK_SENTENCE =
  "Automating the ChatGPT web interface may violate OpenAI's terms of use and can get your account suspended.";
export const FALLBACK_GREETING =
  "Hi, I am the Machine God companion. If you use ChatGPT, I can set up a bridge so Machine God can ask ChatGPT " +
  "through your own account. " + RISK_SENTENCE + " Do you want me to set it up?";
export const SYSTEM_PROMPT =
  "You are the Machine God companion, a small assistant that runs locally in the user's terminal. " +
  "Write a greeting of 2 or 3 sentences, addressed directly to the user (say 'you'). " +
  "Offer to set up an optional bridge that lets Machine God ask ChatGPT through the user's own ChatGPT account. " +
  "You MUST include this sentence word for word: \"" + RISK_SENTENCE + "\" " +
  "End by asking whether the user wants the bridge set up now, to be answered with yes or no. " +
  "Plain English text only. No markdown, no lists, no emoji.";

// ---------- paths and state ----------
export { resolvePaths, makeAsker, isYes, homeDir } from "./mg-common.js";
import { resolvePaths, makeAsker, isYes, homeDir, whichSync, run } from "./mg-common.js";

export function readState(file) {
  try {
    const s = JSON.parse(fs.readFileSync(file, "utf8"));
    return s && typeof s === "object" ? s : null;
  } catch {
    return null;
  }
}

export function writeState(file, state) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp.${process.pid}`;
  fs.writeFileSync(tmp, JSON.stringify({ ...state, version: STATE_VERSION, at: new Date().toISOString() }, null, 2) + "\n");
  fs.renameSync(tmp, file);
}

const aiConnected = (rec) => !!rec && Object.values(rec.ais || {}).includes("connected");

export function stateIsFinal(state) {
  // a state written by version 1 (before the GitHub and AI steps existed) is not final: the new steps are still to be offered once
  if (!state || !(state.status === "done" || state.status === "declined") || state.version === 1) return false;
  // a state from before the "fuse the AIs" question existed: offered once, and only to people who connected an AI
  if (state.steps && state.steps.grid !== true && aiConnected(state.ais)) return false;
  return true;
}

const SKIP_ARGS = new Set(["--help", "-h", "--version", "-V", "-v"]);
/** Returns a reason string when the companion must not run, else null. */
export function skipReason({ argv, env, stdinTTY, stdoutTTY, state }) {
  if (env.MG_FIRSTRUN_OFF === "1") return "off";
  if (argv.some((a) => SKIP_ARGS.has(a))) return "info-flag";
  if (env.MG_FIRSTRUN_FORCE === "1") return null;
  if (stateIsFinal(state)) return "done";
  if (!stdinTTY || !stdoutTTY) return "no-tty";
  return null;
}

// ---------- ChatGPT detection (installed desktop app or an open window titled ChatGPT; nothing else) ----------
const defaultExists = (p) => {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
};
const defaultRun = (cmd, args) => {
  try {
    const r = spawnSync(cmd, args, { encoding: "utf8", timeout: 4000, windowsHide: true });
    return r.error || r.status === null ? null : { status: r.status, stdout: r.stdout || "" };
  } catch {
    return null;
  }
};

export function windowTitleHasChatGPT(text) {
  return text.split(/\r?\n/).some((l) => /\bChatGPT\b/.test(l));
}

/** -> { found: boolean, how: string|null }. Pure apart from the injected exists()/run(). */
export function detectChatGPT({ platform = process.platform, env = process.env, home = os.homedir(), exists = defaultExists, run = defaultRun } = {}) {
  if (platform === "darwin") {
    for (const p of ["/Applications/ChatGPT.app", path.join(home, "Applications", "ChatGPT.app")]) {
      if (exists(p)) return { found: true, how: `app:${p}` };
    }
    return { found: false, how: null };
  }
  if (platform === "win32") {
    const local = env.LOCALAPPDATA || path.win32.join(home, "AppData", "Local");
    const dir = path.win32.join(local, "Programs", "ChatGPT");
    if (exists(dir)) return { found: true, how: `app:${dir}` };
    const r = run("powershell.exe", [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "(Get-AppxPackage *ChatGPT* | Select-Object -First 1 -ExpandProperty Name)",
    ]);
    if (r && r.status === 0 && r.stdout.trim()) return { found: true, how: `appx:${r.stdout.trim().split(/\r?\n/)[0]}` };
    return { found: false, how: null };
  }
  // Linux and others: window titles only, and only when a display server is present and a tool exists.
  if (!env.DISPLAY && !env.WAYLAND_DISPLAY) return { found: false, how: null };
  const w = run("wmctrl", ["-l"]);
  if (w && w.status === 0 && windowTitleHasChatGPT(w.stdout)) return { found: true, how: "window:wmctrl" };
  const x = run("xdotool", ["search", "--name", "ChatGPT"]);
  if (x && x.status === 0 && x.stdout.trim()) return { found: true, how: "window:xdotool" };
  return { found: false, how: null };
}

// ---------- questions ----------
// ---------- download + verify ----------
export function sha256File(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash("sha256");
    fs.createReadStream(file).on("data", (c) => h.update(c)).on("error", reject).on("end", () => resolve(h.digest("hex")));
  });
}

/** Download url to dest (resumable via .part), verify sha256, throw on mismatch. Returns dest. */
export async function downloadVerified({ url, dest, sha256, fetchFn = fetch, onProgress = () => {} }) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  if (fs.existsSync(dest) && (await sha256File(dest)) === sha256) return dest;
  const part = `${dest}.part`;
  let have = fs.existsSync(part) ? fs.statSync(part).size : 0;
  const headers = have > 0 ? { Range: `bytes=${have}-` } : {};
  const res = await fetchFn(url, { headers, redirect: "follow" });
  if (res.status === 416) {
    // part is already complete or stale: verify it, else start over
    if ((await sha256File(part)) === sha256) {
      fs.renameSync(part, dest);
      return dest;
    }
    fs.rmSync(part, { force: true });
    return downloadVerified({ url, dest, sha256, fetchFn, onProgress });
  }
  if (!res.ok) throw new Error(`download failed: HTTP ${res.status} for ${url}`);
  if (res.status === 200 && have > 0) have = 0; // server ignored Range
  const total = have + Number(res.headers.get("content-length") || 0);
  const fd = fs.openSync(part, have > 0 ? "a" : "w");
  let got = have;
  try {
    for await (const chunk of res.body) {
      fs.writeSync(fd, chunk);
      got += chunk.length;
      onProgress(got, total);
    }
  } finally {
    fs.closeSync(fd);
  }
  const actual = await sha256File(part);
  if (actual !== sha256) {
    fs.rmSync(part, { force: true });
    throw new Error(`checksum mismatch for ${path.basename(dest)}: expected ${sha256}, got ${actual}`);
  }
  fs.renameSync(part, dest);
  return dest;
}

function progressPrinter(label, out = process.stdout) {
  let last = -1;
  return (got, total) => {
    const pct = total ? Math.floor((got / total) * 100) : -1;
    if (pct === last) return;
    last = pct;
    const mb = (got / 1048576).toFixed(0);
    out.write(`\r  ${label}: ${pct >= 0 ? pct + "%" : ""} (${mb} MB)   `);
  };
}

// ---------- local model: llama-server ----------
export function llamaKey({ platform = process.platform, arch = process.arch } = {}) {
  return `${platform}-${arch}`;
}

export function findFile(dir, name) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      const r = findFile(p, name);
      if (r) return r;
    } else if (e.name === name) return p;
  }
  return null;
}

export async function ensureLlamaServer({ dataDir, platform = process.platform, arch = process.arch, log = console.log }) {
  const asset = LLAMA_ASSETS[llamaKey({ platform, arch })];
  if (!asset) throw new Error(`no pinned llama.cpp build for ${platform}/${arch}`);
  const root = path.join(dataDir, "llama", LLAMA_TAG);
  const exe = platform === "win32" ? "llama-server.exe" : "llama-server";
  const have = fs.existsSync(root) ? findFile(root, exe) : null;
  if (have) return have;
  const archive = path.join(dataDir, "llama", asset.name);
  log(`  downloading llama.cpp ${LLAMA_TAG} (official ggml-org release, ${asset.name})`);
  await downloadVerified({ url: `${LLAMA_BASE}/${asset.name}`, dest: archive, sha256: asset.sha256, onProgress: progressPrinter("llama.cpp") });
  process.stdout.write("\n");
  fs.rmSync(root, { recursive: true, force: true });
  fs.mkdirSync(root, { recursive: true });
  const r = spawnSync("tar", ["-xf", archive, "-C", root], { encoding: "utf8", windowsHide: true });
  if (r.status !== 0) throw new Error(`could not extract ${asset.name}: ${(r.stderr || r.error || "").toString().slice(0, 200)}`);
  fs.rmSync(archive, { force: true });
  const found = findFile(root, exe);
  if (!found) throw new Error(`${exe} not found in ${asset.name}`);
  if (platform !== "win32") fs.chmodSync(found, 0o755);
  return found;
}

export function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

export async function startLlama({ exe, modelPath, port, ctx = 2048 }) {
  const dir = path.dirname(exe);
  const env = { ...process.env, LD_LIBRARY_PATH: `${dir}:${process.env.LD_LIBRARY_PATH || ""}`, DYLD_LIBRARY_PATH: `${dir}:${process.env.DYLD_LIBRARY_PATH || ""}` };
  const child = spawn(exe, ["-m", modelPath, "--host", "127.0.0.1", "--port", String(port), "-c", String(ctx), "-np", "1", "-t", String(Math.max(1, Math.min(4, os.cpus().length - 1)))], {
    cwd: dir,
    env,
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
  });
  let tail = "";
  child.stderr.on("data", (d) => {
    tail = (tail + d).slice(-600);
  });
  let exited = false;
  child.on("exit", () => {
    exited = true;
  });
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    if (exited) throw new Error(`llama-server exited early: ${tail.replace(/\s+/g, " ").slice(-200)}`);
    try {
      const r = await fetch(`http://127.0.0.1:${port}/health`);
      if (r.ok) return child;
    } catch {}
    await new Promise((r) => setTimeout(r, 400));
  }
  child.kill();
  throw new Error("llama-server did not become ready in 90 s");
}

export function stopLlama(child) {
  try {
    child.kill("SIGTERM");
  } catch {}
  setTimeout(() => {
    try {
      child.kill("SIGKILL");
    } catch {}
  }, 3000).unref();
}

export function cleanModelText(t) {
  return (t || "").replace(/<think>[\s\S]*?<\/think>/g, "").replace(/\s+/g, " ").trim();
}

/** True when the greeting carries the risk warning (OpenAI + terms + suspended) and is a sane length. */
export function greetingIsValid(t) {
  return t.length >= 60 && t.length <= 1200 && /openai/i.test(t) && /terms/i.test(t) && /suspend/i.test(t) && /chatgpt/i.test(t);
}

async function chatCompletion({ port, fetchFn = fetch, system, user, maxTokens, temperature, grammar }) {
  const body = {
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    max_tokens: maxTokens,
    temperature,
    chat_template_kwargs: { enable_thinking: false },
  };
  if (grammar) body.grammar = grammar;
  const res = await fetchFn(`http://127.0.0.1:${port}/v1/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`model server answered HTTP ${res.status}`);
  const j = await res.json();
  return cleanModelText(j?.choices?.[0]?.message?.content);
}

// The 0.8B model is a narrow fine-tune and rarely follows the full greeting instruction. So: first the full greeting as
// specified (accepted only if it carries the risk warning), then a grammar-constrained opening sentence that the program
// completes with fixed offer/risk/question text, then the fixed fallback text.
export const OPENING_SYSTEM =
  "You are the Machine God companion, a friendly assistant in the user's terminal. " +
  "Write one short welcoming sentence addressed to the user, mentioning Machine God.";
export const OPENING_GRAMMAR = 'root ::= ("Hello" | "Hi" | "Welcome") [^.?!\\n]{3,70} [A-Za-z] "."\n';
const DANGLING = /\b(the|a|an|and|or|to|of|for|in|on|with|your|you'll|you|how|that|is|are)\.$/i;

export function openingIsValid(t) {
  return /^(Hello|Hi|Welcome)\b/.test(t) && t.length >= 20 && t.length <= 120 && !DANGLING.test(t) && !/[\r\n]/.test(t) && /Machine God/i.test(t);
}

export function composeGreeting(opening) {
  return `${opening} I can set up an optional bridge so Machine God can ask ChatGPT through your own ChatGPT account. ${RISK_SENTENCE} Do you want me to set it up?`;
}

/** -> { text, mode: "model" | "model-opening" | "fallback", tries } */
export async function makeGreeting({ port, fetchFn = fetch }) {
  let tries = 1;
  const full = await chatCompletion({ port, fetchFn, system: SYSTEM_PROMPT, user: "Greet me now.", maxTokens: 220, temperature: 0.5 });
  if (greetingIsValid(full)) return { text: full, mode: "model", tries };
  for (let i = 0; i < 3; i++) {
    tries++;
    const o = await chatCompletion({ port, fetchFn, system: OPENING_SYSTEM, user: "I just started Machine God for the first time.", maxTokens: 60, temperature: 0.7, grammar: OPENING_GRAMMAR });
    if (openingIsValid(o)) return { text: composeGreeting(o), mode: "model-opening", tries };
  }
  return { text: FALLBACK_GREETING, mode: "fallback", tries };
}

// ---------- ChatGPT bridge setup ----------
const isWin = process.platform === "win32";
const venvPython = (venv) => (isWin ? path.join(venv, "Scripts", "python.exe") : path.join(venv, "bin", "python"));

async function ensureUv(dataDir, log) {
  const onPath = whichSync("uv");
  if (onPath) return onPath;
  const bin = path.join(dataDir, "uv", "bin");
  const local = path.join(bin, isWin ? "uv.exe" : "uv");
  if (fs.existsSync(local)) return local;
  log("  uv (Python package manager) not found: installing it with Astral's official installer into " + bin);
  fs.mkdirSync(bin, { recursive: true });
  const env = { UV_UNMANAGED_INSTALL: bin, UV_NO_MODIFY_PATH: "1" };
  let r;
  if (isWin) {
    r = await run("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"], { env });
  } else {
    const script = await (await fetch("https://astral.sh/uv/install.sh")).text();
    r = await run("sh", ["-s"], { env, input: script });
  }
  if (!fs.existsSync(local)) throw new Error(`uv install failed: ${r.out.replace(/\s+/g, " ").slice(-300)}`);
  return local;
}

export function bridgeReadyInfo(configDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(configDir, "bridge.json"), "utf8"));
  } catch {
    return null;
  }
}

async function bridgeCall(configDir, method, route, body) {
  const info = bridgeReadyInfo(configDir);
  if (!info) throw new Error("bridge is not running");
  const token = fs.readFileSync(path.join(configDir, "bridge.token"), "utf8").trim();
  const res = await fetch(`http://127.0.0.1:${info.port}${route}`, {
    method,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

export function mcpAddCommand(python, script) {
  return ["claude", "mcp", "add", "--scope", "user", "machine-god-chatgpt", "--", python, script];
}

/** Sets the bridge up. Returns { status, detail }. Throws nothing the caller must handle. */
export async function setupBridge({ installDir, configDir, dataDir, log = console.log, waitLoginMs = 10 * 60 * 1000 }) {
  const bridgeDir = path.join(installDir, "bridge");
  const script = path.join(bridgeDir, "chatgpt_bridge.py");
  const mcp = path.join(bridgeDir, "mcp_chatgpt.py");
  if (!fs.existsSync(script) || !fs.existsSync(mcp)) return { status: "failed", detail: `bridge files missing in ${bridgeDir}` };
  fs.mkdirSync(configDir, { recursive: true });
  fs.mkdirSync(dataDir, { recursive: true });
  const logFile = path.join(dataDir, "bridge-setup.log");
  const step = async (label, cmd, args, opts) => {
    log(`  ${label} ...`);
    const r = await run(cmd, args, opts);
    fs.appendFileSync(logFile, `$ ${cmd} ${args.join(" ")}\n${r.out}\n`);
    if (r.code !== 0) throw new Error(`${label} failed (see ${logFile}): ${r.out.replace(/\s+/g, " ").slice(-240)}`);
  };
  const env = { MG_CONFIG_DIR: configDir, MG_DATA_DIR: dataDir, PLAYWRIGHT_BROWSERS_PATH: path.join(dataDir, "browsers") };
  try {
    const uv = await ensureUv(dataDir, log);
    const venv = path.join(dataDir, "bridge-venv");
    const py = venvPython(venv);
    if (!fs.existsSync(py)) await step("creating Python environment", uv, ["venv", venv, "--python", "3.12"]);
    await step("installing aiohttp and patchright (pinned)", uv, ["pip", "install", "--python", py, "-r", path.join(bridgeDir, "requirements.txt")]);
    await step("downloading the bridge's own Chromium", py, ["-m", "patchright", "install", "chromium"], { env });
    // token: random, local, mode 600
    const tokenFile = path.join(configDir, "bridge.token");
    if (!fs.existsSync(tokenFile)) fs.writeFileSync(tokenFile, crypto.randomBytes(32).toString("hex") + "\n", { mode: 0o600 });
    if (!isWin) fs.chmodSync(tokenFile, 0o600);
    log("  starting the bridge on 127.0.0.1 ...");
    fs.rmSync(path.join(configDir, "bridge.json"), { force: true });
    const logFd = fs.openSync(path.join(dataDir, "bridge.log"), "a");
    const child = spawn(py, [script, "serve"], { detached: true, stdio: ["ignore", logFd, logFd], env: { ...process.env, ...env }, windowsHide: true });
    child.unref();
    let up = false;
    for (let i = 0; i < 60 && !up; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const info = bridgeReadyInfo(configDir);
      if (info) {
        try {
          up = (await fetch(`http://127.0.0.1:${info.port}/health`)).ok;
        } catch {}
      }
    }
    if (!up) throw new Error(`bridge did not start (see ${path.join(dataDir, "bridge.log")})`);
    log("  opening the bridge's browser window. Log in to ChatGPT yourself in that window (the bridge never sees your password).");
    await bridgeCall(configDir, "POST", "/login");
    let loggedIn = false;
    const until = Date.now() + waitLoginMs;
    let stop = false;
    const onSigint = () => (stop = true);
    process.once("SIGINT", onSigint);
    while (!stop && Date.now() < until) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const s = await bridgeCall(configDir, "GET", "/status");
        if (s.logged_in === true) {
          loggedIn = true;
          break;
        }
      } catch {}
    }
    process.off("SIGINT", onSigint);
    log(loggedIn ? "  logged in to ChatGPT." : "  not logged in yet (you can log in later; the bridge window opens again when Machine God asks ChatGPT).");
    // register the MCP tool for this user
    const cmd = mcpAddCommand(py, mcp);
    if (whichSync("claude")) {
      const r = await run(cmd[0], cmd.slice(1));
      fs.appendFileSync(logFile, `$ ${cmd.join(" ")}\n${r.out}\n`);
      if (r.code === 0) log("  registered the MCP tool machine-god-chatgpt (tool: chatgpt_ask).");
      else log(`  could not register the MCP tool automatically. Run this yourself:\n    ${cmd.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ")}`);
    } else {
      log(`  the \`claude\` CLI is not installed. After installing it, register the tool with:\n    ${cmd.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ")}`);
    }
    return { status: "installed", detail: loggedIn ? "logged-in" : "login-pending" };
  } catch (e) {
    return { status: "failed", detail: String(e.message || e).slice(0, 400) };
  }
}

// ---------- main flow ----------
/** Step 1: ChatGPT detection, optional local greeting model and bridge. Mutates and returns record. */
async function chatgptStep({ env, log, out, ask, installDir, detect, platform, record, stateFile, configDir, dataDir }) {
  const det = detect({ env, platform });
  let usesChatGPT = det.found;
  if (det.found) {
    log("I found the ChatGPT desktop app or a ChatGPT window on this computer.");
    record.chatgpt = "detected";
  } else {
    usesChatGPT = await ask("Do you use ChatGPT? [y/N]");
    record.chatgpt = usesChatGPT ? "user-says-yes" : "user-says-no";
  }
  if (!usesChatGPT) {
    log("No ChatGPT bridge needed.");
    record.status = "declined";
    return record;
  }

  log("");
  log(`A small local model (Qwen 0.8B, ${(MODEL.size / 1e6).toFixed(0)} MB download, runs on your computer only) can greet you and explain an optional ChatGPT bridge.`);
  let greeting = FALLBACK_GREETING;
  let child = null;
  if (await ask(`Download it now? [y/N]`)) {
    try {
      const modelPath = path.join(dataDir, "models", MODEL.file);
      await downloadVerified({ url: `${RELEASE_BASE}/${MODEL.file}`, dest: modelPath, sha256: MODEL.sha256, onProgress: progressPrinter("model") });
      out.write("\n");
      log("  model downloaded and checksum verified.");
      const exe = await ensureLlamaServer({ dataDir, log });
      const port = await freePort();
      child = await startLlama({ exe, modelPath, port });
      const g = await makeGreeting({ port });
      greeting = g.text;
      record.model = "used";
      record.greeting = g.mode;
    } catch (e) {
      log(`  local model unavailable: ${String(e.message || e).slice(0, 200)}. Using the standard text.`);
      record.model = "failed";
    } finally {
      if (child) stopLlama(child);
    }
  } else {
    record.model = "declined";
  }

  log("");
  log(greeting);
  log("");
  if (await ask("Set up the ChatGPT bridge now? [y/N]")) {
    log("Setting up the bridge (own browser profile, local only, you log in yourself):");
    const r = await setupBridge({ installDir, configDir, dataDir, log, waitLoginMs: env.MG_FIRSTRUN_LOGIN_WAIT_S ? Number(env.MG_FIRSTRUN_LOGIN_WAIT_S) * 1000 : undefined });
    record.bridge = r.status;
    record.detail = r.detail;
    log(r.status === "installed" ? "Bridge ready." : `Bridge setup failed: ${r.detail}\nTry again later with: MG_FIRSTRUN_FORCE=1 machine-god`);
  } else {
    record.bridge = "declined";
    log("No bridge. You can run this again anytime: delete " + stateFile);
    record.status = "declined";
  }
  return record;
}

/**
 * Companion flow: 1. ChatGPT  2. GitHub (account, SSH, private GRID repo)  3. which AIs you use (fusion)  4. fuse them into one Machine God (shared memory, only if an AI is connected).
 * Each step is asked once and every question can be answered no. State is written after each step (status "partial", the
 * real outcome in `outcome`), so a Ctrl-C never repeats what was already answered; the last write sets the final status.
 * `prior` = an earlier state: a version 1 state (written before the GitHub and AI steps existed) skips step 1, a partial one skips what it finished.
 * Injectable: detect, github, ais.
 */
/** Self-improvement (reflect/): only on yes. `improve enable` registers the reflection hooks in the user's Claude Code settings (backup first). */
export async function runImproveStep({ ask, log, env, installDir }) {
  log("");
  log("Machine God can reflect after each task and learn lessons from what went wrong. Task summaries (secrets redacted, size capped)");
  log("go to the AI you use; lessons change only behaviour. Code changes are only proposed and applied after your yes (`machine-god improve proposals`).");
  if (!(await ask("Turn on self-improvement? [y/N]"))) { log("  Skipped. Later: `machine-god improve enable`."); return { improve: "declined" }; }
  const root = installDir || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const r = spawnSync(process.execPath, [path.join(root, "reflect", "cli.ts"), "enable"], { env: { ...process.env, ...env }, encoding: "utf8", timeout: 30000 });
  for (const l of `${r.stdout || ""}${r.stderr || ""}`.trim().split("\n").filter(Boolean)) log("  " + l);
  return { improve: r.status === 0 ? "on" : "failed" };
}

export async function runFirstRun({ env = process.env, out = process.stdout, ask, installDir, detect = detectChatGPT, platform = process.platform, github = runGithubStep, ais = runAisStep, grid = runGridStep, improve = runImproveStep, prior = null } = {}) {
  const log = (s = "") => out.write(s + "\n");
  const { configDir, dataDir, stateFile } = resolvePaths({ env, platform });
  const record = prior
    ? { ...prior, steps: { ...(prior.steps || {}), ...(prior.version === 1 || prior.version === undefined ? { chatgpt: true } : {}) } }
    : { status: "done", chatgpt: "unknown", model: "skipped", bridge: "skipped", steps: {} };
  if (prior && prior.status === "partial") record.status = prior.outcome || "done";
  delete record.outcome;
  const save = (final) => writeState(stateFile, final ? record : { ...record, status: "partial", outcome: record.status });
  log("");
  log(prior ? "== Machine God: new in this version ==" : "== Machine God first start ==");
  if (!record.steps.chatgpt) {
    await chatgptStep({ env, log, out, ask, installDir, detect, platform, record, stateFile, configDir, dataDir });
    record.steps.chatgpt = true;
    save(false);
  }
  const text = ask.text || (async () => "");
  const ctxBase = { ask, text, log, env, platform, paths: { configDir, dataDir, stateFile } };
  if (!record.steps.github) {
    try {
      record.github = await github({ ...ctxBase });
    } catch (e) {
      record.github = { account: "unknown", grid: "failed", detail: String(e.message || e).slice(0, 160) };
      log(`  GitHub step stopped: ${record.github.detail}`);
    }
    record.steps.github = true;
    save(false);
  }
  if (!record.steps.ais) {
    try {
      record.ais = await ais({
        ...ctxBase, secret: ask.secret || (async () => ""),
        installDir,
        setupBridge: () => setupBridge({ installDir, configDir, dataDir, log }),
      });
    } catch (e) {
      record.ais = { ais: {}, mcp: "none", detail: String(e.message || e).slice(0, 160) };
      log(`  AI step stopped: ${record.ais.detail}`);
    }
    record.steps.ais = true;
    save(false);
  }
  if (!record.steps.grid) {
    try {
      record.grid = await grid({ ...ctxBase, bun: process.execPath, script: path.join(installDir || path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."), "grid", "mcp_grid.js") });
    } catch (e) {
      record.grid = { fused: "failed", detail: String(e.message || e).slice(0, 160) };
      log(`  GRID step stopped: ${record.grid.detail}`);
    }
    record.steps.grid = true;
    save(false);
  }
  if (!record.steps.improve) {
    try { record.improve = (await improve({ ask, log, env, installDir })).improve; }
    catch (e) { record.improve = "failed"; log(`  Self-improvement step stopped: ${String(e.message || e).slice(0, 160)}`); }
    record.steps.improve = true;
  }
  log("");
  log("Done. Later: `machine-god ais`, `machine-god grid` (shared memory; `grid repo` for GitHub), `machine-god mailbox`, `machine-god interests`, `machine-god improve`. To see this walkthrough again: delete " + stateFile);
  save(true);
  return record;
}

export async function main(argv = process.argv.slice(2), env = process.env) {
  const { stateFile } = resolvePaths({ env });
  const state = readState(stateFile);
  const why = skipReason({ argv, env, stdinTTY: !!process.stdin.isTTY, stdoutTTY: !!process.stdout.isTTY, state });
  if (why) return 0;
  const ask = makeAsker({ env });
  try {
    const installDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
    await runFirstRun({ env, ask, installDir, prior: stateIsFinal(state) ? null : state });
  } catch (e) {
    process.stderr.write(`machine-god first run skipped: ${String(e.message || e).slice(0, 200)}\n`);
  } finally {
    ask.close();
  }
  return 0;
}

if (import.meta.main) {
  main().then(() => process.exit(0), () => process.exit(0));
}
