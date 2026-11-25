import { afterAll, describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { makeAsker } from "../firstrun/mg-common.js";
import * as F from "./fusion.js";
import * as A from "./ais.js";
import * as M from "./mcp_fusion.js";

const tmp = () => fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mg-fu-")));
const MOCKKEY = "MOCKKEY-0123456789-not-a-real-key";
const servers = [];
const mock = (fn) => {
  const s = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: fn });
  servers.push(s);
  return `http://127.0.0.1:${s.port}`;
};
afterAll(() => servers.forEach((s) => s.stop(true)));
const mkEnv = (extra = {}) => {
  const d = tmp();
  return { d, env: { MG_CONFIG_DIR: d, MG_DATA_DIR: d, PATH: process.env.PATH, ...extra } };
};
const sink = () => {
  const lines = [];
  return { lines, out: { write: (s) => lines.push(s) }, log: (s = "") => lines.push(s + "\n"), text: () => lines.join("") };
};
const geminiMock = (seen = []) =>
  mock(async (req) => {
    const u = new URL(req.url);
    seen.push({ path: u.pathname, search: u.search, key: req.headers.get("x-goog-api-key"), body: await req.json() });
    if (req.headers.get("x-goog-api-key") !== MOCKKEY) return Response.json({ error: { message: `bad key ${req.headers.get("x-goog-api-key")}` } }, { status: 400 });
    return Response.json({ candidates: [{ content: { parts: [{ text: "gemini says hi" }] } }] });
  });
const chatMock = (answer, seen = []) =>
  mock(async (req) => {
    seen.push({ auth: req.headers.get("authorization"), url: req.url, body: await req.json() });
    return Response.json({ choices: [{ message: { content: answer } }] });
  });

describe("keys and connections on disk", () => {
  test("keys.json is mode 600, ais.json holds no secret, disconnect removes the key", () => {
    const { d } = mkEnv();
    F.saveKey(d, "gemini", MOCKKEY);
    F.connect(d, "gemini", { test: "ok" });
    if (process.platform !== "win32") {
      expect(fs.statSync(F.keysFile(d)).mode & 0o777).toBe(0o600);
      expect(fs.statSync(F.aisFile(d)).mode & 0o777).toBe(0o600);
    }
    expect(fs.readFileSync(F.aisFile(d), "utf8")).not.toContain(MOCKKEY);
    expect(F.loadKeys(d).gemini.key).toBe(MOCKKEY);
    expect(F.disconnect(d, d, "gemini")).toBe(true);
    expect(F.loadKeys(d).gemini).toBeUndefined();
    expect(F.connectedIds(d)).toEqual([]);
  });
  test("scrub removes the key and key-shaped strings", () => {
    expect(F.scrub(`oops ${MOCKKEY} and AIza${"a".repeat(35)} and ghp_${"b".repeat(30)}`, [MOCKKEY])).toBe("oops [key] and [key] and [key]");
    expect(F.keyHash(MOCKKEY)).toBe(`${MOCKKEY.length} chars`);
  });
  test("key shape", () => {
    expect(F.validKeyShape(MOCKKEY)).toBe(true);
    for (const bad of ["", "short", "has space in it 123456", "x".repeat(401), null]) expect(F.validKeyShape(bad)).toBe(false);
  });
});

