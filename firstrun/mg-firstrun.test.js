import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import * as mg from "./mg-firstrun.js";

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "mg-fr-"));

describe("paths", () => {
  test("linux uses ~/.config and ~/.local/share", () => {
    const p = mg.resolvePaths({ platform: "linux", env: {}, home: "/home/u" });
    expect(p.configDir).toBe("/home/u/.config/machine-god");
    expect(p.dataDir).toBe("/home/u/.local/share/machine-god");
    expect(p.stateFile).toBe("/home/u/.config/machine-god/firstrun.json");
  });
  test("windows uses APPDATA and LOCALAPPDATA", () => {
    const p = mg.resolvePaths({ platform: "win32", env: { APPDATA: "C:\\U\\AppData\\Roaming", LOCALAPPDATA: "C:\\U\\AppData\\Local" }, home: "C:\\U" });
    expect(p.configDir).toBe("C:\\U\\AppData\\Roaming\\machine-god");
    expect(p.dataDir).toBe("C:\\U\\AppData\\Local\\machine-god");
  });
  test("MG_CONFIG_DIR / MG_DATA_DIR override", () => {
    const p = mg.resolvePaths({ platform: "linux", env: { MG_CONFIG_DIR: "/c", MG_DATA_DIR: "/d" }, home: "/h" });
    expect(p.stateFile).toBe("/c/firstrun.json");
    expect(p.dataDir).toBe("/d");
  });
});

describe("skipReason / fast path", () => {
  const base = { argv: [], env: {}, stdinTTY: true, stdoutTTY: true, state: null };
  test("fresh interactive start runs", () => expect(mg.skipReason(base)).toBe(null));
  test("--help and --version skip", () => {
    expect(mg.skipReason({ ...base, argv: ["--help"] })).toBe("info-flag");
    expect(mg.skipReason({ ...base, argv: ["x", "--version"] })).toBe("info-flag");
  });
  test("non-TTY skips", () => {
    expect(mg.skipReason({ ...base, stdinTTY: false })).toBe("no-tty");
    expect(mg.skipReason({ ...base, stdoutTTY: false })).toBe("no-tty");
  });
  test("done and declined skip, other states do not", () => {
    expect(mg.skipReason({ ...base, state: { status: "done" } })).toBe("done");
    expect(mg.skipReason({ ...base, state: { status: "declined" } })).toBe("done");
    expect(mg.skipReason({ ...base, state: { status: "weird" } })).toBe(null);
  });
  test("FORCE overrides state and TTY, OFF overrides FORCE", () => {
    expect(mg.skipReason({ ...base, env: { MG_FIRSTRUN_FORCE: "1" }, stdinTTY: false, state: { status: "done" } })).toBe(null);
    expect(mg.skipReason({ ...base, env: { MG_FIRSTRUN_FORCE: "1", MG_FIRSTRUN_OFF: "1" } })).toBe("off");
  });
  test("state round trip and corrupt file", () => {
    const d = tmp();
    const f = path.join(d, "sub", "firstrun.json");
    expect(mg.readState(f)).toBe(null);
    mg.writeState(f, { status: "done" });
    expect(mg.readState(f).status).toBe("done");
    fs.writeFileSync(f, "{not json");
    expect(mg.readState(f)).toBe(null);
  });
  test("launching the script with a final state exits 0 fast without output", () => {
    const d = tmp();
    mg.writeState(path.join(d, "firstrun.json"), { status: "done" });
    const t0 = performance.now();
    const r = spawnSync(process.execPath, [path.join(import.meta.dir, "mg-firstrun.js")], { env: { ...process.env, MG_CONFIG_DIR: d, MG_DATA_DIR: d }, encoding: "utf8" });
    const ms = performance.now() - t0;
    console.log(`fast path wall time: ${ms.toFixed(0)} ms`);
    expect(r.status).toBe(0);
    expect(r.stdout).toBe("");
    expect(ms).toBeLessThan(500);
  });
});

