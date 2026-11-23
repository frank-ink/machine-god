// Machine God fusion MCP server (stdio, no dependencies, runs on the bundled Bun).
// Tools: ask_<ai>(prompt) for every AI you connected with `machine-god ais connect`, and ask_all(prompt) (asks all, labelled answers).
// Register once:  claude mcp add --scope user machine-god-fusion -- <bun> <this file>
// The list of tools is read from ais.json on every tools/list, so connecting or disconnecting needs no re-registration.
import { resolvePaths } from "../firstrun/mg-common.js";
import { PROVIDERS, askAll, askProvider, connectedIds, formatAll } from "./fusion.js";

const promptSchema = { type: "object", properties: { prompt: { type: "string", description: "The full question or task." } }, required: ["prompt"] };

export function toolList(env = process.env) {
  const { configDir } = resolvePaths({ env });
  const ids = connectedIds(configDir);
  const tools = ids.map((id) => ({
    name: `ask_${id}`,
    description: `Ask ${PROVIDERS[id].label} (connected by the user) and return its answer as text. Use for a second opinion or research. Nothing else is sent: only your prompt.`,
    inputSchema: promptSchema,
  }));
  tools.push({
    name: "ask_all",
    description: `Ask every connected AI (${ids.length ? ids.join(", ") : "none connected yet: run `machine-god ais`"}) the same prompt in parallel and return each answer labelled with the AI's name.`,
    inputSchema: promptSchema,
  });
  return tools;
}

export async function callTool(name, args, env = process.env) {
  const prompt = args?.prompt;
  if (typeof prompt !== "string" || !prompt.trim()) return { text: "prompt required", isError: true };
  const paths = resolvePaths({ env });
  const ids = connectedIds(paths.configDir);
  try {
    if (name === "ask_all") {
      if (!ids.length) return { text: "No AIs connected. Run: machine-god ais", isError: true };
      const rs = await askAll(prompt, { env, paths, ids });
      return { text: formatAll(rs), isError: rs.every((r) => !r.ok) };
    }
    const m = /^ask_([a-z]+)$/.exec(name || "");
    if (!m || !ids.includes(m[1])) return { text: `unknown or not connected: ${name}`, isError: true };
    return { text: await askProvider(m[1], prompt, { env, paths }), isError: false };
  } catch (e) {
    return { text: `${name} failed: ${String(e.message || e).slice(0, 300)}`, isError: true };
  }
}

export async function handle(msg, env = process.env) {
  const id = msg.id;
  switch (msg.method) {
    case "initialize": {
      const pv = msg.params?.protocolVersion || "2024-11-05";
      return { jsonrpc: "2.0", id, result: { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: { name: "machine-god-fusion", version: "1" } } };
    }
    case "ping":
      return { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return { jsonrpc: "2.0", id, result: { tools: toolList(env) } };
    case "tools/call": {
      const r = await callTool(msg.params?.name, msg.params?.arguments, env);
      return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: r.text }], isError: r.isError } };
    }
    default:
      return id === undefined || id === null ? null : { jsonrpc: "2.0", id, error: { code: -32601, message: "method not found" } };
  }
}

async function serve() {
  let buf = "";
  const pending = new Set();
  const onLine = async (line) => {
    if (!line.trim()) return;
    let reply;
    try {
      reply = await handle(JSON.parse(line));
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
}

if (import.meta.main) serve().then(() => process.exit(0));
