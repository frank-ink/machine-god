// Machine God GitHub onboarding (a step of the first-run companion; also `machine-god grid`).
//   1. Do you have a GitHub account? (no -> signup link)
//   2. SSH key: use ~/.ssh/id_ed25519 or create one with ssh-keygen (YOU type the passphrase), add it at github.com/settings/ssh/new, test ssh -T
//   3. GRID repo "machine-god-grid" (private): mailbox (control/, results/) and shared memory (memory/), cloned to the data dir over SSH.
// Every question can be answered no and the step moves on. Nothing is created on GitHub without you: with the `gh` CLI it offers
// `gh repo create machine-god-grid --private`, otherwise it shows the page and the exact name. Test switches: MG_GRID_REMOTE (use this git URL instead of
// GitHub, for tests), MG_GRID_DIR (clone location).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { homeDir, makeAsker, resolvePaths, run as defaultRun, whichSync } from "./mg-common.js";

export const GRID_NAME = "machine-god-grid";
export const URLS = {
  signup: "https://github.com/signup",
  sshNew: "https://github.com/settings/ssh/new",
  repoNew: "https://github.com/new",
};

export const sshPaths = (home) => {
  const dir = path.join(home, ".ssh");
  return { dir, priv: path.join(dir, "id_ed25519"), pub: path.join(dir, "id_ed25519.pub") };
};

/** ssh -T git@github.com: exit 1 with "successfully authenticated" is the success case. -> { ok, user } */
export function parseSshTest({ code, out }) {
  const ok = /successfully authenticated/i.test(out || "") && (code === 1 || code === 0);
  const m = /Hi ([A-Za-z0-9-]+)!/.exec(out || "");
  return { ok, user: ok && m ? m[1] : null };
}

export const GRID_README = `# Machine God GRID

This private repository is the shared mailbox and memory of your Machine God install.

- \`control/\`  requests from your AIs (for example ChatGPT through its GitHub connector): \`<id>.json\` with either
  \`{"cmd": "ls", "from": "chatgpt"}\` or \`{"question": "...", "from": "chatgpt"}\`
- \`results/\`  answers written by \`machine-god mailbox\` on your computer: \`<id>.json\`
- \`memory/\`   shared notes (the interest organ can export here later)

## The rule

Other AIs can only READ. \`machine-god mailbox\` runs a short fixed list of read-only commands (ls, cat, head, git status, git log, uname, df)
inside folders you approved. Everything else is shown in your terminal and runs only after you type \`yes\`. Nothing runs while you are not
at the terminal. Keep this repository **private**: anyone who can push here can send requests.

Run it on your computer: \`machine-god mailbox\` (foreground, polls this repo every 30 seconds, Ctrl-C stops it).
`;

export function initGridLayout(dir) {
  for (const d of ["control", "results", "memory"]) {
    fs.mkdirSync(path.join(dir, d), { recursive: true });
    const k = path.join(dir, d, ".gitkeep");
    if (!fs.existsSync(k)) fs.writeFileSync(k, "");
  }
  const r = path.join(dir, "README.md");
  if (!fs.existsSync(r)) fs.writeFileSync(r, GRID_README);
}

async function git(runFn, dir, args, { ident = false } = {}) {
  const pre = ident ? ["-c", "user.name=Machine God", "-c", "user.email=machine-god@users.noreply.github.com"] : [];
  return runFn("git", [...pre, "-C", dir, ...args], { env: { GIT_TERMINAL_PROMPT: "0" } });
}

/** Clone (or reuse) the GRID repo, create the layout, push it. -> { status: "ready"|"failed", detail } */
export async function prepareGrid({ remote, dir, runFn = defaultRun }) {
  if (!fs.existsSync(path.join(dir, ".git"))) {
    fs.mkdirSync(path.dirname(dir), { recursive: true });
    const c = await runFn("git", ["clone", remote, dir], { env: { GIT_TERMINAL_PROMPT: "0" } });
    if (c.code !== 0) return { status: "failed", detail: `git clone failed: ${c.out.replace(/\s+/g, " ").slice(-200)}` };
  }
  const hasCommit = (await git(runFn, dir, ["rev-parse", "--verify", "-q", "HEAD"])).code === 0;
  if (!hasCommit) await git(runFn, dir, ["checkout", "-q", "-B", "main"]);
  const before = fs.existsSync(path.join(dir, "control")) && fs.existsSync(path.join(dir, "results")) && fs.existsSync(path.join(dir, "README.md"));
  initGridLayout(dir);
  await git(runFn, dir, ["add", "-A"]);
  const dirty = (await git(runFn, dir, ["diff", "--cached", "--quiet"])).code !== 0;
  if (dirty) {
    const hasName = (await git(runFn, dir, ["config", "user.name"])).out.trim() && (await git(runFn, dir, ["config", "user.email"])).out.trim();
    const c = await git(runFn, dir, ["commit", "-q", "-m", "Initialize Machine God GRID layout"], { ident: !hasName });
    if (c.code !== 0) return { status: "failed", detail: `commit failed: ${c.out.replace(/\s+/g, " ").slice(-200)}` };
  }
  const br = (await git(runFn, dir, ["symbolic-ref", "--short", "HEAD"])).out.trim() || "main";
  const p = await git(runFn, dir, ["push", "-q", "-u", "origin", `HEAD:${br}`]);
  if (p.code !== 0) return { status: "failed", detail: `git push failed: ${p.out.replace(/\s+/g, " ").slice(-200)}` };
  return { status: "ready", detail: before && !dirty ? "already set up" : "layout pushed" };
}

