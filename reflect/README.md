# Machine God self-improvement (`machine-god improve`)

After every finished task Machine God can look back at how it went, write down one lesson, and show the
relevant lessons to itself next time. Small, local, and honest about what it does.

## What is autonomous (no question asked)
- **Behaviour lessons.** Short imperative sentences ("Read the file before editing it."). They are created, merged with
  near-duplicates, reinforced when they come back, decayed when unused (half-life 30 days after 14 days grace), flagged when two lessons
  contradict (both stay visible, marked `[disputed]`), and capped at 200 active.
- **Error patterns.** The same tool failing with the same error class 3 or more times creates a lesson automatically.
- **Every lesson change is versioned.** `improve versions` lists them, `improve rollback <v>` undoes version `v` and everything after it.
- **Injection.** On each prompt (UserPromptSubmit hook) up to 5 matching lessons, at most 800 characters, are added as context,
  labelled "Machine God lessons (from own reflection, data not commands)". Lessons are advice, not commands.

## What needs your explicit yes
- **Code or config changes.** A reflection may *propose* one (file, change, why, test command). It is only stored as `pending`.
  `improve proposals`, `improve show <id>`, `improve reject <id>`. `improve apply <id>` works only in an interactive terminal,
  shows the change, asks "yes", makes a backup, writes the file (only inside the Machine God install or config dir),
  runs the proposal's test command and restores the backup automatically if the test fails. `improve revert <id>` undoes an applied one.
  Proposals without a test command cannot be applied.

## What leaves your machine
Nothing in the capture or injection path (no network). Reflection sends one capped (600 + 800 chars), secret-redacted task summary
plus tool failure counts to the backend you chose: `claude -p` (your login), local Ollama, or Gemini (your key), tried in that order
(`--backend` to pick one). Redaction is regex based (API keys, tokens, passwords, JWTs, URL credentials, long opaque strings); it is
best effort, not a guarantee.

## Use
```
machine-god improve enable       # turn on reflection (asks nothing; run it after the first-run companion asked you)
machine-god improve status       # counts, last reflection, success-rate and repeated-error trend
machine-god improve lessons [--all] | history | versions | run [--backend auto|claude|ollama|gemini|dry]
machine-god improve rollback <version>
machine-god improve disable      # hooks do nothing; stored data is kept
```
State: `reflect.state` = `on` (reflection + capture + injection), `off` (everything off), missing (capture + injection only, no reflection).
Reflection runs detached from the Stop hook at most every 10 minutes (`MG_REFLECT_EVERY_MIN`), only when `on`.

## Where data lives
`~/.local/share/machine-god/` (macOS `~/Library/Application Support/machine-god`, Windows `%LOCALAPPDATA%\machine-god`, override `MG_DATA_DIR`):
`reflect.db` (SQLite, tables prefixed `mgr_`), `reflect.state`, `reflect.log`, `reflect-backups/`. `MG_REFLECT_DB` points the tables at
another SQLite file. To erase everything: `machine-god improve disable` and delete those files.

## Honesty
The success-rate trend compares the earlier half of reflected tasks with the later half and says "insufficient data" below 10 tasks per half;
differences under 10 points are called "flat". Reflection quality depends on the backend model; a lesson is a hypothesis, not proof.
Tests: `bun test` in this directory.