describe("detectChatGPT", () => {
  const never = () => false;
  const none = () => null;
  test("macOS: /Applications and ~/Applications", () => {
    expect(mg.detectChatGPT({ platform: "darwin", home: "/Users/u", exists: (p) => p === "/Applications/ChatGPT.app", run: none }).found).toBe(true);
    expect(mg.detectChatGPT({ platform: "darwin", home: "/Users/u", exists: (p) => p === "/Users/u/Applications/ChatGPT.app", run: none }).found).toBe(true);
    expect(mg.detectChatGPT({ platform: "darwin", home: "/Users/u", exists: never, run: none }).found).toBe(false);
  });
  test("Windows: Programs\\ChatGPT dir, then Appx package", () => {
    const env = { LOCALAPPDATA: "C:\\U\\AppData\\Local" };
    expect(mg.detectChatGPT({ platform: "win32", env, exists: (p) => p === "C:\\U\\AppData\\Local\\Programs\\ChatGPT", run: none }).found).toBe(true);
    const calls = [];
    const run = (c, a) => (calls.push(c), { status: 0, stdout: "OpenAI.ChatGPT-Desktop\r\n" });
    expect(mg.detectChatGPT({ platform: "win32", env, exists: never, run })).toEqual({ found: true, how: "appx:OpenAI.ChatGPT-Desktop" });
    expect(calls).toEqual(["powershell.exe"]);
    expect(mg.detectChatGPT({ platform: "win32", env, exists: never, run: () => ({ status: 0, stdout: "" }) }).found).toBe(false);
  });
  test("Linux: window title via wmctrl, then xdotool", () => {
    const env = { DISPLAY: ":0" };
    const wm = (c) => (c === "wmctrl" ? { status: 0, stdout: "0x01 0 host ChatGPT - Brave\n0x02 0 host Terminal\n" } : null);
    expect(mg.detectChatGPT({ platform: "linux", env, run: wm })).toEqual({ found: true, how: "window:wmctrl" });
    const xd = (c) => (c === "xdotool" ? { status: 0, stdout: "12345\n" } : null);
    expect(mg.detectChatGPT({ platform: "linux", env, run: xd }).how).toBe("window:xdotool");
  });
  test("Linux: no match, no tools, or no display means not found (then the caller asks)", () => {
    expect(mg.detectChatGPT({ platform: "linux", env: { DISPLAY: ":0" }, run: (c) => ({ status: 0, stdout: c === "wmctrl" ? "0x01 0 h Terminal\n" : "" }) }).found).toBe(false);
    expect(mg.detectChatGPT({ platform: "linux", env: { DISPLAY: ":0" }, run: none }).found).toBe(false);
    expect(mg.detectChatGPT({ platform: "linux", env: {}, run: () => ({ status: 0, stdout: "ChatGPT" }) }).found).toBe(false);
  });
  test("detection never touches browser data: only the injected exists/run are used", () => {
    const seen = [];
    mg.detectChatGPT({ platform: "darwin", home: "/Users/u", exists: (p) => (seen.push(p), false), run: none });
    mg.detectChatGPT({ platform: "win32", env: { LOCALAPPDATA: "C:\\L" }, exists: (p) => (seen.push(p), false), run: (c, a) => (seen.push(c + " " + a.join(" ")), null) });
    for (const s of seen) expect(s.replace("-NoProfile", "")).not.toMatch(/cookie|history|profile|Login Data|User Data/i);
  });
});

describe("greeting", () => {
  test("fallback text contains the risk sentence and passes validation", () => {
    expect(mg.FALLBACK_GREETING).toContain(mg.RISK_SENTENCE);
    expect(mg.greetingIsValid(mg.FALLBACK_GREETING)).toBe(true);
  });
  test("model output without the risk sentence is rejected", () => {
    expect(mg.greetingIsValid("Hello! I can set up a ChatGPT bridge for you, it is great and fast and easy. Want it now?")).toBe(false);
    expect(mg.greetingIsValid("")).toBe(false);
  });
  test("cleanModelText strips think blocks and whitespace", () => {
    expect(mg.cleanModelText("<think>x\ny</think>\n Hi   there \n")).toBe("Hi there");
  });
  test("system prompt carries the exact risk sentence", () => expect(mg.SYSTEM_PROMPT).toContain(mg.RISK_SENTENCE));
});