/** Unauthenticated check: a private repo answers 404 to the public API. -> "public" | "not-public" | "unknown" */
export async function repoVisibility(user, fetchFn = fetch) {
  try {
    const r = await fetchFn(`https://api.github.com/repos/${user}/${GRID_NAME}`, { headers: { accept: "application/vnd.github+json", "user-agent": "machine-god" }, signal: AbortSignal.timeout(8000) });
    if (r.status === 200) return "public";
    if (r.status === 404) return "not-public";
  } catch {}
  return "unknown";
}

/**
 * ctx: { ask, text, log, env, platform, home, paths, runFn, which, fetchFn }
 * -> record { account, ssh, sshUser?, grid, gridDir?, detail? }
 */
export async function runGithubStep(ctx) {
  const { ask, text, log } = ctx;
  const env = ctx.env || process.env;
  const platform = ctx.platform || process.platform;
  const home = ctx.home || homeDir(env, platform);
  const paths = ctx.paths || resolvePaths({ env, platform });
  const runFn = ctx.runFn || defaultRun;
  const which = ctx.which || ((n) => whichSync(n, env, platform));
  const rec = { account: "unknown", ssh: "skipped", grid: "skipped" };
  log("");
  log("== GitHub (optional) ==");
  log("A private GitHub repository can be the shared mailbox and memory between Machine God and your AIs. It needs a GitHub account and an SSH key.");

  // 1. account
  if (await ask("Do you have a GitHub account? [y/N]")) rec.account = "yes";
  else {
    log(`  Create one (free): ${URLS.signup}`);
    if (!(await ask("  Continue once your account exists? [y/N]"))) {
      rec.account = "no";
      log("  Skipping GitHub. Run `machine-god grid` any time later.");
      return rec;
    }
    rec.account = "created";
  }

  // 2. SSH
  const keys = sshPaths(home);
  const win = platform === "win32";
  let sshUser = null;
  if (!which("ssh") || !which("ssh-keygen")) {
    log(win
      ? "  OpenSSH is missing. Windows 10/11: Settings -> Apps -> Optional features -> add \"OpenSSH Client\", then run `machine-god grid` again."
      : "  `ssh` / `ssh-keygen` not found. Install the OpenSSH client with your package manager, then run `machine-god grid` again.");
    rec.ssh = "tools-missing";
  } else if (await ask("Set up the SSH key for GitHub now? [y/N]")) {
    if (!fs.existsSync(keys.pub)) {
      log(`  No key at ${keys.pub}.`);
      if (await ask("  Create one now with `ssh-keygen -t ed25519 -C machine-god`? You type the passphrase yourself (empty = none); Machine God never sees it. [y/N]")) {
        fs.mkdirSync(keys.dir, { recursive: true, mode: 0o700 });
        ask.suspend?.();
        const r = await runFn("ssh-keygen", ["-t", "ed25519", "-C", "machine-god", "-f", keys.priv], { stdio: "inherit" });
        if (r.code !== 0 || !fs.existsSync(keys.pub)) log("  ssh-keygen did not create a key.");
      }
    } else log(`  Found your key: ${keys.pub}`);
    if (fs.existsSync(keys.pub)) {
      log("  Your PUBLIC key (safe to share, this is what GitHub needs):");
      log("  " + fs.readFileSync(keys.pub, "utf8").trim());
      log(`  Add it here (Title: machine-god, Key type: Authentication Key): ${URLS.sshNew}`);
      if (await ask("  Added it on GitHub? [y/N]")) {
        for (let attempt = 0; attempt < 3; attempt++) {
          const r = await runFn("ssh", ["-T", "-o", "ConnectTimeout=15", "git@github.com"], {});
          const t = parseSshTest(r);
          if (t.ok) {
            sshUser = t.user;
            rec.ssh = "ok";
            log(`  SSH works${t.user ? ` (GitHub user ${t.user})` : ""}.`);
            break;
          }
          rec.ssh = "failed";
          log(`  SSH test failed: ${(r.out || "").replace(/\s+/g, " ").slice(-160)}`);
          if (!(await ask("  Test again? [y/N]"))) break;
        }
      } else rec.ssh = "key-not-added";
    } else rec.ssh = "no-key";
  } else rec.ssh = "declined";
  if (sshUser) rec.sshUser = sshUser;

  // 3. GRID repo
  const override = env.MG_GRID_REMOTE;
  if (rec.ssh !== "ok" && !override) {
    log("  The GRID repo needs a working SSH connection to GitHub. Skipping it; run `machine-god grid` when SSH works.");
    return rec;
  }
  if (!(await ask(`Set up your private GRID repo "${GRID_NAME}" (mailbox + shared memory) now? [y/N]`))) {
    rec.grid = "declined";
    return rec;
  }
  let remote = override;
  if (!remote) {
    const user = sshUser || (await text("  Your GitHub username:"));
    if (!/^[A-Za-z0-9-]{1,39}$/.test(user || "")) {
      rec.grid = "failed";
      rec.detail = "no valid GitHub username";
      log("  No valid username; skipping.");
      return rec;
    }
    remote = `git@github.com:${user}/${GRID_NAME}.git`;
    const ghAuthed = which("gh") && (await runFn("gh", ["auth", "status"])).code === 0;
    let created = false;
    if (ghAuthed && (await ask(`  \`gh\` is installed and logged in. Create the PRIVATE repo with \`gh repo create ${GRID_NAME} --private\` now? [y/N]`))) {
      const r = await runFn("gh", ["repo", "create", GRID_NAME, "--private", "--description", "Machine God GRID: mailbox and shared memory"]);
      created = r.code === 0 || /already exists|Name already exists/i.test(r.out);
      log(created ? "  repo ready." : `  gh could not create it: ${r.out.replace(/\s+/g, " ").slice(-160)}`);
    }
    if (!created) {
      log(`  Create it yourself: ${URLS.repoNew}`);
      log(`    Repository name: ${GRID_NAME}   Visibility: Private   (leave README/.gitignore/license unchecked)`);
      if (!(await ask("  Created it? [y/N]"))) {
        rec.grid = "declined";
        return rec;
      }
    }
    const vis = await repoVisibility(user, ctx.fetchFn);
    if (vis === "public") {
      log(`  WARNING: ${GRID_NAME} is PUBLIC. Anyone could send requests and read your results. Make it private (repo Settings -> Danger Zone -> Change visibility).`);
      if (!(await ask("  Continue anyway? [y/N]"))) {
        rec.grid = "declined";
        rec.detail = "repo is public";
        return rec;
      }
    }
  } else log(`  Using the git remote from MG_GRID_REMOTE.`);
  const dir = env.MG_GRID_DIR || path.join(paths.dataDir, "grid");
  const g = await prepareGrid({ remote, dir, runFn });
  rec.grid = g.status;
  rec.detail = g.detail;
  if (g.status === "ready") {
    rec.gridDir = dir;
    fs.mkdirSync(paths.configDir, { recursive: true });
    fs.writeFileSync(path.join(paths.configDir, "grid.json"), JSON.stringify({ remote, dir }, null, 2) + "\n", { mode: 0o600 });
    log(`  GRID repo ready in ${dir} (${g.detail}). Layout: control/ results/ memory/ README.md`);
    log("  Start the mailbox when you want AIs to reach this computer: machine-god mailbox");
  } else log(`  GRID setup failed: ${g.detail}`);
  return rec;
}

export async function main(argv = process.argv.slice(2), env = process.env) {
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log("machine-god grid: set up GitHub SSH and your private machine-god-grid repo (every step asks first)");
    return 0;
  }
  const ask = makeAsker({ env });
  try {
    const rec = await runGithubStep({ ask, text: ask.text, log: (s = "") => console.log(s), env });
    return rec.grid === "failed" ? 1 : 0;
  } finally {
    ask.close();
  }
}

if (import.meta.main) main().then((c) => process.exit(c), (e) => (console.error(`grid: ${String(e.message || e).slice(0, 300)}`), process.exit(1)));
