import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { makeAsker } from "./mg-common.js";
import * as G from "./mg-github.js";

const tmp = () => fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mg-gh-")));
const git = (cwd, ...a) => spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.invalid", ...a], { cwd, encoding: "utf8" });
const bare = () => {
  const root = tmp();
  const o = path.join(root, "origin.git");
  git(root, "init", "-q", "--bare", "-b", "main", o);
  return { root, o };
};
const sink = () => {
  const lines = [];
  return { out: { write: (s) => lines.push(s) }, log: (s = "") => lines.push(s + "\n"), text: () => lines.join("") };
};
const SSH_OK = { code: 1, out: "Hi tester! You've successfully authenticated, but GitHub does not provide shell access.\n" };
const SSH_BAD = { code: 255, out: "git@github.com: Permission denied (publickey).\n" };

function harness({ answers, home = tmp(), extraEnv = {}, ssh = [SSH_OK], tools = ["ssh", "ssh-keygen"], keygenWorks = true, platform = "linux", fetchStatus = 404 }) {
  const s = sink();
  const env = { MG_FIRSTRUN_ANSWERS: answers, ...extraEnv };
  const ask = makeAsker({ env, output: s.out });
  const calls = [];
  const sshQueue = [...ssh];
  const runFn = async (cmd, args, opts = {}) => {
    calls.push([cmd, ...args]);
    if (cmd === "ssh-keygen") {
      expect(opts.stdio).toBe("inherit"); // the user types the passphrase, we never see it
      if (!keygenWorks) return { code: 1, out: "" };
      const f = args[args.indexOf("-f") + 1];
      fs.writeFileSync(f, "PRIVATE-MOCK");
      fs.writeFileSync(f + ".pub", "ssh-ed25519 AAAAMOCKPUBLICKEY machine-god\n");
      return { code: 0, out: "" };
    }
    if (cmd === "ssh") return sshQueue.length > 1 ? sshQueue.shift() : sshQueue[0];
    return (await import("./mg-common.js")).run(cmd, args, opts);
  };
  const paths = { configDir: path.join(home, "cfg"), dataDir: path.join(home, "data") };
  const ctx = { ask, text: ask.text, log: s.log, env, platform, home, paths, runFn, which: (n) => (tools.includes(n) ? `/usr/bin/${n}` : null), fetchFn: async () => ({ status: fetchStatus }) };
  return { s, ctx, calls, home, paths };
}

describe("parsing and layout", () => {
  test("ssh -T success is exit 1 plus the sentence; user name extracted", () => {
    expect(G.parseSshTest(SSH_OK)).toEqual({ ok: true, user: "tester" });
    expect(G.parseSshTest(SSH_BAD)).toEqual({ ok: false, user: null });
    expect(G.parseSshTest({ code: 1, out: "something else" }).ok).toBe(false);
  });
  test("links", () => {
    expect(G.URLS).toEqual({ signup: "https://github.com/signup", sshNew: "https://github.com/settings/ssh/new", repoNew: "https://github.com/new" });
  });
  test("layout: control, results, memory, README with the rule", () => {
    const d = tmp();
    G.initGridLayout(d);
    for (const x of ["control/.gitkeep", "results/.gitkeep", "memory/.gitkeep", "README.md"]) expect(fs.existsSync(path.join(d, x))).toBe(true);
    expect(fs.readFileSync(path.join(d, "README.md"), "utf8")).toContain("Other AIs can only READ");
  });
  test("repoVisibility: 200 public, 404 not public, error unknown", async () => {
    expect(await G.repoVisibility("u", async () => ({ status: 200 }))).toBe("public");
    expect(await G.repoVisibility("u", async () => ({ status: 404 }))).toBe("not-public");
    expect(await G.repoVisibility("u", async () => { throw new Error("offline"); })).toBe("unknown");
  });
});

describe("prepareGrid over a local bare repo", () => {
  test("empty remote: clone, layout, commit, push; second run is a no-op; remote has the files", async () => {
    const { root, o } = bare();
    const dir = path.join(root, "grid");
    const r = await G.prepareGrid({ remote: o, dir });
    expect(r).toEqual({ status: "ready", detail: "layout pushed" });
    const check = path.join(root, "check");
    git(root, "clone", "-q", o, check);
    for (const x of ["control/.gitkeep", "results/.gitkeep", "memory/.gitkeep", "README.md"]) expect(fs.existsSync(path.join(check, x))).toBe(true);
    expect((await G.prepareGrid({ remote: o, dir })).detail).toBe("already set up");
  });
  test("unreachable remote -> failed, not thrown", async () => {
    const root = tmp();
    const r = await G.prepareGrid({ remote: path.join(root, "nope.git"), dir: path.join(root, "grid") });
    expect(r.status).toBe("failed");
    expect(r.detail).toContain("git clone failed");
  });
});

