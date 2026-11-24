// Machine God GRID MCP server (stdio, no dependencies, runs on the bundled Bun).
// Tools: grid_ask(prompt, task_hint?), remember(text), recall(query), whoami, history(n).
// Register once:  claude mcp add --scope user machine-god-grid -- <bun> <this file>   (`machine-god grid fuse` does it after your yes)
// Every client that uses this server shares the same persona and the same unified.db memory.
import { formatAsk, formatWhoami, openGrid } from "./core.js";
import { autoSync } from "./sync.js";

const S = (props, required = []) => ({ type: "object", properties: props, required });
export const TOOLS = [
  {
    name: "grid_ask",
    description:
      "Ask Machine God: one entity across all connected AIs with one shared memory. The request goes through the GRID (memory recall + persona), is routed to the connected AI whose capabilities fit (web search, images, code execution, long context, local/private, connectors), and the answer says which AI answered. " +
      "Use it when a task needs another AI's own tools or when earlier context from other AIs matters. task_hint: auto (default) | web_search | images | code_exec | long_context | private | connectors | code | ai:<name> | all (ask every connected AI).",
    inputSchema: S({ prompt: { type: "string", description: "The full question or task." }, task_hint: { type: "string", description: "Optional routing hint." } }, ["prompt"]),
  },
  { name: "remember", description: "Save a durable fact or note into the shared Machine God memory (unified.db). Never put secrets in it.", inputSchema: S({ text: { type: "string" } }, ["text"]) },
  { name: "recall", description: "Search the shared Machine God memory; returns the best matching saved facts and notes.", inputSchema: S({ query: { type: "string" }, k: { type: "integer", description: "How many (default 5)." } }, ["query"]) },
  { name: "whoami", description: "Machine God's persona, connected AIs and their declared capabilities, and memory statistics.", inputSchema: S({}) },
  { name: "history", description: "The last n answered requests (who asked, which AI answered).", inputSchema: S({ n: { type: "integer", description: "Default 10." } }) },
];

/** The client that calls us is itself an AI; asking the same AI through the GRID would only loop back. */
export function selfIdFromClient(name) {
  const n = String(name || "").toLowerCase();
  if (/claude/.test(n)) return "claude";
  if (/gemini/.test(n)) return "gemini";
  if (/chatgpt|openai|codex/.test(n)) return "chatgpt";
  if (/copilot/.test(n)) return "copilot";
  return null;
}
const slug = (s) => String(s || "client").toLowerCase().replace(/[^a-z0-9._-]+/g, "-").slice(0, 40) || "client";

export async function callTool(name, args, { env = process.env, client = "", openOpts = {} } = {}) {
  const asker = `mcp:${slug(client)}`;
  const a = args && typeof args === "object" ? args : {};
  let g;
  try {
    g = openGrid({ env, ...openOpts });
  } catch (e) {
    return { text: `GRID memory unavailable: ${String(e.message || e).slice(0, 300)}`, isError: true };
  }
  try {
    switch (name) {
      case "grid_ask": {
        if (typeof a.prompt !== "string" || !a.prompt.trim()) return { text: "prompt required", isError: true };
        const self = selfIdFromClient(client);
        const hint = typeof a.task_hint === "string" ? a.task_hint : "auto";
        const exclude = self && hint.toLowerCase() !== `ai:${self}` ? [self] : [];
        if (hint.toLowerCase() === "all") {
          const r = await g.askAll(a.prompt, { asker, exclude, autofacts: true });
          return { text: r.text, isError: !r.ok };
        }
        const r = await g.ask(a.prompt, { hint, asker, exclude, autofacts: true });
        return { text: formatAsk(r), isError: false };
      }
      case "remember": {
        if (typeof a.text !== "string" || !a.text.trim()) return { text: "text required", isError: true };
        const r = g.remember(a.text, { by: asker });
        return r.refused ? { text: `not saved: ${r.refused}`, isError: true } : { text: r.added ? `saved (${r.id})` : `already known (${r.id})`, isError: false };
      }
      case "recall": {
        if (typeof a.query !== "string" || !a.query.trim()) return { text: "query required", isError: true };
        const hits = g.recall(a.query, { k: Math.min(20, Math.max(1, Number(a.k) || 5)) });
        return { text: hits.length ? hits.map((m) => `- (${m.id}, ${m.kind}${m.ai ? `, ${m.ai}` : ""}) ${m.subject ? m.subject + ": " : ""}${m.value}`).join("\n") : "nothing found", isError: false };
      }
      case "whoami":
        return { text: formatWhoami(g.whoami()), isError: false };
      case "history": {
        const rows = g.history(Math.min(50, Math.max(1, Number(a.n) || 10)));
        return { text: rows.length ? rows.map((h) => `${new Date(h.ts * 1000).toISOString().slice(0, 19)}Z ${h.asker || "?"} -> ${h.ai || "?"}\n  Q: ${String(h.prompt).slice(0, 200)}\n  A: ${String(h.answer).slice(0, 300)}`).join("\n") : "no history yet", isError: false };
      }
      default:
        return { text: `unknown tool: ${name}`, isError: true };
    }
  } catch (e) {
    return { text: `${name} failed: ${String(e.message || e).slice(0, 400)}`, isError: true };
  } finally {
    g.close();
  }
}

export async function handle(msg, ctx = {}) {
  const id = msg.id;
  const env = ctx.env || process.env;
  switch (msg.method) {
    case "initialize": {
      ctx.client = msg.params?.clientInfo?.name || ctx.client || "";
      const pv = msg.params?.protocolVersion || "2024-11-05";
      return { jsonrpc: "2.0", id, result: { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: { name: "machine-god-grid", version: "1" } } };
    }
    case "ping":
      return { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
    case "tools/call": {
      const r = await callTool(msg.params?.name, msg.params?.arguments, { env, client: ctx.client, openOpts: ctx.openOpts });
      return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: r.text }], isError: r.isError } };
    }
    default:
      return id === undefined || id === null ? null : { jsonrpc: "2.0", id, error: { code: -32601, message: "method not found" } };
  }
}

async function serve() {
  const ctx = { env: process.env, client: "" };
  try {
    const g = openGrid({ env: process.env });
    autoSync(g.db, { env: process.env, paths: g.paths }); // import what other computers saved
    g.close();
  } catch {}
  let buf = "";
  const pending = new Set();
  const onLine = async (line) => {
    if (!line.trim()) return;
    let reply;
    try {
      reply = await handle(JSON.parse(line), ctx);
    } catch (e) {
      reply = { jsonrpc: "2.0", id: null, error: { code: -32603, message: String(e.message || e).slice(0, 200) } };
    }
    if (reply) process.stdout.write(JSON.stringify(reply) + "\n");
  };
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (d) => {
    buf += d;
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i);
      buf = buf.slice(i + 1);
      const p = onLine(line).finally(() => pending.delete(p));
      pending.add(p);
    }
  });
  await new Promise((r) => process.stdin.on("end", r));
  await Promise.all(pending);
  try {
    const g = openGrid({ env: process.env });
    autoSync(g.db, { env: process.env, paths: g.paths }); // push what was learned
    g.close();
  } catch {}
}

if (import.meta.main) serve().then(() => process.exit(0));
