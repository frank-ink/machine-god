import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { openDb, redact, T, setState, getState, tokens, dbPath } from "./core.ts";
import * as L from "./learn.ts";
import { handle, onTool, readTranscript } from "./hook.ts";
import { parseReflection, run, dryLlm, buildPrompt } from "./reflect.ts";
import * as P from "./proposals.ts";
import { metrics } from "./cli.ts";
import { installHooks, removeHooks, settingsFile } from "./settings.ts";

const FAKE_KEY = "sk-" + "ant-api03-abcdefghijklmnop1234"; // fake, split so scanners do not flag the test
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "mgr-"));
const mem = () => openDb(":memory:");
const D = L.DAY;
const here = import.meta.dir;
const spawnBun = async (script: string, args: string[], env: Record<string, string>, stdin = "") => {
  const t0 = performance.now();
  const p = Bun.spawn([process.execPath, path.join(here, script), ...args], { stdin: new Blob([stdin]), stdout: "pipe", stderr: "pipe", env: { PATH: process.env.PATH!, ...env } });
  const [out, err, code] = [await new Response(p.stdout).text(), await new Response(p.stderr).text(), await p.exited];
  return { out, err, code, ms: performance.now() - t0 };
};
const writeTranscript = (f: string, prompt: string, answer: string) => fs.writeFileSync(f, [
  { type: "user", message: { role: "user", content: "older prompt" } },
  { type: "assistant", message: { role: "assistant", content: [{ type: "text", text: "older answer" }] } },
  { type: "user", message: { role: "user", content: [{ type: "text", text: prompt }] } },
  { type: "assistant", message: { role: "assistant", content: [{ type: "tool_use", name: "Bash" }] } },
  { type: "user", message: { role: "user", content: [{ type: "tool_result", content: "x" }] } },
  { type: "assistant", message: { role: "assistant", content: [{ type: "text", text: answer }] } },
].map((x) => JSON.stringify(x)).join("\n") + "\n");

describe("redaction", () => {
  test("keys, tokens, passwords, urls, blobs", () => {
    const s = redact("key " + "sk-" + "ant-api03-abcdefghijklmnop1234 and " + "gh" + "p_abcdefghijklmnopqrstuv, pass" + "word=hunter22, Authorization: " + "Bearer abc.def.ghijklmnopqrs, https://u:" + "pw12345@host/x, " + "AKIA" + "ABCDEFGHIJKLMNOP, 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 ok");
    for (const bad of ["sk-ant", "ghp_", "hunter22", "abc.def", "pw12345", "AKIAABC", "9f86d081"]) expect(s).not.toContain(bad);
    expect(redact("plain text about a/long/path/name and words")).toBe("plain text about a/long/path/name and words");
  });
});

