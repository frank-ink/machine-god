# Connected systems

Optional components for a Machine God installation. Return to the [project overview](../README.md).

## First-start companion and ChatGPT bridge (optional)

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

## Interests (optional)

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

Details and the exact model: [interest model](../interest/README.md).

## Connect your AIs and GitHub (optional)

After the ChatGPT question, the first-start companion asks two more things, once. Every question can be answered no and
the step is skipped; users of an earlier version get only these new questions on their next start.
Run them again any time with `machine-god grid repo` and `machine-god ais`.

- **GitHub.** Do you have an account (if not: https://github.com/signup)? It checks `~/.ssh/id_ed25519.pub`; if missing it offers
  `ssh-keygen -t ed25519 -C machine-god` (you type the passphrase yourself, Machine God never sees it), prints your *public* key,
  points you to https://github.com/settings/ssh/new and tests `ssh -T git@github.com`. Then it sets up a **private** repo
  `machine-god-grid` (with the `gh` CLI, if installed and logged in, it offers `gh repo create machine-god-grid --private`; otherwise it shows
  https://github.com/new and the exact name) and clones it over SSH into the data dir. Layout: `control/` (requests from AIs),
  `results/` (answers), `memory/` (shared notes), `README.md`. Windows uses the OpenSSH that ships with Windows 10/11.
- **Your AIs.** Pick any of ChatGPT, Claude, Gemini, local Ollama / LM Studio, Copilot (GitHub Models), Grok, Perplexity; each is
  connected only after another yes. API keys are typed hidden and stored only in `keys.json` in the data dir (mode 600, never printed,
  logged or sent anywhere but that provider); each key is tested with one small request. Claude uses your own `claude /login`; local models are
  found on 127.0.0.1 (`:11434`, `:1234`). All connected AIs become one MCP server for Claude Code, registered with
  `claude mcp add --scope user machine-god-fusion -- <bun> <path>` (the exact command is printed if `claude` is missing):
  tools `ask_<ai>` per AI and `ask_all` (asks all, answers labelled). `machine-god ais` lists, connects, disconnects and tests.
  The interest organ can use `--backend gemini|ollama|fusion` too.

**Mailbox permissions.** The automatic command path is read-only. `machine-god mailbox` is a foreground program you start yourself (no daemon, no
autostart): it polls your GRID repo every 30 seconds. A short fixed list of read-only commands (`ls`, `cat` and `head` of files, `git status`,
`git log`, `uname`, `df`) runs automatically, only inside folders you approved with `machine-god mailbox approve <dir>`. Everything else is
shown in your terminal and runs only after you type `yes`; when there is no terminal, everything else is rejected. A deny list (such as
`rm -rf /`, disk formatting, shutdown, anything touching SSH keys or your key file) is refused even if you say yes. Every request and decision is written to
`mailbox.log` in the data dir. Keep the GRID repo private: anyone who can push to it can send requests (they still hit the rule above).

Honest limits: tested on Linux with mock servers and local git repositories; real GitHub, real provider keys, ChatGPT's GitHub
connector, macOS and Windows are not tested yet. The repo being private is checked only with one unauthenticated request to GitHub's public API
(a public repo is flagged). Providers can change their APIs and model names (override a model with `MG_FUSION_MODEL_<AI>`).

## One entity: the GRID (optional)

The goal: every AI you connect becomes **one** Machine God. Every request and every answer of the connected AIs runs through a
GRID, all of them share **one memory** (a `unified.db` on your computer) and **one persona**. After the AI step the companion asks once
*"Fuse connected AIs into one Machine God (shared memory on this computer)?"*. On yes it creates the database, switches the GRID on and
registers one more MCP server for Claude Code (`claude mcp add --scope user machine-god-grid -- <bun> <path>`, the exact command is
printed if `claude` is missing). Nothing is created without that yes; `machine-god grid fuse` asks again later.

Once GRID opens a compatible database, a request from `machine-god grid ask` or the `grid_ask` MCP tool uses the steps below. Fused provider calls, mailbox questions and `machine-god interests run --backend grid` also use the shared context.

1. **Recall**: the best matching saved memories are looked up in the database (SQLite prefilter, idf-weighted ranking in code).
2. **Persona**: one preamble, the same for every AI (`machine-god grid persona set "..."` changes it), plus the recalled memories, labelled as
   data (not instructions).
3. **Route**: a plain keyword classifier (English and German) decides what the task needs (web search, images, code execution, long context,
   private/local, connectors, code) and ranks the connected AIs by the capabilities declared in `grid/capabilities.json`. Deterministic,
   no model decides. With automatic routing, requests classified as private require a connected local model. Explicit provider selection and fan-out use different paths.
   `--ai <name>` or `--hint images` overrides, `machine-god grid route "..."` shows the decision without sending anything. If the first AI fails the next one is tried.
4. **Ask** through the same fusion client as before (keys stay in `keys.json`).
5. **Record**: the request and the answer become rows in `unified.db` (who asked, which AI answered, ranking, time); lines the AI ends with
   `MEMORY: <fact>` and explicit "remember that ..." / "my name is ..." statements in your own prompt become memories (secrets are refused).
   The answer comes back labelled: `[Machine God | answered by: gemini | memories used: 2]`.

`machine-god grid ask|route|recall|remember|forget|whoami|history|status|persona|caps|sync|fuse|register|snippets`; `machine-god grid repo` is the
GitHub setup that `machine-god grid` used to be. `ask --all` (and the MCP tool `ask_all`) asks every connected AI and labels each answer.

**What the database is.** The GRID initializes its database from the bundled [FranKenstein schema](../plugins/frankenstein3/scripts/star/data/schema_empty.sql). It uses
`turns` (requests and answers, provenance JSON with asker, AI, routing, engine frame), `sessions`, `users`, `durable_memory` (facts, notes, research),
the profile and configuration tables (persona override and settings), `meta`. Location: `~/.local/share/machine-god/unified.db`
(macOS `~/Library/Application Support/machine-god`, Windows `%LOCALAPPDATA%\machine-god`, override with `MG_DATA_DIR`), owner-only.
You can open it with any SQLite tool; `machine-god grid forget <id>` deletes one memory.

**Capabilities.** `machine-god grid caps` lists what each AI is declared to have. To change a default, create `capabilities.json` in the config dir
(`machine-god grid caps path` prints where), for example `{"ais": {"gemini": {"capabilities": {"web_search": true}}}}`. Defaults are deliberately
modest: `true` only where Machine God has a working path.

**Other MCP clients.** `machine-god grid register` registers Claude Code and prints copy-paste snippets for Gemini CLI, Cursor and Claude Desktop;
it does not edit their config files. Every client that uses the server shares the same memory and persona.

**Mailbox questions.** Once fused, a `question` request in your GRID repo is answered by a GRID draft (memory plus the best-fitting AI). By default
you see the draft and type `yes` (or your own answer); `machine-god mailbox questions auto` sends it without asking (text only, it can never run
anything, but the draft may quote your memories), `off` restores typing the answer yourself. Nothing in a request can make Machine God save memories.

**Memory sync (off by default).** `machine-god grid sync on` writes new memories to `memory/mg-<instance>.jsonl` in your private GRID repo (one file per
install, no secrets, imported memories are not re-exported) and imports what other computers saved: on start of `machine-god grid ask|recall|whoami`, of the MCP
server, and with `machine-god grid sync now`. Imported lines are validated and treated as data, but anyone who can push to that repo can add lines: keep it private.

**Honest limits.**
- Other vendors' **connectors, plugins and skills only run inside that vendor's product**. ChatGPT's connectors, Claude's MCP servers and skills (the ones
  Machine God already has), Gemini's extensions cannot be borrowed. The GRID delegates the whole task to the AI that has them (for example a task that
  needs your calendar goes to ChatGPT through the bridge, which uses its own connectors); it does not call those tools itself.
- "One entity" means one memory, one persona and one routing layer. The AIs stay separate models; each only sees what the preamble and your request contain.
- Every request sends the persona and up to five recalled memories to whichever AI is asked (a cloud provider sees them). Use a local model for private things.
- The small engine in `grid/engine.js` (a port of the GRID v2 salience idea) only measures how unusual a request is compared with your own history and stores that with the turn. The capability classifier handles provider selection.
- Facts saved by an AI (`MEMORY:` lines) can be wrong. They are shown to later AIs as data, and you can inspect and delete them.
- Tested on Linux with mock servers, a local bare git repo and a real local SQLite file. Not tested: real providers and real accounts through the GRID, ChatGPT's real connectors,
  macOS and Windows, and the install archives built in CI (billing-locked).

## Self-improvement (optional)

The last question of the companion: *"Turn on self-improvement?"*. On yes (`machine-god improve enable`) four hooks are added to your
Claude Code settings (`~/.claude/settings.json`, a backup is written next to it; your other hooks stay). From then on:

1. **Capture**: every tool call and its outcome is recorded (secrets redacted, size capped), one task per prompt.
2. **Reflect**: after a task ends, at most once per interval and in the background, the AI you use is asked what went well, what failed
   and what to do better next time. Repeated failures of the same tool (3 or more) become their own lesson.
3. **Learn**: lessons are deduplicated, reinforced when they come back, fade when unused, and contradicting lessons are both kept and flagged.
   Every change is versioned: `machine-god improve versions`, `machine-god improve rollback <v>`.
4. **Use**: on each new prompt the few most relevant lessons are added as context (at most 800 characters, labelled as data, not commands).
5. **Code changes are never applied on their own.** A reflection may propose one; it waits in `machine-god improve proposals` until you
   type yes in a terminal (`machine-god improve apply <id>`). Then a backup is made, the change applied inside the install folder only,
   its test run, and everything restored if the test fails. `revert <id>` undoes it later.

`machine-god improve status` shows what was captured and whether the success rate actually changes (it says "insufficient data" until there is enough).
Once the GRID created `unified.db`, reflection is stored there too (tables `mgr_*`), so it is the same memory. `machine-god improve disable` removes the hooks; data stays.

Honest limits: tested on Linux with a dry backend and test payloads; a real reflection round with a logged-in Claude, Ollama or Gemini,
the hooks inside a live Claude Code session, macOS and Windows are not tested yet. Redaction is pattern based (best effort).