describe("makeGreeting", () => {
  const reply = (content) => async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }) });
  const seq = (...contents) => {
    const bodies = [];
    const f = async (url, init) => {
      bodies.push(JSON.parse(init.body));
      return reply(contents[Math.min(bodies.length - 1, contents.length - 1)])();
    };
    f.bodies = bodies;
    return f;
  };
  test("opening validation", () => {
    expect(mg.openingIsValid("Welcome to Machine God, your terminal companion.")).toBe(true);
    expect(mg.openingIsValid("Welcome to Machine God, where you will find the.")).toBe(false);
    expect(mg.openingIsValid("Go away.")).toBe(false);
    expect(mg.openingIsValid("Welcome to the terminal, friend, enjoy yourself here.")).toBe(false);
  });
  test("composeGreeting always carries the risk sentence and passes greetingIsValid", () => {
    const g = mg.composeGreeting("Welcome to Machine God, glad you are here.");
    expect(g).toContain(mg.RISK_SENTENCE);
    expect(mg.greetingIsValid(g)).toBe(true);
    expect(g.endsWith("?")).toBe(true);
  });
  test("a complete model greeting is used as is", async () => {
    const text = "Hello! I can set up a ChatGPT bridge for you. " + mg.RISK_SENTENCE + " Shall I do it now?";
    const r = await mg.makeGreeting({ port: 1, fetchFn: seq(text) });
    expect(r.mode).toBe("model");
    expect(r.text).toBe(text);
  });
  test("incomplete greeting -> constrained opening + fixed remainder", async () => {
    const f = seq("I'm sorry, but I can't do that.", "Welcome to Machine God, glad you are here.");
    const r = await mg.makeGreeting({ port: 1, fetchFn: f });
    expect(r.mode).toBe("model-opening");
    expect(r.text).toContain(mg.RISK_SENTENCE);
    expect(f.bodies[1].grammar).toBe(mg.OPENING_GRAMMAR);
    expect(f.bodies[0].grammar).toBeUndefined();
  });
  test("nothing usable -> fixed fallback after 4 requests", async () => {
    const f = seq("No.");
    const r = await mg.makeGreeting({ port: 1, fetchFn: f });
    expect(r).toEqual({ text: mg.FALLBACK_GREETING, mode: "fallback", tries: 4 });
    expect(f.bodies.length).toBe(4);
  });
  test("grammar string ends with a newline and escapes \\n for GBNF", () => {
    expect(mg.OPENING_GRAMMAR).toContain("[^.?!\\n]");
  });
});