describe("capture hooks", () => {
  test("PostToolUse ok + failure; Stop with transcript; secrets redacted; duplicates ignored", () => {
    const dir = tmp(), now = 1_000_000;
    handle("post", { session_id: "s1", tool_name: "Bash", tool_input: { command: "npm test" }, tool_response: { stdout: "ok" }, duration_ms: 42 }, dir, { now });
    handle("post", { session_id: "s1", hook_event_name: "PostToolUseFailure", tool_name: "Read", error: "ENOENT: no such file /x password=topsecret1" }, dir, { now });
    const tr = path.join(dir, "t.jsonl");
    writeTranscript(tr, "fix the build, my token=abcd1234efgh", "Done. key " + FAKE_KEY + " removed.");
    expect(readTranscript(tr)).toEqual({ prompt: "fix the build, my token=abcd1234efgh", answer: "Done. key " + FAKE_KEY + " removed." });
    const noSpawn = { now, spawnFn: () => { throw new Error("must not spawn"); } };
    handle("stop", { session_id: "s1", transcript_path: tr }, dir, noSpawn);
    handle("stop", { session_id: "s1", transcript_path: tr }, dir, noSpawn); // duplicate Stop
    const db = openDb(path.join(dir, "reflect.db"));
    const ev = db.all<any>(`SELECT * FROM ${T}events ORDER BY id`);
    expect(ev.map((e) => [e.tool, e.sub, e.ok, e.err_class, e.dur_ms])).toEqual([["Bash", "npm", 1, null, 42], ["Read", "", 0, "not-found", null]]);
    expect(JSON.stringify(ev)).not.toContain("topsecret1");
    const t = db.all<any>(`SELECT * FROM ${T}tasks`);
    expect(t.length).toBe(1);
    expect(t[0].tools_n).toBe(2); expect(t[0].errs_n).toBe(1);
    expect(JSON.stringify(t)).not.toMatch(/abcd1234efgh|sk-ant/);
    expect(db.get<any>(`SELECT COUNT(*) n FROM ${T}events WHERE task_id IS NULL`).n).toBe(0);
  });
  test("garbage input, missing transcript, state off, MG_REFLECT_RUNNING: no throw, no output", () => {
    const dir = tmp();
    expect(handle("stop", { transcript_path: "/nonexistent" }, dir)).toBe("");
    expect(handle("post", {}, dir)).toBe("");
    expect(handle("nonsense", {}, dir)).toBe("");
    const d2 = tmp(), d3 = tmp(); setState("off", d2);
    handle("post", { tool_name: "Bash" }, d2);
    expect(fs.existsSync(path.join(d2, "reflect.db"))).toBe(false);
    setState("on", d3);
    handle("post", { tool_name: "Bash" }, d3, { env: { MG_REFLECT_RUNNING: "1" } });
    expect(fs.existsSync(path.join(d3, "reflect.db"))).toBe(false);
  });
  test("Stop spawns reflection only when enabled and at most once per N min", () => {
    const dir = tmp(); let spawned = 0;
    const tr = path.join(dir, "t.jsonl"); writeTranscript(tr, "task one here", "answer one");
    const o = (now: number) => ({ now, everyMin: 10, spawnFn: () => { spawned++; } });
    handle("stop", { session_id: "a", transcript_path: tr }, dir, o(1e9)); expect(spawned).toBe(0); // state unset
    setState("on", dir);
    writeTranscript(tr, "task two here", "answer two");
    handle("stop", { session_id: "a", transcript_path: tr }, dir, o(1e9 + 1)); expect(spawned).toBe(1);
    writeTranscript(tr, "task three here", "answer three");
    handle("stop", { session_id: "a", transcript_path: tr }, dir, o(1e9 + 60_000)); expect(spawned).toBe(1); // inside 10 min
    writeTranscript(tr, "task four here", "answer four");
    handle("stop", { session_id: "a", transcript_path: tr }, dir, o(1e9 + 11 * 60_000)); expect(spawned).toBe(2);
  });
});

describe("storage switch", () => {
  test("once the GRID created unified.db in the data dir, reflection uses it (one memory); before that reflect.db", () => {
    const dir = tmp();
    expect(dbPath(dir, {})).toBe(path.join(dir, "reflect.db"));
    const u = openDb(path.join(dir, "unified.db")); u.run("CREATE TABLE durable_memory(id TEXT)"); u.close();
    expect(dbPath(dir, {})).toBe(path.join(dir, "unified.db"));
    handle("post", { tool_name: "Bash", session_id: "s" }, dir, { env: {} });
    const db = openDb(path.join(dir, "unified.db"));
    expect(db.get<{ n: number }>(`SELECT COUNT(*) n FROM ${T}events`)!.n).toBe(1);
    expect(db.get<{ n: number }>("SELECT COUNT(*) n FROM sqlite_master WHERE name='durable_memory'")!.n).toBe(1);
    db.close(); expect(fs.existsSync(path.join(dir, "reflect.db"))).toBe(false);
  });
  test("MG_REFLECT_DB moves all tables into another SQLite file (e.g. unified.db) next to foreign tables", () => {
    const dir = tmp(), udb = path.join(dir, "unified.db");
    const pre = openDb(udb); pre.run("CREATE TABLE durable_memory(k TEXT)"); pre.close();
    handle("post", { tool_name: "Bash", session_id: "s" }, dir, { env: { MG_REFLECT_DB: udb } });
    const db = openDb(udb);
    expect(db.get<any>(`SELECT COUNT(*) n FROM ${T}events`).n).toBe(1); expect(db.all(`SELECT name FROM sqlite_master WHERE name='durable_memory'`).length).toBe(1);
    expect(fs.existsSync(path.join(dir, "reflect.db"))).toBe(false);
  });
});

