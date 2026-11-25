// Machine God AI fusion: connect your AIs, one by one, each only after your yes; then one MCP server (mcp_fusion.js) exposes them.
//   machine-god ais                      list
//   machine-god ais connect [ai] [model] connect (asks first; keys are typed hidden and stored only in keys.json, mode 600)
//   machine-god ais disconnect <ai>      forget it (and its key)
//   machine-god ais test [ai]            one cheap request per AI, prints ok / fail (never the key)
//   machine-god ais register             register the fusion MCP server with Claude Code
// The same flow runs in the first-run companion (runAisStep).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeAsker, resolvePaths, whichSync, run } from "../firstrun/mg-common.js";
import { PROVIDERS, PROVIDER_IDS, chatModels, connect, connectedIds, disconnect, keyHash, loadAis, loadKeys, probeLocal, saveKey, testProvider, validKeyShape } from "./fusion.js";

export const ORDER = ["chatgpt", "claude", "gemini", "local", "copilot", "grok", "perplexity"];
export const CONNECTORS_URL = "https://chatgpt.com/#settings/Connectors";
const ALIASES = { gpt: "chatgpt", openai: "chatgpt", anthropic: "claude", ollama: "local", lmstudio: "local", "lm studio": "local", localmodel: "local", github: "copilot", "github models": "copilot", xai: "grok", pplx: "perplexity", google: "gemini" };

/** "1,3, grok" / "chatgpt gemini" / "none" -> ["chatgpt","gemini"] (unknown words are returned in .unknown) */
export function parseSelection(text) {
  const ids = [];
  const unknown = [];
  const t = String(text || "").toLowerCase().replace(/lm studio/g, "lmstudio").replace(/github models/g, "copilot").trim();
  if (!t || /^(none|no|n|nothing|-)$/.test(t)) return { ids, unknown };
  if (/^(all|everything)$/.test(t)) return { ids: [...ORDER], unknown };
  for (const raw of t.split(/[,;]+|\s+(?=[a-z0-9])/).map((x) => x.trim()).filter(Boolean)) {
    let id = null;
    if (/^[1-7]$/.test(raw)) id = ORDER[Number(raw) - 1];
    else if (PROVIDERS[raw]) id = raw;
    else if (ALIASES[raw]) id = ALIASES[raw];
    if (id) {
      if (!ids.includes(id)) ids.push(id);
    } else unknown.push(raw);
  }
  return { ids, unknown };
}

export function fusionMcpCommand(bun, script) {
  return ["claude", "mcp", "add", "--scope", "user", "machine-god-fusion", "--", bun, script];
}
const quote = (cmd) => cmd.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");
const here = path.dirname(fileURLToPath(import.meta.url));

/** Register the fusion MCP server with Claude Code, or print the exact command. -> "registered" | "printed" | "failed" */
export async function registerFusion({ log, runFn = run, which = whichSync, bun = process.execPath, script = path.join(here, "mcp_fusion.js") }) {
  const cmd = fusionMcpCommand(bun, script);
  if (!which("claude")) {
    log(`  the \`claude\` CLI is not installed. After installing it, register the fusion tool with:\n    ${quote(cmd)}`);
    return "printed";
  }
  const r = await runFn(cmd[0], cmd.slice(1));
  if (r.code === 0 || /already exists/i.test(r.out)) {
    log("  registered the MCP server machine-god-fusion (tools: ask_<ai>, ask_all). Restart Claude Code to see it.");
    return "registered";
  }
  log(`  could not register it automatically. Run this yourself:\n    ${quote(cmd)}`);
  return "failed";
}

/**
 * Connect one AI. ctx: { ask, text, secret, log, paths, env, fetchFn, which, runFn, setupBridge, installDir, model }
 * -> { status: "connected" | "skipped" | "failed", detail }
 */
