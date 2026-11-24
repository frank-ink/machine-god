// machine-god grid <command>   (the launcher runs this file for `machine-god grid ...`)
//   ask [--ai <name>|--hint <task>|--all] "<prompt>"   one question through the GRID (memory + persona + routing), answer labelled with the AI that answered
//   route "<prompt>"          show which AI would take it and why (nothing is sent)
//   recall "<query>"          search the shared memory        remember "<text>"   save a note       forget <id>   delete one memory
//   whoami                    persona, connected AIs, capabilities, memory stats
//   history [n]               last answered requests          status              GRID state, MCP registration, sync
//   persona [show|set "<text>"|reset]   caps [path]           sync [on|off|now|status]
//   init | fuse [--yes] | register | snippets                 set up the shared memory and the MCP server
//   repo [...]                the private GitHub GRID repo (SSH key, repo, mailbox layout): what `machine-god grid` was before
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeAsker, resolvePaths } from "../firstrun/mg-common.js";
import { connectedIds } from "../fusion/fusion.js";
import { capabilitiesOverrideFile, describeCaps, loadCapabilities } from "./capabilities.js";
import { formatAsk, formatWhoami, gridEnabled, openGrid } from "./core.js";
import { FUSE_QUESTION, fuse, gridMcpCommand, printSnippets, registerGrid } from "./setup.js";
import { autoSync, repoDir, repoReady, setSync, syncMode, syncNow } from "./sync.js";
import * as U from "./udb.js";

const here = path.dirname(fileURLToPath(import.meta.url));

export const USAGE = `usage: machine-god grid <command>
  ask [--ai <name> | --hint <task> | --all] "<prompt>"   one question through the GRID (shared memory, one persona, routed by capability)
  route "<prompt>"        which AI would take it and why (nothing is sent)
  recall "<query>"        search the shared memory       remember "<text>"   save a note       forget <id>
  whoami                  persona, connected AIs and capabilities     history [n]    last answers     status
  persona [show|set "<text>"|reset]      caps [path]      sync [on|off|now|status]
  init | fuse [--yes] | register | snippets             set up the shared memory (unified.db) and the MCP server
  repo [...]              the private GitHub GRID repo (SSH, mailbox, memory sync target); same as the old \`machine-god grid\`
tasks for --hint: auto web_search images code_exec long_context private connectors code`;

function takeFlag(args, name, hasValue) {
  const i = args.indexOf(name);
  if (i < 0) return hasValue ? undefined : false;
  const v = hasValue ? args[i + 1] : true;
  args.splice(i, hasValue ? 2 : 1);
  return v;
}

async function readStdin() {
  let s = "";
  process.stdin.setEncoding("utf8");
  for await (const c of process.stdin) s += c;
  return s;
}