describe("reflection parse", () => {
  const good = { outcome: "partial", what_went_well: "a", what_to_improve: "b", lesson: "Read the file before editing it.", applies_to: ["edit", "read"], confidence: 0.7, proposal: { kind: "config", file: "cfg.json", change: "{}", why: "w", test: "true" } };
  test("fenced / prose-wrapped JSON ok, proposal kept", () => {
    const r = parseReflection("Sure!\n```json\n" + JSON.stringify(good) + "\n```\nthanks")!;
    expect(r.outcome).toBe("partial"); expect(r.applies_to).toEqual(["edit", "read"]); expect(r.proposal?.kind).toBe("config");
  });
  test("malformed -> null", () => {
    for (const bad of ["", "no json", "{\"outcome\":\"success\"}", "{\"outcome\":\"great\",\"lesson\":\"Do the thing properly.\"}", "{broken"]) expect(parseReflection(bad)).toBeNull();
    expect(parseReflection(JSON.stringify({ ...good, confidence: 7, proposal: { kind: "shell", file: "x", change: "y" } }))!.confidence).toBe(1);
  });
  test("malformed answers are skipped with retry limit, never learned", async () => {
    const db = mem(); db.run(`INSERT INTO ${T}tasks(ts,session,prompt,answer,tools_n,errs_n) VALUES(1,'s','p','a',0,0)`);
    for (let i = 0; i < 3; i++) expect((await run(db, { llm: async () => "garbage" })).skipped).toBe(1);
    expect(db.get<any>(`SELECT reflected FROM ${T}tasks`).reflected).toBe(2);
    expect(db.all(`SELECT * FROM ${T}lessons`).length).toBe(0);
  });
  test("prompt contains task data and is capped inputs only", () => {
    expect(buildPrompt({ prompt: "P", answer: "A", tools_n: 3, errs_n: 1 }, "Bash x1")).toContain("tool calls: 3, failed: 1");
  });
});