describe("runGithubStep", () => {
  test("no account and not continuing: shows the signup link, skips everything", async () => {
    const h = harness({ answers: "no,no" });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec).toMatchObject({ account: "no", ssh: "skipped", grid: "skipped" });
    expect(h.s.text()).toContain("https://github.com/signup");
    expect(h.calls).toEqual([]);
  });
  test("saying no everywhere does nothing", async () => {
    const h = harness({ answers: "yes,no" });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec).toMatchObject({ account: "yes", ssh: "declined", grid: "skipped" });
    expect(h.calls).toEqual([]);
  });
  test("full path: keygen (user confirms), public key + link shown, ssh test ok, grid cloned from a local bare repo", async () => {
    const { root, o } = bare();
    const dir = path.join(root, "grid");
    const h = harness({ answers: "yes,yes,yes,yes,yes", extraEnv: { MG_GRID_REMOTE: o, MG_GRID_DIR: dir } });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec).toMatchObject({ account: "yes", ssh: "ok", sshUser: "tester", grid: "ready", gridDir: dir });
    const text = h.s.text();
    expect(text).toContain("ssh-ed25519 AAAAMOCKPUBLICKEY");
    expect(text).not.toContain("PRIVATE-MOCK");
    expect(text).toContain("https://github.com/settings/ssh/new");
    expect(h.calls[0]).toEqual(["ssh-keygen", "-t", "ed25519", "-C", "machine-god", "-f", path.join(h.home, ".ssh", "id_ed25519")]);
    expect(h.calls[1]).toEqual(["ssh", "-T", "-o", "ConnectTimeout=15", "git@github.com"]);
    expect(JSON.parse(fs.readFileSync(path.join(h.paths.configDir, "grid.json"), "utf8"))).toEqual({ remote: o, dir });
    expect(fs.existsSync(path.join(dir, "control"))).toBe(true);
    if (process.platform !== "win32") expect(fs.statSync(path.join(h.home, ".ssh")).mode & 0o777).toBe(0o700);
  });
  test("an existing key is reused, no ssh-keygen question", async () => {
    const home = tmp();
    fs.mkdirSync(path.join(home, ".ssh"));
    fs.writeFileSync(path.join(home, ".ssh", "id_ed25519.pub"), "ssh-ed25519 EXISTING me\n");
    const h = harness({ home, answers: "yes,yes,yes,no" });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec.ssh).toBe("ok");
    expect(h.calls.some((c) => c[0] === "ssh-keygen")).toBe(false);
    expect(h.s.text()).toContain("Found your key");
  });
  test("failed ssh test can be retried; declining keeps the grid step out", async () => {
    const h = harness({ answers: "yes,yes,yes,yes,yes,no", ssh: [SSH_BAD] });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec.ssh).toBe("failed");
    expect(rec.grid).toBe("skipped");
    expect(h.calls.filter((c) => c[0] === "ssh").length).toBe(2);
    expect(h.s.text()).toContain("Permission denied");
  });
  test("a second try that works", async () => {
    const h = harness({ answers: "yes,yes,yes,yes,yes,yes,no", ssh: [SSH_BAD, SSH_OK] });
    expect((await G.runGithubStep(h.ctx)).ssh).toBe("ok");
  });
  test("ssh-keygen declined: no key created", async () => {
    const h = harness({ answers: "yes,yes,no" });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec.ssh).toBe("no-key");
    expect(h.calls).toEqual([]);
  });
  test("OpenSSH missing: Windows gets the optional-feature hint", async () => {
    const h = harness({ answers: "yes", tools: [], platform: "win32" });
    const rec = await G.runGithubStep(h.ctx);
    expect(rec.ssh).toBe("tools-missing");
    expect(h.s.text()).toContain("OpenSSH Client");
  });
  test("real flow without gh: shows github.com/new with the exact name and Private, then clones over SSH url", async () => {
    const cloned = [];
    const h = harness({ answers: "yes,yes,yes,yes,yes,yes" });
    h.ctx.home = h.home;
    const orig = h.ctx.runFn;
    h.ctx.runFn = async (cmd, args, o) => (cmd === "git" && args[0] === "clone" ? (cloned.push(args[1]), { code: 128, out: "mock: no network" }) : orig(cmd, args, o));
    const rec = await G.runGithubStep(h.ctx);
    const text = h.s.text();
    expect(text).toContain("https://github.com/new");
    expect(text).toContain("machine-god-grid");
    expect(text).toContain("Private");
    expect(cloned).toEqual(["git@github.com:tester/machine-god-grid.git"]);
    expect(rec.grid).toBe("failed");
  });
  test("gh installed and logged in: offers gh repo create --private", async () => {
    const h = harness({ answers: "yes,yes,yes,yes,yes,yes", tools: ["ssh", "ssh-keygen", "gh"] });
    const orig = h.ctx.runFn;
    h.ctx.runFn = async (cmd, args, o) => {
      if (cmd === "gh") return (h.calls.push([cmd, ...args]), { code: 0, out: "" });
      if (cmd === "git" && args[0] === "clone") return { code: 128, out: "mock" };
      return orig(cmd, args, o);
    };
    await G.runGithubStep(h.ctx);
    expect(h.calls).toContainEqual(["gh", "repo", "create", "machine-god-grid", "--private", "--description", "Machine God GRID: mailbox and shared memory"]);
    expect(h.s.text()).not.toContain("https://github.com/new");
  });
  test("a PUBLIC repo is flagged and the default answer stops", async () => {
    const h = harness({ answers: "yes,yes,yes,yes,yes,yes,no", fetchStatus: 200 });
    const orig = h.ctx.runFn;
    h.ctx.runFn = async (cmd, args, o) => (cmd === "git" ? (h.calls.push(["GIT-CALLED"]), { code: 0, out: "" }) : orig(cmd, args, o));
    const rec = await G.runGithubStep(h.ctx);
    expect(rec).toMatchObject({ grid: "declined", detail: "repo is public" });
    expect(h.s.text()).toContain("WARNING");
    expect(h.calls.some((c) => c[0] === "GIT-CALLED")).toBe(false);
  });
});
