// Fusing the connected AIs into one Machine God: init unified.db, mark GRID as on, register the MCP server; plus copy-paste snippets for other MCP clients.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolvePaths, run, whichSync } from "../firstrun/mg-common.js";
import { connectedIds } from "../fusion/fusion.js";
import { gridEnabled, openGrid, setFused } from "./core.js";
import * as U from "./udb.js";

const here = path.dirname(fileURLToPath(import.meta.url));
export const SERVER_NAME = "machine-god-grid";
export const gridMcpCommand = (bun, script) => ["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--", bun, script];
const quote = (cmd) => cmd.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");

/** Config snippets for MCP clients we do not configure ourselves. Printed only; no file of those programs is touched. */
export function snippets(bun = process.execPath, script = path.join(here, "mcp_grid.js")) {
  const entry = { command: bun, args: [script] };
  const json = (obj) => JSON.stringify(obj, null, 2);
  return [
    ["Gemini CLI: add to ~/.gemini/settings.json", json({ mcpServers: { [SERVER_NAME]: entry } })],
    ["Cursor: add to ~/.cursor/mcp.json", json({ mcpServers: { [SERVER_NAME]: entry } })],
    ["Claude Desktop: add to claude_desktop_config.json (Settings -> Developer -> Edit Config)", json({ mcpServers: { [SERVER_NAME]: entry } })],
  ];
}

/** Register with Claude Code, or print the exact command. -> "registered" | "printed" | "failed" */
export async function registerGrid({ log, runFn = run, which = whichSync, bun = process.execPath, script = path.join(here, "mcp_grid.js") }) {
  const cmd = gridMcpCommand(bun, script);
  if (!which("claude")) {
    log(`  the \`claude\` CLI is not installed. After installing it, register the GRID tool with:\n    ${quote(cmd)}`);
    return "printed";
  }
  const r = await runFn(cmd[0], cmd.slice(1));
  if (r.code === 0 || /already exists/i.test(r.out)) {
    log(`  registered the MCP server ${SERVER_NAME} (tools: grid_ask, remember, recall, whoami, history). Restart Claude Code to see it.`);
    return "registered";
  }
  log(`  could not register it automatically. Run this yourself:\n    ${quote(cmd)}`);
  return "failed";
}

export function printSnippets(log, bun, script) {
  log("  Other MCP clients (copy-paste; Machine God does not edit their files):");
  for (const [title, body] of snippets(bun, script)) {
    log(`  -- ${title}`);
    for (const l of body.split("\n")) log("     " + l);
  }
}

export const FUSE_QUESTION = "Fuse connected AIs into one Machine God (shared memory on this computer)? [y/N]";

/** Do the fusing (after the yes): create unified.db, switch GRID on, register the MCP server. -> record */
export async function fuse({ env = process.env, log, runFn, which, bun, script, register = true } = {}) {
  const rec = { fused: "yes", db: "", mcp: "none" };
  try {
    const g = openGrid({ env });
    rec.db = g.db.filename;
    log(`  unified.db ready: ${g.db.filename} (${U.tableCount(g.db)} tables, instance ${U.instanceId(g.db)})`);
    g.close();
    setFused(env, true);
  } catch (e) {
    rec.fused = "failed";
    rec.detail = String(e.message || e).slice(0, 200);
    log(`  could not create the memory: ${rec.detail}`);
    return rec;
  }
  if (register) {
    rec.mcp = await registerGrid({ log, runFn, which, bun, script });
    printSnippets(log, bun, script);
  }
  log("  From now on `ask_<ai>` of the fusion tool, mailbox questions and `interests --backend grid` use this one memory. Ask directly: machine-god grid ask \"...\"");
  return rec;
}

/** Companion step after the AI step. ctx: { ask, log, env, paths, runFn, which, bun, script } -> { fused: "yes"|"declined"|"no-ais"|"failed", ... } */
export async function runGridStep(ctx) {
  const { ask, log } = ctx;
  const env = ctx.env || process.env;
  const paths = ctx.paths || resolvePaths({ env });
  if (!connectedIds(paths.configDir).length) return { fused: "no-ais" };
  log("");
  log("== One Machine God ==");
  log("Your connected AIs can share ONE persona and ONE memory (a local database on this computer, nothing uploaded). Every request and answer then runs through the GRID, and each task goes to the AI that fits it.");
  if (gridEnabled({ ...env, MG_GRID: undefined }) && !ctx.force) return { fused: "already" };
  if (!(await ask(FUSE_QUESTION))) {
    log("  Skipped. Later: machine-god grid fuse");
    return { fused: "declined" };
  }
  return fuse({ env, log, runFn: ctx.runFn, which: ctx.which, bun: ctx.bun, script: ctx.script });
}