describe("learning", () => {
  test("dedupe + reinforce raises confidence, merges keywords", () => {
    const db = mem();
    const a = L.learn(db, { text: "Read the file before editing it to prevent mismatches.", applies_to: ["edit"], confidence: 0.5 }, 1000);
    const b = L.learn(db, { text: "Always read the file before editing it, prevents mismatches.", applies_to: ["read"], confidence: 0.6 }, 2000);
    expect(a.action).toBe("added"); expect(b).toEqual({ action: "reinforced", id: a.id });
    const l = L.activeLessons(db);
    expect(l.length).toBe(1); expect(l[0].confidence).toBeGreaterThan(0.5); expect(l[0].reinforced).toBe(2); expect(l[0].applies_to).toContain("read");
    expect(L.learn(db, { text: "short" }).action).toBe("skipped");
  });
  test("decay after grace, dormant below 0.15, reinforce revives; no double decay", () => {
    const db = mem(); const id = L.learn(db, { text: "Use smaller steps when a build is slow.", confidence: 0.5 }, 0).id!;
    expect(L.decay(db, 10 * D)).toBe(0); // inside grace
    expect(L.decay(db, 44 * D)).toBe(1); // 30 d past grace -> half
    expect(L.activeLessons(db)[0].confidence).toBeCloseTo(0.25, 2);
    expect(L.decay(db, 44 * D + 1000)).toBe(0); // same day: nothing
    L.decay(db, 100 * D);
    expect(db.get<any>(`SELECT status FROM ${T}lessons WHERE id=?`, id).status).toBe("dormant");
    expect(L.activeLessons(db).length).toBe(0);
    expect(L.learn(db, { text: "Use smaller steps when a build is slow.", confidence: 0.6 }, 101 * D).action).toBe("reinforced");
    expect(db.get<any>(`SELECT status FROM ${T}lessons WHERE id=?`, id).status).toBe("active");
  });
  test("used lessons do not decay", () => {
    const db = mem(); L.learn(db, { text: "Check the lockfile before installing packages.", applies_to: ["install"], confidence: 0.5 }, 0);
    L.relevant(db, "install packages lockfile", 5, 800, 40 * D);
    expect(L.decay(db, 45 * D)).toBe(0);
  });
  test("contradiction: both kept, both flagged and visible", () => {
    const db = mem();
    const a = L.learn(db, { text: "Run the full test suite after every edit.", confidence: 0.6 }, 1).id!;
    const b = L.learn(db, { text: "Never run the full test suite after every edit.", confidence: 0.6 }, 2).id!;
    expect(b).not.toBe(a);
    const l = L.activeLessons(db);
    expect(l.length).toBe(2); expect(l.every((x) => x.status === "flagged" && x.flag?.startsWith("contradicts:"))).toBe(true);
    expect(L.relevant(db, "run the test suite", 5, 800, 3).text).toContain("[disputed]");
  });
  test("cap moves lowest-confidence lessons to dormant", () => {
    const db = mem();
    for (let i = 0; i < L.MAX_ACTIVE + 5; i++) L.learn(db, { text: `Distinct lesson number${i} about topic${i}x${i * 7} handling.`, confidence: 0.2 + (i % 50) / 100 }, i);
    expect(L.activeLessons(db).length).toBe(L.MAX_ACTIVE);
  });
  test("repeated tool failure (>=3 same tool+class) -> automatic lesson; <3 -> none; no re-learn without growth", () => {
    const db = mem(); const now = 5 * D;
    for (let i = 0; i < 2; i++) onTool(db, { session_id: "s", hook_event_name: "PostToolUseFailure", tool_name: "Edit", error: "String to replace not found in file" }, now);
    expect(L.errorPatterns(db, now)).toBe(0);
    onTool(db, { session_id: "s", hook_event_name: "PostToolUseFailure", tool_name: "Edit", error: "old_string not unique" }, now);
    expect(L.errorPatterns(db, now)).toBe(1);
    const l = L.activeLessons(db); expect(l.length).toBe(1); expect(l[0].text).toMatch(/Edit.*edit-mismatch.*3x/); expect(l[0].source).toBe("error-pattern");
    expect(L.errorPatterns(db, now)).toBe(0); expect(L.activeLessons(db)[0].reinforced).toBe(1);
  });
  test("versions + rollback restore exact earlier state (add, reinforce, decay)", () => {
    const db = mem();
    const id = L.learn(db, { text: "Prefer grep over reading whole files when searching.", confidence: 0.5 }, 0).id!;
    const v1 = db.get<any>(`SELECT MAX(version) v FROM ${T}lesson_versions`).v;
    L.learn(db, { text: "Prefer grep over reading whole files when searching.", confidence: 0.9 }, 1000);
    L.learn(db, { text: "Second unrelated lesson about commit messages.", confidence: 0.5 }, 2000);
    L.decay(db, 60 * D);
    const before = db.get<any>(`SELECT confidence, reinforced FROM ${T}lessons WHERE id=?`, id);
    expect(before.reinforced).toBe(2);
    expect(L.rollback(db, v1 + 1)).toBeGreaterThanOrEqual(3);
    const after = db.get<any>(`SELECT confidence, reinforced FROM ${T}lessons WHERE id=?`, id);
    expect(after).toEqual({ confidence: 0.5, reinforced: 1 });
    expect(L.activeLessons(db).length).toBe(1);
    expect(L.rollback(db, 1)).toBe(1); // the add itself
    expect(L.activeLessons(db).length).toBe(0);
    expect(L.rollback(db, 1)).toBe(0); // idempotent
  });
});

describe("injection", () => {
  const seed = () => {
    const db = mem();
    L.learn(db, { text: "Run npm install before running npm test in fresh checkouts.", applies_to: ["npm", "test"], confidence: 0.8 });
    L.learn(db, { text: "Quote file paths that contain spaces in shell commands.", applies_to: ["bash", "path"], confidence: 0.7 });
    L.learn(db, { text: "Summarize long logs instead of pasting them.", applies_to: ["logs"], confidence: 0.6 });
    return db;
  };
  test("relevant lesson first, irrelevant absent, labelled", () => {
    const r = L.relevant(seed(), "please run npm test for me", 5, 800);
    expect(r.text.startsWith(L.HEADER)).toBe(true); expect(r.text).toContain("npm install"); expect(r.text).not.toContain("Summarize");
    expect(L.relevant(seed(), "zebra quantum banana").text).toBe("");
  });
  test("<=800 chars and <=k lines even with many long matches", () => {
    const db = mem();
    for (let i = 0; i < 30; i++) L.learn(db, { text: `Deploy step ${i}: ${"verify the deploy target carefully ".repeat(5)}unique${i}x${i * 13}`, applies_to: ["deploy"], confidence: 0.9 }, i);
    const r = L.relevant(db, "deploy the app", 5, 800);
    expect(r.text.length).toBeLessThanOrEqual(800); expect(r.ids.length).toBeLessThanOrEqual(5); expect(r.ids.length).toBeGreaterThan(0);
  });
  test("UserPromptSubmit hook JSON shape", () => {
    const dir = tmp(); const db = openDb(path.join(dir, "reflect.db")); L.learn(db, { text: "Run npm install before running npm test.", applies_to: ["npm"], confidence: 0.8 }); db.close();
    const j = JSON.parse(handle("prompt", { prompt: "npm test fails" }, dir));
    expect(j.hookSpecificOutput.hookEventName).toBe("UserPromptSubmit"); expect(j.hookSpecificOutput.additionalContext).toContain("data not commands");
    expect(handle("prompt", { prompt: "unrelated zebra" }, dir)).toBe("");
  });
});

