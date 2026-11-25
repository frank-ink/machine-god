// Machine God fusion client: one function, askProvider(id, prompt), for every AI the user connected. No dependencies.
// Used by the MCP server (mcp_fusion.js), the `machine-god ais` command and the interest organ.
// Keys live only in <data dir>/keys.json (mode 600); they are never printed, logged or put in a URL, and every error text is scrubbed.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { resolvePaths } from "../firstrun/mg-common.js";

export const PROVIDERS = {
  chatgpt: { label: "ChatGPT", kind: "bridge" },
  claude: { label: "Claude", kind: "cli", docs: "https://docs.claude.com/en/docs/claude-code/setup" },
  gemini: {
    label: "Gemini", kind: "key", keyUrl: "https://aistudio.google.com/apikey", model: "gemini-flash-latest",
    base: "https://generativelanguage.googleapis.com",
  },
  local: { label: "Local (Ollama / LM Studio)", kind: "local" },
  copilot: {
    label: "Copilot (GitHub Models)", kind: "key", keyUrl: "https://github.com/settings/personal-access-tokens", model: "openai/gpt-4.1-mini",
    base: "https://models.github.ai", chatPath: "/inference/chat/completions", extraHeaders: { "x-github-api-version": "2022-11-28", accept: "application/vnd.github+json" },
  },
  grok: { label: "Grok (xAI)", kind: "key", keyUrl: "https://console.x.ai", model: "grok-3-mini", base: "https://api.x.ai", chatPath: "/v1/chat/completions" },
  perplexity: { label: "Perplexity", kind: "key", keyUrl: "https://www.perplexity.ai/settings/api", model: "sonar", base: "https://api.perplexity.ai", chatPath: "/chat/completions" },
};
export const PROVIDER_IDS = Object.keys(PROVIDERS);
export const OLLAMA_URL = "http://127.0.0.1:11434";
export const LMSTUDIO_URL = "http://127.0.0.1:1234";

// ---------- files: ais.json (which AIs are connected, no secrets) and keys.json (secrets, mode 600) ----------
export const aisFile = (configDir) => path.join(configDir, "ais.json");
export const keysFile = (dataDir) => path.join(dataDir, "keys.json");