describe("asking providers (mock HTTP)", () => {
  test("gemini: key only in the x-goog-api-key header, never in the URL", async () => {
    const seen = [];
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock(seen) });
    F.saveKey(d, "gemini", MOCKKEY);
    F.connect(d, "gemini");
    expect(await F.askProvider("gemini", "hello", { env })).toBe("gemini says hi");
    expect(seen[0].key).toBe(MOCKKEY);
    expect(seen[0].path).toBe("/v1beta/models/gemini-flash-latest:generateContent");
    expect(seen[0].search).toBe("");
    expect(seen[0].body.contents[0].parts[0].text).toBe("hello");
  });
  test("an error that echoes the key is scrubbed", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: mock(() => Response.json({ error: { message: `invalid key ${MOCKKEY}` } }, { status: 403 })) });
    F.saveKey(d, "gemini", MOCKKEY);
    const e = await F.askProvider("gemini", "x", { env }).catch((x) => x);
    expect(e.message).toContain("HTTP 403");
    expect(e.message).not.toContain(MOCKKEY);
    expect(e.message).toContain("[key]");
  });
  test("grok, perplexity, copilot: OpenAI-style request with a Bearer header", async () => {
    for (const [id, model] of [["grok", "grok-3-mini"], ["perplexity", "sonar"], ["copilot", "openai/gpt-4.1-mini"]]) {
      const seen = [];
      const { d, env } = mkEnv({ [`MG_FUSION_BASE_${id.toUpperCase()}`]: chatMock(`${id} answer`, seen) });
      F.saveKey(d, id, MOCKKEY);
      expect(await F.askProvider(id, "q", { env })).toBe(`${id} answer`);
      expect(seen[0].auth).toBe(`Bearer ${MOCKKEY}`);
      expect(seen[0].body.model).toBe(model);
      expect(seen[0].url).not.toContain(MOCKKEY);
    }
  });
  test("no key stored -> clear error, no request", async () => {
    const { env } = mkEnv();
    await expect(F.askProvider("grok", "q", { env })).rejects.toThrow(/no key stored for grok/);
  });
  test("timeout is reported", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GROK: mock(async () => (await Bun.sleep(400), Response.json({}))) });
    F.saveKey(d, "grok", MOCKKEY);
    await expect(F.askProvider("grok", "q", { env, timeoutMs: 100 })).rejects.toThrow(/timeout/);
  });
  test("testProvider: ok and fail, never the key", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock() });
    F.saveKey(d, "gemini", MOCKKEY);
    expect(await F.testProvider("gemini", { env })).toMatchObject({ ok: true });
    F.saveKey(d, "gemini", "WRONG-KEY-0123456789");
    const t = await F.testProvider("gemini", { env });
    expect(t.ok).toBe(false);
    expect(JSON.stringify(t)).not.toContain(MOCKKEY);
  });
  test("claude goes through the injected CLI runner with the prompt on stdin", async () => {
    const { env } = mkEnv();
    let got;
    const cli = async (cmd, args, o) => ((got = { cmd, args, input: o.input }), { code: 0, out: JSON.stringify({ result: "claude says hi", is_error: false }), err: "" });
    expect(await F.askProvider("claude", "hey", { env, cli })).toBe("claude says hi");
    expect(got).toMatchObject({ cmd: "claude", args: ["-p", "--output-format", "json"], input: "hey" });
    await expect(F.askProvider("claude", "hey", { env, cli: async () => ({ code: 1, out: "", err: "not logged in" }) })).rejects.toThrow(/claude failed/);
  });
});