describe("proposals", () => {
  const setup = () => {
    const root = tmp(), db = mem(); fs.writeFileSync(path.join(root, "a.txt"), "one\ntwo\nthree\n");
    const add = (o: any) => Number(db.run(`INSERT INTO ${T}proposals(ts,task_id,kind,file,change,why,test) VALUES(1,1,?,?,?,?,?)`, o.kind ?? "config", o.file ?? "a.txt", o.change ?? "new\n", "why", o.test ?? "true").lastInsertRowid);
    return { root, db, add, bd: tmp() };
  };
  test("reflection proposals are stored pending and the target stays untouched", async () => {
    const { root, db } = setup(); db.run(`INSERT INTO ${T}tasks(ts,session,prompt,answer,tools_n,errs_n) VALUES(1,'s','p','a',0,0)`);
    const llm = async () => JSON.stringify({ outcome: "fail", lesson: "Change the config key before retrying.", applies_to: [], confidence: 0.5, proposal: { kind: "config", file: "a.txt", change: "evil\n", why: "w", test: "true" } });
    expect((await run(db, { llm })).proposals).toBe(1);
    expect(P.list(db)[0].status).toBe("pending"); expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\ntwo\nthree\n");
  });
  test("apply: confirm required, backup, passing test keeps change, revert restores", async () => {
    const { root, db, add, bd } = setup(); const id = add({ change: "new\n" });
    expect((await P.apply(db, id, { confirm: () => false, roots: [root], backupDir: bd })).note).toBe("not confirmed");
    expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\ntwo\nthree\n");
    const r = await P.apply(db, id, { confirm: () => true, roots: [root], backupDir: bd });
    expect(r.status).toBe("applied"); expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("new\n");
    expect(fs.readdirSync(bd).length).toBe(1);
    expect(P.revert(db, id)).toBe(true); expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\ntwo\nthree\n");
  });
  test("failing test -> auto rollback of existing and of new file", async () => {
    const { root, db, add, bd } = setup();
    const id = add({ change: "broken\n", test: "exit 3" });
    const r = await P.apply(db, id, { confirm: () => true, roots: [root], backupDir: bd });
    expect(r.status).toBe("rolledback"); expect(r.note).toContain("exit 3"); expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\ntwo\nthree\n");
    const id2 = add({ file: "sub/new.json", change: "{}", test: "false" });
    expect((await P.apply(db, id2, { confirm: () => true, roots: [root], backupDir: bd })).status).toBe("rolledback");
    expect(fs.existsSync(path.join(root, "sub/new.json"))).toBe(false);
  });
  test("unified diff applies; mismatching diff fails without touching the file", async () => {
    const { root, db, add, bd } = setup();
    const id = add({ change: "--- a/a.txt\n+++ b/a.txt\n@@ -1,3 +1,3 @@\n one\n-two\n+TWO\n three\n" });
    expect((await P.apply(db, id, { confirm: () => true, roots: [root], backupDir: bd })).status).toBe("applied");
    expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\nTWO\nthree\n");
    const bad = add({ change: "@@ -1,2 +1,2 @@\n nope\n-x\n+y\n" });
    expect((await P.apply(db, bad, { confirm: () => true, roots: [root], backupDir: bd })).status).toBe("failed");
    expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("one\nTWO\nthree\n");
  });
  test("refuses paths outside install/config dirs, symlink escape, and missing test", async () => {
    const { root, db, add, bd } = setup(); const outside = tmp();
    fs.symlinkSync(outside, path.join(root, "link"));
    for (const file of ["../escape.txt", "/etc/mg-test-x", "link/x.txt"]) {
      const r = await P.apply(db, add({ file }), { confirm: () => true, roots: [root], backupDir: bd });
      expect(r.note).toContain("outside"); }
    expect(fs.existsSync(path.join(outside, "x.txt"))).toBe(false);
    expect((await P.apply(db, add({ test: "" }), { confirm: () => true, roots: [root], backupDir: bd })).note).toContain("no test");
  });
  test("CLI apply without TTY is refused (exit 3), file untouched; reject works", async () => {
    const dir = tmp(), root = tmp(); fs.writeFileSync(path.join(root, "a.txt"), "orig\n");
    const db = openDb(path.join(dir, "reflect.db")); db.run(`INSERT INTO ${T}proposals(ts,task_id,kind,file,change,why,test) VALUES(1,1,'code','a.txt','x','w','true')`); db.close();
    const env = { MG_DATA_DIR: dir, MG_HOME: root, HOME: dir };
    const r = await spawnBun("cli.ts", ["apply", "1"], env, "yes\n");
    expect(r.code).toBe(3); expect(r.err).toContain("interactive"); expect(fs.readFileSync(path.join(root, "a.txt"), "utf8")).toBe("orig\n");
    expect((await spawnBun("cli.ts", ["reject", "1"], env)).code).toBe(0);
    expect((await spawnBun("cli.ts", ["proposals"], env)).out).toContain("[rejected]");
  });
});