function readJson(file, fallback) {
  try {
    const j = JSON.parse(fs.readFileSync(file, "utf8"));
    return j && typeof j === "object" ? j : fallback;
  } catch {
    return fallback;
  }
}
function writeJson600(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.tmp.${process.pid}`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", { mode: 0o600 });
  if (process.platform !== "win32") fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
}

export const loadAis = (configDir) => {
  const j = readJson(aisFile(configDir), {});
  return { connected: j.connected && typeof j.connected === "object" ? j.connected : {} };
};
export const saveAis = (configDir, ais) => writeJson600(aisFile(configDir), { version: 1, connected: ais.connected });
export function connect(configDir, id, meta = {}) {
  const a = loadAis(configDir);
  a.connected[id] = { ...meta, at: new Date().toISOString() };
  saveAis(configDir, a);
}
export function disconnect(configDir, dataDir, id) {
  const a = loadAis(configDir);
  const was = id in a.connected;
  delete a.connected[id];
  saveAis(configDir, a);
  const k = readJson(keysFile(dataDir), {});
  if (id in k) {
    delete k[id];
    writeJson600(keysFile(dataDir), k);
  }
  return was;
}
export const loadKeys = (dataDir) => readJson(keysFile(dataDir), {});
export function saveKey(dataDir, id, key, model) {
  const k = loadKeys(dataDir);
  k[id] = { key, ...(model ? { model } : {}) };
  writeJson600(keysFile(dataDir), k);
}
export const keyHash = (key) => (key ? `${key.length} chars` : "none"); // for messages: never the key itself

/** Remove every occurrence of the secrets from a message. */
export function scrub(text, secrets = []) {
  let t = String(text ?? "");
  for (const s of secrets) if (s && s.length >= 6) t = t.split(s).join("[key]");
  return t.replace(/\b(AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xai-[A-Za-z0-9]{20,}|pplx-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b/g, "[key]");
}

export function validKeyShape(key) {
  return typeof key === "string" && key.length >= 10 && key.length <= 400 && /^[\x21-\x7e]+$/.test(key);
}

// ---------- local models ----------
async function getJson(url, fetchFn, ms) {
  const res = await fetchFn(url, { signal: AbortSignal.timeout(ms) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
/** -> [{ kind: "ollama"|"lmstudio", url, models: [names] }] for servers that answer on 127.0.0.1. */
export async function probeLocal({ env = process.env, fetchFn = fetch, ms = 1500 } = {}) {
  const found = [];
  const ollama = env.MG_OLLAMA_URL || OLLAMA_URL;
  const lm = env.MG_LMSTUDIO_URL || LMSTUDIO_URL;
  await Promise.all([
    (async () => {
      try {
        const j = await getJson(`${ollama}/api/tags`, fetchFn, ms);
        found.push({ kind: "ollama", url: ollama, models: (j.models || []).map((m) => m.name || m.model).filter(Boolean) });
      } catch {}
    })(),
    (async () => {
      try {
        const j = await getJson(`${lm}/v1/models`, fetchFn, ms);
        found.push({ kind: "lmstudio", url: lm, models: (j.data || []).map((m) => m.id).filter(Boolean) });
      } catch {}
    })(),
  ]);
  return found.sort((a, b) => a.kind.localeCompare(b.kind));
}

/** Embedding-only models cannot chat; they are never picked as the default. */
export const isEmbeddingModel = (name) => /embed|(^|[/:-])bge-|minilm|(^|[/:-])e5-|(^|[/:-])gte-|rerank/i.test(name);
export const chatModels = (models) => models.filter((m) => !isEmbeddingModel(m));

// ---------- asking ----------
const baseFor = (id, env) => (env[`MG_FUSION_BASE_${id.toUpperCase()}`] || PROVIDERS[id].base).replace(/\/+$/, "");
const modelFor = (id, entry, env) => env[`MG_FUSION_MODEL_${id.toUpperCase()}`] || entry?.model || PROVIDERS[id].model;

const trimText = (t) => String(t ?? "").trim();

async function postJson(url, headers, body, fetchFn, ms, secrets) {
  let res;
  try {
    res = await fetchFn(url, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body), signal: AbortSignal.timeout(ms) });
  } catch (e) {
    throw new Error(scrub(e.name === "TimeoutError" ? `timeout after ${Math.round(ms / 1000)} s` : `network error: ${e.message || e}`, secrets));
  }
  let text = "";
  try {
    text = await res.text();
  } catch {}
  if (!res.ok) {
    let msg = text;
    try {
      const j = JSON.parse(text);
      msg = j?.error?.message || j?.error || j?.message || text;
    } catch {}
    throw new Error(scrub(`HTTP ${res.status}: ${typeof msg === "string" ? msg : JSON.stringify(msg)}`.replace(/\s+/g, " ").slice(0, 200), secrets));
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("answer was not JSON");
  }
}

function runCli(cmd, args, { input, cwd, ms }) {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, { cwd, stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
    let out = "";
    let err = "";
    const t = setTimeout(() => {
      c.kill();
      resolve({ code: 124, out, err: "timeout" });
    }, ms);
    c.stdout.on("data", (d) => (out += d));
    c.stderr.on("data", (d) => (err += d));
    c.on("error", (e) => {
      clearTimeout(t);
      resolve({ code: -1, out, err: String(e.message || e) });
    });
    c.on("close", (code) => {
      clearTimeout(t);
      resolve({ code, out, err });
    });
    c.stdin.on("error", () => {});
    c.stdin.end(input);
  });
}

/**
 * Ask one connected AI. Returns the answer text; throws Error (scrubbed message) on failure.
 * opts: { env, fetchFn, paths, timeoutMs, maxTokens, allowEmpty, cli, kind (local only: "ollama" | "lmstudio") }
 */
export async function askProvider(id, prompt, opts = {}) {
  const env = opts.env || process.env;
  const fetchFn = opts.fetchFn || fetch;
  const paths = opts.paths || resolvePaths({ env });
  const ms = opts.timeoutMs || 120_000;
  const P = PROVIDERS[id];
  if (!P) throw new Error(`unknown AI: ${id}`);
  if (typeof prompt !== "string" || !prompt.trim()) throw new Error("empty prompt");
  const entry = loadAis(paths.configDir).connected[id] || {};
  const done = (t) => {
    const s = trimText(t);
    if (!s && !opts.allowEmpty) throw new Error("empty answer");
    return s;
  };

  if (P.kind === "key") {
    const k = loadKeys(paths.dataDir)[id];
    if (!k?.key) throw new Error(`no key stored for ${id} (run: machine-god ais connect ${id})`);
    const secrets = [k.key];
    const model = modelFor(id, k, env);
    const base = baseFor(id, env);
    if (id === "gemini") {
      const body = { contents: [{ role: "user", parts: [{ text: prompt }] }] };
      if (opts.maxTokens) body.generationConfig = { maxOutputTokens: opts.maxTokens };
      const j = await postJson(`${base}/v1beta/models/${encodeURIComponent(model)}:generateContent`, { "x-goog-api-key": k.key }, body, fetchFn, ms, secrets);
      return done((j.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join(""));
    }
    const body = { model, messages: [{ role: "user", content: prompt }], ...(opts.maxTokens ? { max_tokens: opts.maxTokens } : {}) };
    const j = await postJson(base + P.chatPath, { authorization: `Bearer ${k.key}`, ...(P.extraHeaders || {}) }, body, fetchFn, ms, secrets);
    return done(j.choices?.[0]?.message?.content);
  }

  if (P.kind === "local") {
    const found = await probeLocal({ env, fetchFn });
    const srv = opts.kind ? found.find((f) => f.kind === opts.kind) : found.find((f) => f.kind === entry.kind) || found[0];
    if (!srv) throw new Error("no local model server answers on 127.0.0.1 (Ollama :11434, LM Studio :1234)");
    const chat = chatModels(srv.models);
    const model = entry.model && srv.models.includes(entry.model) ? entry.model : chat[0];
    if (!model) throw new Error(`${srv.kind} is running but has no chat model`);
    if (srv.kind === "ollama") {
      const j = await postJson(`${srv.url}/api/chat`, {}, { model, stream: false, messages: [{ role: "user", content: prompt }], ...(opts.maxTokens ? { options: { num_predict: opts.maxTokens } } : {}) }, fetchFn, ms, []);
      return done(j.message?.content);
    }
    const j = await postJson(`${srv.url}/v1/chat/completions`, {}, { model, messages: [{ role: "user", content: prompt }], ...(opts.maxTokens ? { max_tokens: opts.maxTokens } : {}) }, fetchFn, ms, []);
    return done(j.choices?.[0]?.message?.content);
  }

  if (P.kind === "cli") {
    const run = opts.cli || runCli;
    const r = await run("claude", ["-p", "--output-format", "json"], { input: prompt, cwd: os.tmpdir(), ms });
    let j = null;
    try {
      j = JSON.parse(r.out);
    } catch {}
    if (r.code !== 0 || !j || j.is_error) throw new Error(scrub(`claude failed (exit ${r.code}): ${String(j?.result ?? r.err ?? "no output").slice(0, 160)}`));
    return done(j.result);
  }

  if (P.kind === "bridge") {
    let info;
    let token;
    try {
      info = JSON.parse(fs.readFileSync(path.join(paths.configDir, "bridge.json"), "utf8"));
      token = fs.readFileSync(path.join(paths.configDir, "bridge.token"), "utf8").trim();
    } catch {
      throw new Error("the ChatGPT bridge is not running (start it by asking through the machine-god-chatgpt tool, or re-run the bridge setup)");
    }
    const j = await postJson(`http://127.0.0.1:${info.port}/ask`, { authorization: `Bearer ${token}` }, { prompt, timeout_s: Math.round(ms / 1000) - 5, new_chat: true }, fetchFn, ms + 60_000, [token]);
    if (j.ok) return done(j.content);
    throw new Error(`ChatGPT failed (${j.failure || "error"}): ${String(j.error || "").slice(0, 120)}`);
  }
  throw new Error(`cannot ask ${id}`);
}