export async function connectAI(id, ctx) {
  const { ask, secret, log, paths } = ctx;
  const env = ctx.env || process.env;
  const P = PROVIDERS[id];
  const which = ctx.which || ((n) => whichSync(n, env));
  if (!P) return { status: "failed", detail: "unknown AI" };

  if (P.kind === "key") {
    log(`${P.label}: create an API key here: ${P.keyUrl}`);
    if (id === "copilot") log("  (GitHub fine-grained token with the \"Models\" read permission; it is used for GitHub Models.)");
    if (id === "gemini" || id === "grok" || id === "perplexity") log("  (Usage on a key can cost money at the provider; Machine God sends only the prompts you or your tools ask for.)");
    if (!(await ask(`Paste the ${P.label} key now? It is typed hidden and stored only on this computer (keys.json, owner-only). [y/N]`))) return { status: "skipped", detail: "no key given" };
    const key = (await secret(`${P.label} key (hidden):`)).trim();
    if (!key) return { status: "skipped", detail: "nothing entered" };
    if (!validKeyShape(key)) return { status: "failed", detail: "that does not look like an API key (10-400 visible characters, no spaces)" };
    const had = loadKeys(paths.dataDir)[id];
    saveKey(paths.dataDir, id, key, ctx.model);
    log(`  key stored (${keyHash(key)}); testing with one small request ...`);
    const t = await testProvider(id, { env, fetchFn: ctx.fetchFn, paths });
    log(`  test: ${t.ok ? "ok" : "FAILED"} (${t.detail})`);
    if (!t.ok && !(await ask("  Keep the key anyway? [y/N]"))) {
      if (had) saveKey(paths.dataDir, id, had.key, had.model);
      else disconnect(paths.configDir, paths.dataDir, id);
      return { status: "failed", detail: t.detail };
    }
    connect(paths.configDir, id, { test: t.ok ? "ok" : "failed" });
    return { status: "connected", detail: t.ok ? "test ok" : "kept after failed test" };
  }

  if (P.kind === "local") {
    const found = await probeLocal({ env, fetchFn: ctx.fetchFn });
    if (!found.length) {
      log("  nothing answers on 127.0.0.1:11434 (Ollama) or :1234 (LM Studio).");
      log("  Install Ollama (https://ollama.com/download) or LM Studio (https://lmstudio.ai), start it, load a model, then run: machine-god ais connect local");
      return { status: "skipped", detail: "no local server" };
    }
    for (const f of found) log(`  ${f.kind} at ${f.url}: ${f.models.length ? f.models.join(", ") : "(no models)"}`);
    const usable = found.find((f) => chatModels(f.models).length);
    if (!usable) return { status: "failed", detail: "server running but no chat model installed (embedding models cannot chat)" };
    const model = ctx.model && usable.models.includes(ctx.model) ? ctx.model : chatModels(usable.models)[0];
    connect(paths.configDir, id, { kind: usable.kind, model });
    log(`  connected: ${usable.kind}, model ${model} (change: machine-god ais connect local <model>)`);
    return { status: "connected", detail: `${usable.kind} ${model}` };
  }

  if (P.kind === "cli") {
    if (!which("claude")) {
      log(`  the \`claude\` CLI is not installed. Setup guide: ${P.docs}`);
      return { status: "skipped", detail: "claude CLI missing" };
    }
    if (await ask("Run `claude /login` now? (it opens Claude's own login; Machine God never sees your credentials. Say no if you are already logged in) [y/N]")) {
      ask.suspend?.();
      await (ctx.runFn || run)("claude", ["/login"], { stdio: "inherit" });
    }
    connect(paths.configDir, id, {});
    log("  connected: Machine God will ask Claude through the `claude` CLI (`claude -p`), with your own login.");
    return { status: "connected", detail: "claude CLI" };
  }

  if (P.kind === "bridge") {
    log("ChatGPT can be reached two ways:");
    log("  1. You asking ChatGPT from Machine God: the browser bridge (your own ChatGPT login in a local window).");
    log("  2. ChatGPT asking your computer: through your private GRID repo (machine-god mailbox); ChatGPT can only read, everything else needs your yes.");
    let bridge = fs.existsSync(path.join(paths.configDir, "bridge.json"));
    if (!bridge && ctx.setupBridge && (await ask("Set up the ChatGPT browser bridge now? (may violate OpenAI's terms and can get your account suspended) [y/N]"))) {
      const r = await ctx.setupBridge();
      bridge = r.status === "installed";
      log(bridge ? "  bridge ready." : `  bridge setup failed: ${r.detail}`);
    }
    log("To let ChatGPT use the mailbox: connect GitHub in ChatGPT (Settings -> Connectors), choose your machine-god-grid repo only:");
    log(`  ${CONNECTORS_URL}`);
    log(fs.existsSync(path.join(paths.configDir, "grid.json")) ? "  then run `machine-god mailbox` in a terminal and keep it open while ChatGPT works." : "  first create your GRID repo: machine-god grid repo");
    if (bridge) {
      connect(paths.configDir, id, { bridge: true });
      return { status: "connected", detail: "bridge" };
    }
    return { status: "skipped", detail: "no bridge (mailbox instructions shown)" };
  }
  return { status: "failed", detail: "unsupported" };
}

export function listing(paths, probe = []) {
  const ais = loadAis(paths.configDir).connected;
  const keys = loadKeys(paths.dataDir);
  const lines = [];
  ORDER.forEach((id, i) => {
    const P = PROVIDERS[id];
    const c = ais[id];
    const extra = P.kind === "key" ? (keys[id]?.key ? `key stored (${keyHash(keys[id].key)})` : "no key") : c?.model ? `${c.kind} ${c.model}` : "";
    lines.push(`${i + 1}. ${id.padEnd(10)} ${P.label.padEnd(28)} ${c ? "connected" : "not connected"}${extra ? "  " + extra : ""}`);
  });
  if (probe.length) for (const f of probe) lines.push(`   local server: ${f.kind} ${f.url} (${f.models.length} model${f.models.length === 1 ? "" : "s"})`);
  return lines.join("\n");
}