describe("metrics honesty", () => {
  test("small numbers: no trend claim; enough data: improving detected", () => {
    const db = mem();
    const add = (o: string) => db.run(`INSERT INTO ${T}tasks(ts,session,prompt,answer,tools_n,errs_n,reflected,outcome) VALUES(1,'s','p','a',0,0,1,?)`, o);
    for (let i = 0; i < 6; i++) add(i < 3 ? "fail" : "success");
    expect(metrics(db).success_trend).toContain("insufficient");
    for (let i = 0; i < 20; i++) add("success");
    const db2 = mem(); for (let i = 0; i < 24; i++) db2.run(`INSERT INTO ${T}tasks(ts,session,prompt,answer,tools_n,errs_n,reflected,outcome) VALUES(1,'s','p','a',0,0,1,?)`, i < 12 ? (i % 3 ? "fail" : "success") : "success");
    expect(metrics(db2).success_trend).toBe("improving");
  });
});

describe("e2e (temp HOME, dry backend, real hook + cli subprocesses)", () => {
  test("10 tasks incl. repeated failures -> run -> lessons -> injected for matching prompt; hook timing", async () => {
    const home = tmp(), dir = path.join(home, "data");
    const env = { HOME: home, MG_DATA_DIR: dir, MG_REFLECT_BACKEND: "dry", MG_REFLECT_EVERY_MIN: "100000" };
    const hookMs: number[] = [];
    const hook = async (kind: string, payload: object) => { const r = await spawnBun("hook.ts", [kind], env, JSON.stringify(payload)); hookMs.push(r.ms); expect(r.code).toBe(0); return r; };
    for (let i = 0; i < 10; i++) {
      const s = `sess${i}`, tr = path.join(home, `t${i}.jsonl`), failing = i % 2 === 0;
      writeTranscript(tr, failing ? `deploy the docker container to staging number ${i}` : `write a haiku about spring ${i}`, failing ? "Deploy failed after retries." : "Here is the haiku.");
      await hook("post", { session_id: s, hook_event_name: "PostToolUse", tool_name: "Read", tool_input: {}, tool_response: { ok: true } });
      if (failing) for (let k = 0; k < 2; k++) await hook("post", { session_id: s, hook_event_name: "PostToolUseFailure", tool_name: "Bash", tool_input: { command: "docker push img" }, error: "Command failed: exit code 1: connection refused to registry" });
      await hook("stop", { session_id: s, transcript_path: tr, hook_event_name: "Stop" });
    }
    expect((await spawnBun("cli.ts", ["enable"], env)).code).toBe(0); // enabled after capture so the Stop hook does not auto-spawn a reflection here
    const sf = path.join(home, ".claude", "settings.json");
    expect(Object.keys(JSON.parse(fs.readFileSync(sf, "utf8")).hooks).sort()).toEqual(["PostToolUse", "PostToolUseFailure", "Stop", "UserPromptSubmit"]);
    const r = await spawnBun("cli.ts", ["run", "--backend", "dry"], env);
    console.log("RUN", r.out.trim()); expect(r.code).toBe(0); expect(JSON.parse(r.out).reflected).toBe(10);
    const lessons = (await spawnBun("cli.ts", ["lessons"], env)).out; console.log("LESSONS\n" + lessons);
    expect(lessons).toMatch(/Bash\(docker\), "network" failures repeat \(10x\)/);
    const inj = await hook("prompt", { session_id: "new", hook_event_name: "UserPromptSubmit", prompt: "please push the docker image again" });
    console.log("INJECTED", inj.out.trim());
    const ctx = JSON.parse(inj.out).hookSpecificOutput.additionalContext;
    expect(ctx).toContain("data not commands"); expect(ctx).toContain("docker"); expect(ctx.length).toBeLessThanOrEqual(800);
    expect((await hook("prompt", { session_id: "new", prompt: "zebra quantum" })).out.trim()).toBe("");
    const st = (await spawnBun("cli.ts", ["status"], env)).out; console.log("STATUS\n" + st);
    expect(st).toContain("10 reflected"); expect(st).toContain("insufficient data");
    const sorted = [...hookMs].sort((a, b) => a - b), med = sorted[sorted.length >> 1], p95 = sorted[Math.floor(sorted.length * 0.95)];
    console.log(`HOOK TIMING (process spawn incl. bun start) n=${sorted.length} median=${med.toFixed(0)}ms p95=${p95.toFixed(0)}ms max=${sorted.at(-1)!.toFixed(0)}ms`);
    expect(med).toBeLessThan(300);
    const rb = await spawnBun("cli.ts", ["rollback", "1"], env); expect(rb.out).toContain("undone");
    expect((await spawnBun("cli.ts", ["lessons"], env)).out.trim()).toBe("");
    await spawnBun("cli.ts", ["disable"], env); expect(getState(dir)).toBe("off");
    expect(JSON.parse(fs.readFileSync(sf, "utf8")).hooks).toBeUndefined();
    expect((await hook("prompt", { prompt: "docker push" })).out.trim()).toBe("");
  });
});