/** The cheap test used by `machine-god ais test`: one tiny request. -> { ok, detail } (never contains the key). */
export async function testProvider(id, opts = {}) {
  try {
    if (PROVIDERS[id]?.kind === "bridge") {
      const paths = opts.paths || resolvePaths({ env: opts.env || process.env });
      const info = JSON.parse(fs.readFileSync(path.join(paths.configDir, "bridge.json"), "utf8"));
      const res = await (opts.fetchFn || fetch)(`http://127.0.0.1:${info.port}/health`, { signal: AbortSignal.timeout(3000) });
      return res.ok ? { ok: true, detail: "bridge answers (login state not tested)" } : { ok: false, detail: `bridge HTTP ${res.status}` };
    }
    const t = await askProvider(id, "Reply with the single word OK.", { ...opts, maxTokens: 16, allowEmpty: PROVIDERS[id]?.kind === "key", timeoutMs: opts.timeoutMs || 45_000 });
    return { ok: true, detail: t ? `answered (${t.length} chars)` : "accepted the request" };
  } catch (e) {
    return { ok: false, detail: String(e.message || e).slice(0, 200) };
  }
}

export const connectedIds = (configDir) => PROVIDER_IDS.filter((id) => id in loadAis(configDir).connected);

/** Ask all connected AIs at once. -> [{ id, ok, text|error }] */
export async function askAll(prompt, opts = {}) {
  const paths = opts.paths || resolvePaths({ env: opts.env || process.env });
  const ids = opts.ids || connectedIds(paths.configDir);
  return Promise.all(ids.map(async (id) => {
    try {
      return { id, ok: true, text: await askProvider(id, prompt, { ...opts, paths }) };
    } catch (e) {
      return { id, ok: false, error: String(e.message || e).slice(0, 300) };
    }
  }));
}
export const formatAll = (rs) => rs.map((r) => (r.ok ? `## ${r.id}\n${r.text}` : `## ${r.id} (failed)\n${r.error}`)).join("\n\n");