/** The companion step: which AIs do you use? -> record { ais: {id: status}, mcp } */
export async function runAisStep(ctx) {
  const { ask, text, log, paths } = ctx;
  const rec = { ais: {}, mcp: "none" };
  log("");
  log("== Your AIs ==");
  log("Machine God can fuse the AIs you use into one tool for Claude Code (ask_<ai>, ask_all). Nothing is connected without your yes.");
  ORDER.forEach((id, i) => log(`  ${i + 1}. ${PROVIDERS[id].label}`));
  const sel = parseSelection(await text("Which AIs do you use? Type numbers or names separated by commas, or 'none':"));
  if (sel.unknown.length) log(`  ignoring: ${sel.unknown.join(", ")}`);
  for (const id of sel.ids) {
    if (!(await ask(`Connect ${PROVIDERS[id].label} now? [y/N]`))) {
      rec.ais[id] = "declined";
      continue;
    }
    const r = await connectAI(id, ctx).catch((e) => ({ status: "failed", detail: String(e.message || e).slice(0, 160) }));
    rec.ais[id] = r.status;
    log(`  ${PROVIDERS[id].label}: ${r.status}${r.detail ? ` (${r.detail})` : ""}`);
  }
  if (connectedIds(paths.configDir).length) {
    log("");
    if (await ask("Register the fusion tool with Claude Code now (claude mcp add ...)? [y/N]")) rec.mcp = await registerFusion({ log, runFn: ctx.runFn, which: ctx.which, bun: ctx.bun, script: ctx.script });
    else {
      rec.mcp = "declined";
      log("  later: machine-god ais register");
    }
  }
  return rec;
}

function makeCtx(env, asker, log) {
  const paths = resolvePaths({ env });
  return {
    ask: asker, text: asker.text, secret: asker.secret, log, paths, env,
    installDir: path.resolve(here, ".."),
    setupBridge: async () => {
      const { setupBridge } = await import("../firstrun/mg-firstrun.js");
      return setupBridge({ installDir: path.resolve(here, ".."), configDir: paths.configDir, dataDir: paths.dataDir, log });
    },
  };
}

export async function main(argv = process.argv.slice(2), env = process.env, out = process.stdout) {
  const log = (s = "") => out.write(s + "\n");
  const [cmd = "list", id, model] = argv;
  const paths = resolvePaths({ env });
  const needId = () => {
    if (!PROVIDERS[id]) {
      log(`usage: machine-god ais ${cmd} <${PROVIDER_IDS.join("|")}>`);
      return false;
    }
    return true;
  };
  switch (cmd) {
    case "list":
      log(listing(paths, await probeLocal({ env })));
      log("\nconnect: machine-god ais connect <name>   test: machine-god ais test   MCP: machine-god ais register");
      return 0;
    case "connect": {
      if (id && !needId()) return 1;
      const asker = makeAsker({ env });
      try {
        const ctx = makeCtx(env, asker, log);
        if (!id) return (await runAisStep(ctx), 0);
        const r = await connectAI(id, { ...ctx, model });
        log(`${PROVIDERS[id].label}: ${r.status}${r.detail ? ` (${r.detail})` : ""}`);
        return r.status === "failed" ? 1 : 0;
      } finally {
        asker.close();
      }
    }
    case "disconnect":
      if (!needId()) return 1;
      log(disconnect(paths.configDir, paths.dataDir, id) ? `${id} disconnected, key removed` : `${id} was not connected`);
      return 0;
    case "test": {
      const ids = id ? (needId() ? [id] : null) : connectedIds(paths.configDir);
      if (!ids) return 1;
      if (!ids.length) {
        log("no AIs connected: machine-god ais connect");
        return 0;
      }
      let bad = 0;
      for (const x of ids) {
        const t = await testProvider(x, { env, paths });
        log(`${x.padEnd(10)} ${t.ok ? "ok" : "FAIL"}  ${t.detail}`);
        if (!t.ok) bad++;
      }
      return bad ? 1 : 0;
    }
    case "register":
      return (await registerFusion({ log })) === "failed" ? 1 : 0;
    default:
      log("usage: machine-god ais [list|connect [ai] [model]|disconnect <ai>|test [ai]|register]");
      return cmd === "help" || cmd === "--help" ? 0 : 1;
  }
}

if (import.meta.main) main().then((c) => process.exit(c), (e) => (process.stderr.write(`ais: ${String(e.message || e).slice(0, 300)}\n`), process.exit(1)));