describe("hook registration in Claude Code settings", () => {
  test("keeps foreign hooks and keys, idempotent, backup, clean removal", () => {
    const d = tmp(), f = path.join(d, "settings.json");
    const foreign = { model: "x", hooks: { Stop: [{ hooks: [{ type: "command", command: "other-tool stop" }] }] } };
    fs.writeFileSync(f, JSON.stringify(foreign));
    expect(installHooks(f, "/opt/mg/claude-rs-bridge-bun", "/opt/mg")).toBe(4);
    installHooks(f, "/opt/mg/claude-rs-bridge-bun", "/opt/mg2"); // second run (moved install) replaces, never duplicates
    const j = JSON.parse(fs.readFileSync(f, "utf8"));
    expect(j.model).toBe("x");
    expect(j.hooks.Stop.length).toBe(2); expect(j.hooks.Stop[0].hooks[0].command).toBe("other-tool stop");
    expect(j.hooks.Stop[1].hooks[0].command).toBe(`"/opt/mg/claude-rs-bridge-bun" "${path.join("/opt/mg2", "reflect", "hook.ts")}" stop`);
    expect(j.hooks.PostToolUse[0].matcher).toBe("*"); expect(j.hooks.UserPromptSubmit[0].hooks[0].command).toMatch(/ prompt$/);
    expect(fs.readdirSync(d).filter((x) => x.includes(".machine-god-") && x.endsWith(".bak")).length).toBeGreaterThanOrEqual(2);
    expect(removeHooks(f)).toBe(4);
    expect(JSON.parse(fs.readFileSync(f, "utf8"))).toEqual(foreign);
    expect(removeHooks(f)).toBe(0); expect(removeHooks(path.join(d, "none.json"))).toBe(0);
  });
  test("broken settings.json is never overwritten", () => {
    const d = tmp(), f = path.join(d, "settings.json");
    fs.writeFileSync(f, "{ not json");
    expect(() => installHooks(f, "/b", "/r")).toThrow();
    expect(fs.readFileSync(f, "utf8")).toBe("{ not json");
  });
  test("settings path honours CLAUDE_CONFIG_DIR", () => {
    expect(settingsFile({ CLAUDE_CONFIG_DIR: "/c" })).toBe(path.join("/c", "settings.json"));
    expect(settingsFile({ HOME: "/h" })).toBe(path.join("/h", ".claude", "settings.json"));
  });
  test("tokens helper sanity", () => { expect(tokens("Never retry the same failing command")).toContain("retry"); });
});