export async function main(argv = process.argv.slice(2), env = process.env, out = process.stdout) {
  const w = (s = "") => out.write(s + "\n");
  const [cmd, ...rest] = argv;
  const paths = resolvePaths({ env });
  if (cmd === "repo") {
    const { main: repoMain } = await import("../firstrun/mg-github.js");
    return repoMain(rest, env);
  }
  if (!cmd || cmd === "help" || cmd === "--help" || cmd === "-h") {
    w(USAGE);
    if (!cmd) {
      w("");
      w(`GRID memory: ${gridEnabled(env) ? "on" : "off (machine-god grid fuse)"}   GitHub repo: ${repoReady(repoDir(env, paths)) ? "set up" : "not set up (machine-god grid repo)"}`);
    }
    return 0;
  }
  const withGrid = async (fn) => {
    let g;
    try {
      g = openGrid({ env });
    } catch (e) {
      w(`grid: ${String(e.message || e).slice(0, 300)}`);
      return 1;
    }
    try {
      return await fn(g);
    } finally {
      g.close();
    }
  };
  const textArg = async (args) => {
    const t = args.join(" ").trim();
    if (t && t !== "-") return t;
    return process.stdin.isTTY ? "" : (await readStdin()).trim();
  };

  switch (cmd) {
    case "ask": {
      const args = [...rest];
      const ai = takeFlag(args, "--ai", true);
      const hint = takeFlag(args, "--hint", true);
      const all = takeFlag(args, "--all", false);
      const noLearn = takeFlag(args, "--no-learn", false);
      const prompt = await textArg(args);
      if (!prompt) {
        w('usage: machine-god grid ask [--ai <name> | --hint <task> | --all] "<prompt>"');
        return 1;
      }
      return withGrid(async (g) => {
        autoSync(g.db, { env, paths });
        try {
          if (all) {
            const r = await g.askAll(prompt, { asker: "cli", autofacts: true, learn: !noLearn });
            w(r.text);
            autoSync(g.db, { env, paths });
            return r.ok ? 0 : 2;
          }
          const r = await g.ask(prompt, { asker: "cli", autofacts: true, learn: !noLearn, hint: ai ? `ai:${ai}` : hint || "auto" });
          w(formatAsk(r));
          if (r.stored.length) w(`\n(${r.stored.length} new memor${r.stored.length === 1 ? "y" : "ies"} saved: machine-god grid recall)`);
          autoSync(g.db, { env, paths });
          return 0;
        } catch (e) {
          w(`grid ask failed: ${String(e.message || e).slice(0, 500)}`);
          return 2;
        }
      });
    }
    case "route": {
      const prompt = await textArg(rest);
      if (!prompt) return (w('usage: machine-god grid route "<prompt>"'), 1);
      return withGrid((g) => {
        const r = g.route(prompt);
        w(`tasks: ${r.tasks.join(", ")}${r.reasons.length ? `  (${r.reasons.join("; ")})` : ""}`);
        if (!r.connected.length) w("no AIs connected: machine-god ais");
        else if (!r.ranked.length) w("nobody qualifies (a private task needs a local model: machine-god ais connect local)");
        for (const [i, c] of r.ranked.entries()) w(`${i === 0 ? "->" : "  "} ${c.id.padEnd(10)} score ${c.score}${c.missing.length ? `  lacks: ${c.missing.join(", ")}` : ""}  ${c.why}`);
        return 0;
      });
    }
    case "recall": {
      const q = await textArg(rest);
      if (!q) return (w('usage: machine-god grid recall "<query>"'), 1);
      return withGrid((g) => {
        autoSync(g.db, { env, paths });
        const hits = g.recall(q, { k: 8 });
        if (!hits.length) w("nothing found");
        for (const m of hits) w(`${m.id}  ${m.kind}${m.ai ? `/${m.ai}` : m.by ? `/${m.by}` : ""}  ${new Date(m.ts * 1000).toISOString().slice(0, 10)}  ${m.subject ? m.subject + ": " : ""}${m.value}`);
        return 0;
      });
    }
    case "remember": {
      const t = await textArg(rest);
      if (!t) return (w('usage: machine-god grid remember "<text>"'), 1);
      return withGrid((g) => {
        const r = g.remember(t, { by: "user" });
        w(r.refused ? `not saved: ${r.refused}` : r.added ? `saved (${r.id})` : `already known (${r.id})`);
        if (!r.refused) autoSync(g.db, { env, paths });
        return r.refused ? 1 : 0;
      });
    }
    case "forget": {
      if (!rest[0]) return (w("usage: machine-god grid forget <memory id or its first characters>"), 1);
      return withGrid((g) => {
        const r = g.forget(rest[0]);
        w(r.removed ? `forgot ${r.id}` : r.matches ? `${r.matches} memories match; give more characters` : "no such memory");
        return r.removed ? 0 : 1;
      });
    }
    case "whoami":
      return withGrid((g) => {
        autoSync(g.db, { env, paths });
        w(formatWhoami(g.whoami()));
        return 0;
      });
    case "history": {
      const n = Number(rest[0]) || 10;
      return withGrid((g) => {
        const rows = g.history(n);
        if (!rows.length) w("no history yet");
        for (const h of rows) w(`${new Date(h.ts * 1000).toISOString().slice(0, 19)}Z  ${h.asker || "?"} -> ${h.ai || "?"}\n  Q: ${String(h.prompt).replace(/\s+/g, " ").slice(0, 160)}\n  A: ${String(h.answer).replace(/\s+/g, " ").slice(0, 240)}`);
        return 0;
      });
    }
    case "status": {
      const have = connectedIds(paths.configDir);
      w(`GRID on: ${gridEnabled(env) ? "yes (fusion ask_*, mailbox questions and interests --backend grid use it)" : "no (machine-god grid fuse)"}`);
      w(`memory file: ${U.dbFile(env)} ${fs.existsSync(U.dbFile(env)) ? "(exists)" : "(not created yet)"}`);
      w(`connected AIs: ${have.join(", ") || "none"}`);
      if (fs.existsSync(U.dbFile(env))) {
        return withGrid((g) => {
          const s = U.stats(g.db);
          w(`instance ${s.instance}: ${s.memories} memories, ${s.turns} turns, ${s.answers} answers, ${s.tables} tables`);
          w(`answered by: ${s.answered_by.map((r) => `${r.a} ${r.n}`).join(", ") || "nobody yet"}   askers: ${s.askers.join(", ") || "none"}`);
          w(`memory sync with the GRID repo: ${syncMode(g.db)} (repo ${repoReady(repoDir(env, paths)) ? "present" : "missing"})`);
          w(`MCP: ${gridMcpCommand(process.execPath, path.join(here, "mcp_grid.js")).join(" ")}`);
          return 0;
        });
      }
      return 0;
    }
    case "persona":
      return withGrid((g) => {
        const sub = rest[0] || "show";
        if (sub === "show") w(g.persona());
        else if (sub === "set") {
          const t = rest.slice(1).join(" ").trim();
          if (!t) return (w('usage: machine-god grid persona set "<text>"'), 1);
          if (U.looksSecret(t)) return (w("not saved: looks like a secret"), 1);
          U.setPersonaOverride(g.db, t.slice(0, 4000));
          w("persona saved (it is used for every AI from the next request)");
        } else if (sub === "reset") {
          U.setPersonaOverride(g.db, null);
          w("persona reset to the default");
        } else return (w('usage: machine-god grid persona [show|set "<text>"|reset]'), 1);
        return 0;
      });
    case "caps": {
      const file = capabilitiesOverrideFile(paths.configDir);
      if (rest[0] === "path") return (w(file), 0);
      const c = loadCapabilities(paths.configDir);
      const have = connectedIds(paths.configDir);
      for (const [id, a] of Object.entries(c.ais)) w(`${id.padEnd(10)} ${have.includes(id) ? "connected    " : "not connected"} ${describeCaps(a)}\n           ${a.notes}`);
      w(`\npriority: ${c.priority.join(" > ")}`);
      w(`your overrides: ${file} ${fs.existsSync(file) ? "(present)" : '(create it, e.g. {"ais":{"gemini":{"capabilities":{"web_search":true}}}}, to change a default)'}`);
      return 0;
    }
    case "sync": {
      const sub = rest[0] || "status";
      return withGrid((g) => {
        if (sub === "on" || sub === "off") {
          setSync(g.db, sub === "on");
          w(`memory sync ${sub}.${sub === "on" ? ` New memories are written to memory/ in your GRID repo (${repoDir(env, paths)}) and other computers' notes are imported. Keep the repo private; never remember secrets.` : ""}`);
          if (sub === "on" && !repoReady(repoDir(env, paths))) w("note: no GRID repo clone yet; run `machine-god grid repo` first.");
          return 0;
        }
        if (sub === "now") {
          const r = syncNow(g.db, { env, paths });
          w(`${r.ok ? "sync ok" : "sync failed"}: ${r.detail}`);
          return r.ok ? 0 : 1;
        }
        w(`memory sync: ${syncMode(g.db)}; repo: ${repoDir(env, paths)} ${repoReady(repoDir(env, paths)) ? "(present)" : "(missing)"}`);
        return 0;
      });
    }
    case "init":
      return withGrid((g) => {
        w(`unified.db ready: ${g.db.filename} (${U.tableCount(g.db)} tables, instance ${U.instanceId(g.db)})`);
        return 0;
      });
    case "fuse": {
      const log = (s = "") => w(s);
      if (!connectedIds(paths.configDir).length) return (w("no AIs connected yet: machine-god ais"), 1);
      const asker = makeAsker({ env });
      try {
        if (!rest.includes("--yes") && !(await asker(FUSE_QUESTION))) return (w("not fused."), 0);
        const r = await fuse({ env, log });
        return r.fused === "failed" ? 1 : 0;
      } finally {
        asker.close();
      }
    }
    case "register": {
      const r = await registerGrid({ log: w });
      printSnippets(w);
      return r === "failed" ? 1 : 0;
    }
    case "snippets":
      printSnippets(w);
      return 0;
    default:
      w(USAGE);
      return 1;
  }
}

if (import.meta.main) main().then((c) => process.exit(c), (e) => (process.stderr.write(`grid: ${String(e.message || e).slice(0, 300)}\n`), process.exit(1)));