describe("local probe", () => {
  const ollama = (models) => mock((req) => (req.url.endsWith("/api/tags") ? Response.json({ models: models.map((name) => ({ name })) }) : Response.json({ message: { content: "ollama says hi" } })));
  const lm = (models) => mock((req) => (req.url.endsWith("/v1/models") ? Response.json({ data: models.map((id) => ({ id })) }) : Response.json({ choices: [{ message: { content: "lm says hi" } }] })));
  test("finds Ollama and LM Studio, lists models; nothing running -> empty", async () => {
    const env = { MG_OLLAMA_URL: ollama(["llama3:8b", "qwen3:4b"]), MG_LMSTUDIO_URL: lm(["some-model"]) };
    expect(await F.probeLocal({ env })).toEqual([
      { kind: "lmstudio", url: env.MG_LMSTUDIO_URL, models: ["some-model"] },
      { kind: "ollama", url: env.MG_OLLAMA_URL, models: ["llama3:8b", "qwen3:4b"] },
    ]);
    expect(await F.probeLocal({ env: { MG_OLLAMA_URL: "http://127.0.0.1:1", MG_LMSTUDIO_URL: "http://127.0.0.1:1" }, ms: 500 })).toEqual([]);
  });
  test("embedding-only models are never the default chat model", async () => {
    expect(F.chatModels(["bge-m3:latest", "nomic-embed-text:latest", "qwen2.5:0.5b", "all-minilm"])).toEqual(["qwen2.5:0.5b"]);
    const o = mock(() => Response.json({ models: [{ name: "bge-m3:latest" }] }));
    const { env } = mkEnv({ MG_OLLAMA_URL: o, MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    const s = sink();
    const asker = makeAsker({ env: { ...env, MG_FIRSTRUN_ANSWERS: "" }, output: s.out });
    const r = await A.connectAI("local", { ask: asker, text: asker.text, secret: asker.secret, log: s.log, paths: { configDir: env.MG_CONFIG_DIR, dataDir: env.MG_DATA_DIR }, env });
    expect(r.status).toBe("failed");
    await expect(F.askProvider("local", "q", { env })).rejects.toThrow(/no chat model/);
  });
  test("ask local: chosen kind and model, strict kind option", async () => {
    const { d, env } = mkEnv({ MG_OLLAMA_URL: ollama(["m1"]), MG_LMSTUDIO_URL: lm(["m2"]) });
    F.connect(d, "local", { kind: "lmstudio", model: "m2" });
    expect(await F.askProvider("local", "q", { env })).toBe("lm says hi");
    expect(await F.askProvider("local", "q", { env, kind: "ollama" })).toBe("ollama says hi");
    await expect(F.askProvider("local", "q", { env: { ...env, MG_OLLAMA_URL: "http://127.0.0.1:1" }, kind: "ollama" })).rejects.toThrow(/no local model server/);
  });
});

describe("connecting (scripted answers, mock servers)", () => {
  test("parseSelection", () => {
    expect(A.parseSelection("1, 3").ids).toEqual(["chatgpt", "gemini"]);
    expect(A.parseSelection("Gemini, Ollama grok").ids).toEqual(["gemini", "local", "grok"]);
    expect(A.parseSelection("github models, lm studio").ids).toEqual(["copilot", "local"]);
    expect(A.parseSelection("none").ids).toEqual([]);
    expect(A.parseSelection("").ids).toEqual([]);
    expect(A.parseSelection("all").ids.length).toBe(7);
    expect(A.parseSelection("gemini, banana").unknown).toEqual(["banana"]);
  });
  const ctxFor = (env, answers) => {
    const s = sink();
    const e = { ...env, MG_FIRSTRUN_ANSWERS: answers };
    const asker = makeAsker({ env: e, output: s.out });
    return { s, ctx: { ask: asker, text: asker.text, secret: asker.secret, log: s.log, paths: { configDir: env.MG_CONFIG_DIR, dataDir: env.MG_DATA_DIR }, env }, asker };
  };
  test("gemini: key typed hidden, tested, stored 600, never printed", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock() });
    const { s, ctx } = ctxFor(env, `yes,${MOCKKEY}`);
    const r = await A.connectAI("gemini", ctx);
    expect(r).toEqual({ status: "connected", detail: "test ok" });
    const shown = s.text();
    expect(shown).not.toContain(MOCKKEY);
    expect(shown).toContain("https://aistudio.google.com/apikey");
    expect(shown).toContain("test: ok");
    expect(F.loadKeys(d).gemini.key).toBe(MOCKKEY);
    expect(F.connectedIds(d)).toEqual(["gemini"]);
  });
  test("a key that fails the test is dropped unless kept", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock() });
    const bad = "WRONG-KEY-0123456789";
    const a = ctxFor(env, `yes,${bad},no`);
    expect((await A.connectAI("gemini", a.ctx)).status).toBe("failed");
    expect(a.s.text()).not.toContain(bad);
    expect(F.loadKeys(d).gemini).toBeUndefined();
    expect(F.connectedIds(d)).toEqual([]);
    const b = ctxFor(env, `yes,${bad},yes`);
    expect((await A.connectAI("gemini", b.ctx)).status).toBe("connected");
    expect(F.loadKeys(d).gemini.key).toBe(bad);
  });
  test("saying no to the key prompt stores nothing; a malformed key is refused", async () => {
    const { d, env } = mkEnv();
    expect((await A.connectAI("grok", ctxFor(env, "no").ctx)).status).toBe("skipped");
    expect((await A.connectAI("grok", ctxFor(env, "yes,has space").ctx)).status).toBe("failed");
    expect(fs.existsSync(F.keysFile(d))).toBe(false);
  });
  test("each key AI shows its own key page", async () => {
    const { env } = mkEnv();
    const urls = { copilot: "https://github.com/settings/personal-access-tokens", grok: "https://console.x.ai", perplexity: "https://www.perplexity.ai/settings/api" };
    for (const [id, url] of Object.entries(urls)) {
      const c = ctxFor(env, "no");
      await A.connectAI(id, c.ctx);
      expect(c.s.text()).toContain(url);
    }
  });
  test("local: lists models and connects; nothing running -> skipped with install links", async () => {
    const o = mock((req) => Response.json({ models: [{ name: "qwen3:4b" }] }));
    const { d, env } = mkEnv({ MG_OLLAMA_URL: o, MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    const c = ctxFor(env, "");
    expect((await A.connectAI("local", c.ctx)).status).toBe("connected");
    expect(c.s.text()).toContain("qwen3:4b");
    expect(F.loadAis(d).connected.local).toMatchObject({ kind: "ollama", model: "qwen3:4b" });
    const none = mkEnv({ MG_OLLAMA_URL: "http://127.0.0.1:1", MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    const c2 = ctxFor(none.env, "");
    expect((await A.connectAI("local", c2.ctx)).status).toBe("skipped");
    expect(c2.s.text()).toContain("https://ollama.com/download");
  });
  test("claude: missing CLI -> docs link; present -> connected, login only if you say yes", async () => {
    const { d, env } = mkEnv();
    const a = ctxFor(env, "");
    expect((await A.connectAI("claude", { ...a.ctx, which: () => null })).status).toBe("skipped");
    expect(a.s.text()).toContain("https://docs.claude.com/en/docs/claude-code/setup");
    const ran = [];
    const b = ctxFor(env, "no");
    expect((await A.connectAI("claude", { ...b.ctx, which: () => "/bin/claude", runFn: async (c, a2) => (ran.push([c, a2]), { code: 0, out: "" }) })).status).toBe("connected");
    expect(ran).toEqual([]);
    const c = ctxFor(env, "yes");
    await A.connectAI("claude", { ...c.ctx, which: () => "/bin/claude", runFn: async (cmd, a2) => (ran.push([cmd, a2]), { code: 0, out: "" }) });
    expect(ran).toEqual([["claude", ["/login"]]]);
    expect(F.connectedIds(d)).toEqual(["claude"]);
  });
  test("chatgpt: shows the connectors link and the mailbox rule; connected only with a bridge", async () => {
    const { d, env } = mkEnv();
    const c = ctxFor(env, "no");
    expect((await A.connectAI("chatgpt", c.ctx)).status).toBe("skipped");
    expect(c.s.text()).toContain("https://chatgpt.com/#settings/Connectors");
    expect(c.s.text()).toContain("machine-god grid");
    fs.writeFileSync(path.join(d, "bridge.json"), "{}");
    expect((await A.connectAI("chatgpt", ctxFor(env, "").ctx)).status).toBe("connected");
  });
  test("the companion step: choose, confirm each, register once; 'none' connects nothing", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock(), MG_OLLAMA_URL: "http://127.0.0.1:1", MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    const reg = [];
    const c = ctxFor(env, `gemini grok,yes,yes,${MOCKKEY},no,yes`);
    const rec = await A.runAisStep({ ...c.ctx, which: () => "/bin/claude", runFn: async (cmd, args) => (reg.push([cmd, ...args]), { code: 0, out: "" }), bun: "/b/bun", script: "/i/fusion/mcp_fusion.js" });
    expect(rec.ais).toEqual({ gemini: "connected", grok: "declined" });
    expect(rec.mcp).toBe("registered");
    expect(reg).toEqual([["claude", "mcp", "add", "--scope", "user", "machine-god-fusion", "--", "/b/bun", "/i/fusion/mcp_fusion.js"]]);
    expect(c.s.text()).not.toContain(MOCKKEY);
    const n = ctxFor(env, "none");
    expect((await A.runAisStep({ ...n.ctx, paths: { configDir: tmp(), dataDir: tmp() } })).ais).toEqual({});
  });
  test("registerFusion prints the exact command when claude is missing; 'already exists' counts as registered", async () => {
    const s = sink();
    expect(await A.registerFusion({ log: s.log, which: () => null, bun: "/b/bun", script: "/i/f.js" })).toBe("printed");
    expect(s.text()).toContain("claude mcp add --scope user machine-god-fusion -- /b/bun /i/f.js");
    expect(await A.registerFusion({ log: () => {}, which: () => "/c", runFn: async () => ({ code: 1, out: "MCP server machine-god-fusion already exists" }) })).toBe("registered");
    expect(await A.registerFusion({ log: () => {}, which: () => "/c", runFn: async () => ({ code: 1, out: "boom" }) })).toBe("failed");
  });
});

describe("MCP server", () => {
  test("tools/list follows ais.json: ask_<ai> per connected AI plus ask_all", () => {
    const { d, env } = mkEnv();
    expect(M.toolList(env).map((t) => t.name)).toEqual(["ask_all"]);
    F.connect(d, "gemini");
    F.connect(d, "local", { kind: "ollama", model: "m" });
    expect(M.toolList(env).map((t) => t.name)).toEqual(["ask_gemini", "ask_local", "ask_all"]);
    expect(M.toolList(env)[0].inputSchema.required).toEqual(["prompt"]);
  });
  test("tools/call: single AI, ask_all labelled with one failure, unknown tool, empty prompt", async () => {
    const o = mock((req) => (req.url.endsWith("/api/tags") ? Response.json({ models: [{ name: "m1" }] }) : Response.json({ message: { content: "ollama says hi" } })));
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock(), MG_OLLAMA_URL: o, MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    F.saveKey(d, "gemini", MOCKKEY);
    F.connect(d, "gemini");
    F.connect(d, "local", {});
    F.connect(d, "grok"); // connected but key gone -> fails inside ask_all
    expect(await M.callTool("ask_gemini", { prompt: "hi" }, env)).toEqual({ text: "gemini says hi", isError: false });
    const all = await M.callTool("ask_all", { prompt: "hi" }, env);
    expect(all.isError).toBe(false);
    expect(all.text).toContain("## gemini\ngemini says hi");
    expect(all.text).toContain("## local\nollama says hi");
    expect(all.text).toContain("## grok (failed)");
    expect(all.text).not.toContain(MOCKKEY);
    expect((await M.callTool("ask_claude", { prompt: "hi" }, env)).isError).toBe(true);
    expect((await M.callTool("ask_gemini", { prompt: "" }, env)).isError).toBe(true);
  });
  test("stdio server: initialize, tools/list, tools/call over a real child process", async () => {
    const { d, env } = mkEnv({ MG_FUSION_BASE_GEMINI: geminiMock(), MG_OLLAMA_URL: "http://127.0.0.1:1", MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    F.saveKey(d, "gemini", MOCKKEY);
    F.connect(d, "gemini");
    const child = spawn(process.execPath, [path.join(import.meta.dir, "mcp_fusion.js")], { env, stdio: ["pipe", "pipe", "inherit"] });
    const msgs = [
      { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26" } },
      { jsonrpc: "2.0", method: "notifications/initialized" },
      { jsonrpc: "2.0", id: 2, method: "tools/list" },
      { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "ask_gemini", arguments: { prompt: "hi" } } },
      { jsonrpc: "2.0", id: 4, method: "nope" },
    ];
    let out = "";
    child.stdout.on("data", (x) => (out += x));
    child.stdin.end(msgs.map((m) => JSON.stringify(m)).join("\n") + "\n");
    await new Promise((r) => child.on("close", r));
    const rs = out.trim().split("\n").map((l) => JSON.parse(l));
    expect(rs.map((r) => r.id).sort()).toEqual([1, 2, 3, 4]);
    const by = (id) => rs.find((r) => r.id === id);
    expect(by(1).result.protocolVersion).toBe("2025-03-26");
    expect(by(2).result.tools.map((t) => t.name)).toEqual(["ask_gemini", "ask_all"]);
    expect(by(3).result.content[0].text).toBe("gemini says hi");
    expect(by(4).error.code).toBe(-32601);
    expect(out).not.toContain(MOCKKEY);
  });
});
