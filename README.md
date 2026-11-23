<pre align="center">
         ·         ┃         ·         
     ·        ╲    ▲    ╱        ·     
  ━━━━━━━━━━━━━━  ╱ ╲  ━━━━━━━━━━━━━━  
                 ╱ ◉ ╲                 
  ━━━━━━━━━━━━  ╱▁▁▁▁▁╲  ━━━━━━━━━━━━  
     ·        ╱    ┃    ╲        ·     
         ·         ┃         ·         
                                       
┏┳┓ ┏━┓ ┏━╸ ╻ ╻ ╻ ┏┓╻ ┏━╸   ┏━╸ ┏━┓ ╺┳┓
┃┃┃ ┣━┫ ┃   ┣━┫ ┃ ┃┗┫ ┣╸    ┃╺┓ ┃ ┃  ┃┃
╹ ╹ ╹ ╹ ┗━╸ ╹ ╹ ╹ ╹ ╹ ┗━╸   ┗━┛ ┗━┛ ╺┻┛

       ✠  DEUS · EX · MACHINA  ✠
           IN SILICO VERITAS
</pre>

# Install

One command. It downloads the matching release for your system, checks its SHA-256 checksum and puts
`claude-rs` and `machine-god` on your PATH. No admin rights needed.

**Linux / macOS** (Terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/frank-ink/machine-god/main/scripts/install/install.sh | bash
```

**Windows** (PowerShell, not as administrator):

```powershell
irm https://raw.githubusercontent.com/frank-ink/machine-god/main/scripts/install/install.ps1 | iex
```

Then open a **new** terminal and type:

```bash
machine-god
```

Prebuilt for Linux x64/arm64, macOS Intel/Apple Silicon, Windows x64/arm64.
All releases: [github.com/frank-ink/machine-god/releases](https://github.com/frank-ink/machine-god/releases).

# First start, step by step

1. **Start it.** `machine-god` (or `claude-rs`, same program) opens the Machine God terminal UI with the banner
   above. Your conversation stays in your terminal's own scrollback.
2. **Choose where the thinking happens.** Machine God talks to models through Anthropic's Agent SDK.
   You need one of these:
   - **Your own Claude account:** install the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/setup),
     run `claude /login` once (or type `/login` inside Machine God). Same account, models and limits as Claude Code.
   - **Free pool via Omnipool:** if an Omnipool install is found on this machine, Machine God starts it and routes
     turns through free model providers automatically; no key is typed or stored by Machine God. Switch off with
     `CLAUDE_RS_OMNIPOOL=0`, open its web app with `/api`. *Omnipool is not yet publicly distributed (planned).*
3. **Ask something.** Type a message and press Enter. `/help` lists all commands, `/model` switches models,
   `/usage` shows your usage, `/status` shows the session state.
4. **Update later** by running the same install command again.

### First-start companion and ChatGPT bridge (optional)

The very first time you start `machine-god` in a terminal, a short companion runs before the UI. It looks only for
the **ChatGPT desktop app** or an **open window titled ChatGPT** (it never reads browser cookies, history or
profiles); if it finds nothing it asks once whether you use ChatGPT. If you do, it offers to download a small local
model (Qwen 0.8B, 812 MB, only after you say yes; it runs on your machine through llama.cpp's `llama-server` on
127.0.0.1) that greets you and offers the bridge. Say no at any point and nothing is installed; your answer is
remembered in `~/.config/machine-god/firstrun.json` (Windows: `%APPDATA%\machine-god`), delete it to be asked again.

The bridge lets Machine God ask ChatGPT through **your own** ChatGPT account. **Automating the ChatGPT web
interface may violate OpenAI's terms of use and can get your account suspended; only set it up if you accept that
risk.** After an explicit yes it installs [uv](https://docs.astral.sh/uv/) if missing, creates a Python environment with
pinned `aiohttp` and `patchright`, downloads its own Chromium, starts a local service (127.0.0.1 only, random port,
random token in a mode-600 file) with its own browser profile, opens a window where **you** log in to ChatGPT, and
registers one MCP tool for you: `claude mcp add --scope user machine-god-chatgpt -- <python> <script>` (if the
`claude` CLI is missing it prints that exact command). Data lives in `~/.local/share/machine-god`
(Windows: `%LOCALAPPDATA%\machine-god`). Honest limits: it drives a web page, so a ChatGPT UI change can break it, and
it was written on Linux; the macOS and Windows paths are untested.

### Interests (optional)

Machine God can keep its own interests and research them. Each topic has a weight, a novelty and a boredom value:
good research makes a topic stronger, repeating it makes it boring for a while, untouched topics fade after about two
weeks, and every round can discover new subtopics that become interests of their own. You can steer with like/dislike,
and `history` shows how its interests changed. Nothing runs in the background; you start rounds yourself.

```bash
machine-god interests seed "deep sea ecology" "jazz harmony"
machine-god interests run --rounds 3   # uses your `claude` login; --backend chatgpt uses the bridge
machine-god interests list
machine-god interests history
```

Details and the exact model: [interest/README.md](interest/README.md).

### Planned (not in v0.1.0 yet)

- `/features` overview, `/retina` window, live token meter in the status line
- FranKenstein 3.0 / Agent Zero plugin as a one-click option (the plugin source is in `plugins/frankenstein3`)

Machine God is a fork of [claude-code-rust](https://github.com/srothgan/claude-code-rust) (Apache-2.0); see
[NOTICE.md](NOTICE.md). Built by Gabriel.

# Details

## Claude Code Rust

An alternative terminal frontend for Claude Code, written in Rust. Your conversation stays in your terminal's own scrollback, without flicker.

[![Version](https://img.shields.io/github/v/release/frank-ink/machine-god?label=version)](https://github.com/frank-ink/machine-god/releases/latest)
[![CI](https://github.com/frank-ink/machine-god/actions/workflows/pr.yml/badge.svg)](https://github.com/frank-ink/machine-god/actions/workflows/pr.yml)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://frank-ink.github.io/machine-god/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://www.apache.org/licenses/LICENSE-2.0)

### About

Claude Code Rust (`claude-rs`) is a terminal UI for Claude Code built on [Ratatui](https://ratatui.rs/). It runs your sessions through Anthropic's official Agent SDK via a local bridge, with the same account, models, tools, file edits, permissions, MCP servers, skills and session history as Claude Code itself. Only the interface is different.

<p align="center">
  <img src="assets/demo.gif" alt="Claude Code Rust explaining the terminal problems its native Rust interface solves" width="900">
</p>

### Prerequisite

Install the Claude Code CLI and keep `claude` on `PATH` for some functionality not yet supported by the Anthropic SDK. See the [dependency and feature overview](https://frank-ink.github.io/machine-god/about.html#claude-cli-dependencies) for details.

### Install

#### Install script (recommended, v0.14.0+)

**macOS/Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/frank-ink/machine-god/main/scripts/install/install.sh | sh
```

**Windows PowerShell:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm 'https://raw.githubusercontent.com/frank-ink/machine-god/main/scripts/install/install.ps1' | iex"
```

<details>
<summary><b>Already have Node.js 24+? Use npm instead</b></summary>

```bash
npm install -g claude-code-rust
```

<sub>The package ships prebuilt platform binaries and its own Bun runtime for the Agent SDK bridge, so no Rust toolchain, Bun install, or `postinstall` script is needed. Node.js 24+ is still required to run the `claude-rs` launcher.</sub>

</details>

See the [installation guide](https://frank-ink.github.io/machine-god/installation.html) for release pinning, custom install locations, switching install methods, uninstall, and troubleshooting.

### Usage

```bash
claude-rs
claude-rs --model opus --permission-mode plan "Review this project"
claude-rs --continue
```

Follow [Your first session](https://frank-ink.github.io/machine-god/usage.html) for a complete walkthrough. See the [CLI reference](https://frank-ink.github.io/machine-god/cli.html) for startup flags, shell completions and man pages.

### Why use it

Stock Claude Code offers two renderers, and each one gives something up. The classic renderer keeps the conversation in your terminal's scrollback but redraws it as output streams, which can flicker, jump the scroll position, or duplicate output in long sessions. The [fullscreen renderer](https://code.claude.com/docs/en/fullscreen) fixes that by moving the conversation to the alternate screen, where your terminal's search, tmux copy mode and native text selection no longer see it.

Claude Code Rust renders inline. Finished messages and tool output are written into your terminal's scrollback once, and only the live area at the bottom (the streaming reply, the composer and the footer) is redrawn.

| | Stock classic | Stock fullscreen | Claude Code Rust |
| --- | --- | --- | --- |
| Conversation lives in | Terminal scrollback | Alternate screen | Terminal scrollback |
| Flicker while streaming | Can flicker | No | No |
| Terminal search and tmux copy mode | Yes | Only after exporting from transcript mode | Yes |
| Native text selection | Yes | Mouse is captured by default | Yes |
| Mouse controls in the app | No | Yes | No |

That makes it a good fit if you:

- scroll, search and copy with your terminal or tmux rather than inside the app;
- work in tmux, over SSH, or in Windows Terminal;
- resize windows or split panes while Claude is working;
- prefer a keyboard-driven interface with a single native binary.

It is not a feature-for-feature copy of Claude Code. Some stock features are unavailable, and a few account and plugin operations still call the `claude` CLI. The [feature overview](https://frank-ink.github.io/machine-god/about.html#feature-overview) lists both. There are no benchmarks against the stock interface yet; the comparison above describes how each renderer works, not measured speed or memory.

### What you get

- **Core Claude Code workflow:** tool calls, inline edit diffs, permission prompts, plan mode, subagents and background tasks, MCP authorization, skills and SDK slash commands.
- **Session tools:** a searchable `/resume` picker with forking, `/rewind`, `/compact`, `/export` to Markdown, and `/btw` side questions while a turn runs.
- **Fullscreen views when you want them:** a Git diff viewer (`/diff`), subagent view (`/agents`), settings (`/config`), status, usage and help. These open on demand and close back to the inline chat.
- **Supportability:** `claude-rs doctor`, redacted debug bundles, shell completions and man pages.

### Documentation

Choose a path through the [documentation](https://frank-ink.github.io/machine-god/):

- **Start using the app:** [Install](https://frank-ink.github.io/machine-god/installation.html) and complete [your first session](https://frank-ink.github.io/machine-god/usage.html).
- **Work with it:** [Conversations](https://frank-ink.github.io/machine-god/conversations.html), [configuration](https://frank-ink.github.io/machine-god/configure.html), and [MCP servers and plugins](https://frank-ink.github.io/machine-god/integrations.html).
- **Look something up:** [CLI reference](https://frank-ink.github.io/machine-god/cli.html), [slash commands](https://frank-ink.github.io/machine-god/commands.html), and [settings reference](https://frank-ink.github.io/machine-god/settings.html).
- **Resolve a problem:** [Troubleshooting](https://frank-ink.github.io/machine-god/troubleshooting.html) and [diagnostics](https://frank-ink.github.io/machine-god/diagnostics.html).
- **Contribute or maintain:** [Development](https://frank-ink.github.io/machine-god/development.html), [testing](https://frank-ink.github.io/machine-god/testing.html), [architecture](https://frank-ink.github.io/machine-god/architecture.html), and [contribution policy](CONTRIBUTING.md).

For the design history, including the move from fullscreen to inline rendering in 0.12.0, see [I rebuilt Claude Code's terminal UI in Rust. Then I deleted 12,000 lines of it.](https://medium.com/@simonrothgang/i-rebuilt-claude-codes-terminal-ui-in-rust-then-i-deleted-12-000-lines-of-it-e8593a200452)

### Status

This project is pre-1.0 and under active development. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved.

Development follows new Agent SDK releases and problems found in daily use. The weekly Dependency Monitor tracks SDK updates. There is no fixed feature roadmap or date for 1.0.

### Limitations

Startup is still constrained by the upstream Claude Agent SDK runtime that this TUI wraps. The Rust interface itself is fast, but end-to-end readiness can still take noticeable time before a session is fully available. Improving that remains an active area of work.

### Billing

This app uses Anthropic's Agent SDK. See the [billing note](https://frank-ink.github.io/machine-god/about.html#billing-note) for the current upstream policy source and account-dependent limits.

### License

This project is licensed under the [Apache License 2.0](LICENSE). Apache-2.0 was chosen to keep usage and redistribution straightforward for individual users, downstream packagers, and commercial adopters.

### Disclaimer and Legal Notice

This project is not affiliated with, endorsed by, or supported by Anthropic.

A quick note on where this project stands, since I know people worry about this kind of thing: claude-code-rust is a terminal UI that I wrote from scratch in Rust. It is not a fork, copy or port of the latest Claude Code source leak. It talks to Anthropic's official [Agent SDK](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/agent-sdk) as a runtime dependency instead, the same way any other third-party tool would. No Anthropic source code was read or used as reference at any point during development.

The project authenticates through your existing Claude Code account via the Agent SDK, and the Agent SDK's terms allow building on top of it. Billing, credits, limits, and overage behavior are controlled by Anthropic, including any future changes Anthropic may make to how Agent SDK usage is metered. Other community projects do the same. As far as I can tell, using this project is fine, but I am a single maintainer, not a lawyer. If anything changes on Anthropic's end, I will update this section and adjust the project accordingly.

This project's source code is licensed under [Apache-2.0](LICENSE). The Agent SDK itself is proprietary and governed by [Anthropic's Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms).

For official Claude documentation, see [https://claude.ai/docs](https://claude.ai/docs).