describe("pinned downloads", () => {
  test("every llama.cpp asset has a 64-hex sha256 and the pinned tag", () => {
    for (const [k, a] of Object.entries(mg.LLAMA_ASSETS)) {
      expect(a.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(a.name).toContain(mg.LLAMA_TAG);
      expect(k).toMatch(/^(linux|darwin|win32)-(x64|arm64)$/);
    }
    expect(mg.MODEL.sha256).toMatch(/^[0-9a-f]{64}$/);
  });
  const mkFetch = (buf, { ignoreRange = false } = {}) => async (url, init) => {
    const range = init?.headers?.Range;
    let start = 0;
    let status = 200;
    if (range && !ignoreRange) {
      start = Number(/bytes=(\d+)-/.exec(range)[1]);
      status = 206;
    }
    const body = buf.subarray(start);
    return { ok: true, status, headers: new Headers({ "content-length": String(body.length) }), body: (async function* () { yield body.subarray(0, 5); yield body.subarray(5); })() };
  };
  const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
  test("downloads and verifies", async () => {
    const d = tmp();
    const buf = Buffer.from("hello model bytes");
    const dest = path.join(d, "m.gguf");
    await mg.downloadVerified({ url: "x", dest, sha256: sha(buf), fetchFn: mkFetch(buf) });
    expect(fs.readFileSync(dest).equals(buf)).toBe(true);
    expect(fs.existsSync(dest + ".part")).toBe(false);
  });
  test("checksum mismatch throws and leaves no file", async () => {
    const d = tmp();
    const dest = path.join(d, "m.gguf");
    await expect(mg.downloadVerified({ url: "x", dest, sha256: "0".repeat(64), fetchFn: mkFetch(Buffer.from("abc def ghi")) })).rejects.toThrow(/checksum mismatch/);
    expect(fs.existsSync(dest)).toBe(false);
    expect(fs.existsSync(dest + ".part")).toBe(false);
  });
  test("resumes from a .part file", async () => {
    const d = tmp();
    const buf = Buffer.from("0123456789abcdefghij");
    const dest = path.join(d, "m.gguf");
    fs.writeFileSync(dest + ".part", buf.subarray(0, 8));
    await mg.downloadVerified({ url: "x", dest, sha256: sha(buf), fetchFn: mkFetch(buf) });
    expect(fs.readFileSync(dest).equals(buf)).toBe(true);
  });
  test("restarts when the server ignores Range", async () => {
    const d = tmp();
    const buf = Buffer.from("0123456789abcdefghij");
    const dest = path.join(d, "m.gguf");
    fs.writeFileSync(dest + ".part", buf.subarray(0, 8));
    await mg.downloadVerified({ url: "x", dest, sha256: sha(buf), fetchFn: mkFetch(buf, { ignoreRange: true }) });
    expect(fs.readFileSync(dest).equals(buf)).toBe(true);
  });
});

describe("asker and flow", () => {
  test("scripted answers are consumed in order, then no", async () => {
    const out = { write() {} };
    const ask = mg.makeAsker({ env: { MG_FIRSTRUN_ANSWERS: "yes, no ,y" }, output: out });
    expect([await ask("a"), await ask("b"), await ask("c"), await ask("d")]).toEqual([true, false, true, false]);
  });
  test("not using ChatGPT writes state 'declined' and downloads nothing", async () => {
    const d = tmp();
    const lines = [];
    const env = { MG_CONFIG_DIR: d, MG_DATA_DIR: d, MG_FIRSTRUN_ANSWERS: "no" };
    const ask = mg.makeAsker({ env, output: { write: (s) => lines.push(s) } });
    const rec = await mg.runFirstRun({ env, ask, out: { write: (s) => lines.push(s) }, installDir: d, detect: () => ({ found: false, how: null }) });
    expect(rec.status).toBe("declined");
    expect(mg.readState(path.join(d, "firstrun.json")).chatgpt).toBe("user-says-no");
    expect(fs.existsSync(path.join(d, "models"))).toBe(false);
    expect(lines.join("")).toContain("Do you use ChatGPT?");
  });
  test("ChatGPT found, model declined, bridge declined: standard text with risk sentence, state declined", async () => {
    const d = tmp();
    const lines = [];
    const env = { MG_CONFIG_DIR: d, MG_DATA_DIR: d, MG_FIRSTRUN_ANSWERS: "no,no" };
    const w = { write: (s) => lines.push(s) };
    const rec = await mg.runFirstRun({ env, ask: mg.makeAsker({ env, output: w }), out: w, installDir: d, detect: () => ({ found: true, how: "test" }) });
    expect(rec).toMatchObject({ status: "declined", chatgpt: "detected", model: "declined", bridge: "declined" });
    expect(lines.join("")).toContain(mg.RISK_SENTENCE);
    expect(lines.join("")).not.toContain("Do you use ChatGPT?");
  });
  test("bridge is never set up without an explicit yes", async () => {
    const d = tmp();
    const env = { MG_CONFIG_DIR: d, MG_DATA_DIR: d, MG_FIRSTRUN_ANSWERS: "no" };
    const w = { write() {} };
    const rec = await mg.runFirstRun({ env, ask: mg.makeAsker({ env, output: w }), out: w, installDir: d, detect: () => ({ found: true }) });
    expect(rec.bridge).toBe("declined");
    expect(fs.existsSync(path.join(d, "bridge-venv"))).toBe(false);
    expect(fs.existsSync(path.join(d, "bridge.token"))).toBe(false);
  });
});

describe("mcp command", () => {
  test("exact claude mcp add command", () => {
    expect(mg.mcpAddCommand("/v/bin/python", "/i/bridge/mcp_chatgpt.py")).toEqual(["claude", "mcp", "add", "--scope", "user", "machine-god-chatgpt", "--", "/v/bin/python", "/i/bridge/mcp_chatgpt.py"]);
  });
});
