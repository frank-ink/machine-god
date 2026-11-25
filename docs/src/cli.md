# CLI commands and options

Use this reference for launch syntax, option lifetimes, completions and local manuals. For a guided introduction, start with [Your first session](usage.md). Commands here run in your shell; [slash commands](commands.md) run inside the app.

## Start a session

Start a new session in the current directory:

```bash
machine-god
```

Start with an initial prompt:

```bash
machine-god "Explain this project"
```

The prompt is sent automatically after project trust, startup dialogs, and session selection are complete. The TUI stays open for follow-up messages.

Start in a specific working directory:

```bash
machine-god -C path/to/project
```

## Resume or continue

Resume a previous session:

```bash
machine-god resume
```

Resume by session id:

```bash
machine-god resume <session_id>
```

The Claude-style flags use the same resume workflow:

```bash
machine-god --resume
machine-god -r <session_id> "Continue reviewing the changes"
machine-god --continue
machine-god -c "Finish the review"
```

`--resume` without an ID opens the session picker. `--continue` selects the most recently modified SDK-visible session for the working directory, including its git worktrees; this includes sessions created by `machine-god`. If no session exists, it starts a new one. Resume accepts session IDs; name and transcript-path lookup are not supported. Use `--resume=<session_id>` to make the ID boundary explicit, or `--resume -- "prompt"` to open the picker with an initial prompt. `--resume`, `--continue`, and the `resume` subcommand cannot be combined.

## Initial session choices

Choose how the initial session starts:

Use models and agents available to your account and project. The `reviewer` name below is an example of a configured agent; `/docs agents` shows the current session's choices.

```bash
machine-god --model opus --effort high --permission-mode plan "Review this project"
machine-god --agent reviewer "Review the current changes"
machine-god resume <session_id> --model sonnet --effort medium
```

`--model`, `--effort`, `--permission-mode`, and `--agent` apply to the initial new or resumed session before its first prompt. They do not write saved preferences. Later sessions started inside the TUI use saved settings. Model aliases, full model IDs, agent names, and model-specific effort availability are resolved by the SDK. Effort values are `low`, `medium`, `high`, `xhigh`, and `max`; `max` is a session-only override. Permission modes are `default`, `auto`, `acceptEdits`, `plan`, `dontAsk`, and `bypassPermissions`.

## Name or fork a session

Name the session as you start it, or branch from an existing one:

```bash
machine-god -n "Release prep"
machine-god --continue --name "Release prep, day two"
machine-god --continue --fork-session --name "Experiment"
```

`-n, --name` names a new session or renames the session being resumed or continued. A new or forked session takes the name as its title, and the SDK reports a new session's title after its first turn. A resumed session is renamed once it has connected, through the same SDK rename as the Status tab, so a resume that fails to start, or that asks you to sign in, leaves its saved title unchanged; a rename that fails is shown as an error and the resumed session stays open. Control characters are removed and a name with no visible characters is rejected. `--fork-session` resumes under a new session ID and leaves the original conversation and its title unchanged; it requires `--resume`, `--continue` or the `resume` subcommand. With `--continue` and no earlier session in the directory, `--fork-session` has nothing to fork and a plain new session starts. The resume hint after exit shows the new session ID. Both apply to the initial session only.

## Process-wide launch configuration

Add directories, settings, MCP servers and system prompt text for a run. Replace the example paths with existing directories and files:

```bash
machine-god --add-dir ../shared --settings ./settings.json --mcp-config ./mcp.json
machine-god --settings '{"cleanupPeriodDays": 7}' --strict-mcp-config --mcp-config ./mcp.json
machine-god --system-prompt-file ./release-bot.md --append-system-prompt "Answer in German."
```

- `--add-dir <PATH>` gives Claude access to a directory beyond the working directory; repeat it for more.
- `--settings <JSON_OR_FILE>` takes a JSON object inline (a value starting with `{`) or the path of a JSON file. It becomes the SDK's flag-settings layer, which outranks the user, project and local settings files; managed policy still outranks it. The layer reaches SDK behaviour only: `machine-god`'s own interface preferences (tips, notifications, time format, auto-scroll) are read from the saved settings files, so putting them in `--settings` does nothing. Explicit launch options such as `--model` are applied as SDK options of their own. `machine-god` lays two host restrictions over this layer: `feedbackDrafts` is always `off`, and `crossSessionInbound` is `refuse` unless the value in effect, from this layer or else the saved settings, is `accept` or `refuse`. Draft review and held peer-message review need surfaces `machine-god` does not have.
- `--mcp-config <JSON_OR_FILE>` takes the same inline-or-file form, with an object that contains `mcpServers`, and can be repeated. Servers are merged in command-line order, and a later server replaces an earlier one of the same name. The SDK validates each server definition. `--strict-mcp-config` restricts the session to the servers supplied this way, ignoring project `.mcp.json`, user settings, plugins and agent definitions; without any `--mcp-config` it starts the session with no MCP servers.
- `--system-prompt <TEXT>` or `--system-prompt-file <PATH>` replaces the default system prompt, and `--append-system-prompt <TEXT>` or `--append-system-prompt-file <PATH>` appends instructions to it. The text and file spellings of each option cannot be combined, and an empty prompt, inline or in a file, is rejected. `machine-god` keeps one instruction of its own in every system prompt, which tells Claude not to stop the bridge runtime process: appended text follows it, and a replacement prompt is followed by it.

Relative paths resolve against `--dir`, or the current directory without it. Everything is read and checked before logging, the bridge or the terminal starts: a missing directory, an unreadable or empty file, invalid JSON or an MCP config without `mcpServers` stops the launch with an error that names the flag, and nothing is renamed, written or started. Files are read once at startup, so later edits do not reach a running session. None of these flags write saved preferences, and the Config window shows the saved settings files, not the `--settings` layer.

The configuration flags in this section stay in effect for every session the process starts, including `/new-session`, sessions opened with `/resume` and a new session after login. The SDK records a conversation's system prompt on its first request where recording is enabled; a resumed or continued session then keeps the recorded prompt and ignores a different one, until compaction or a new session. Launch flags apply to interactive launches and cannot be combined with support commands.

## Argument and path validation

An initial prompt whose text matches a subcommand name can be passed after `--`, for example `machine-god -- "doctor"`. Startup arguments cannot be combined with support commands such as `doctor`, `logs`, `config`, or `completions`.

`--dir` and `--bridge-script` are checked before the terminal, trust prompt, or bridge start. A missing path, a file where a directory is expected, a directory where the script is expected, a path behind a directory that cannot be searched, a directory without read or search (execute) permission, or a script that cannot be read prints an error naming the flag and exits with status 2. Nothing is saved. Support commands do not refuse them: `machine-god --bridge-script <PATH> doctor` reports the same bridge script problem as a failed check instead.

A relative `--dir` is resolved against the current directory to its absolute path, with `.` and `..` resolved (following symlinks on Unix, lexically on Windows), before it is used for the session, shown as `Loc:`, or read by `config` and `doctor`. An absolute `--dir` is used as given. `machine-god --dir .` shows and uses the current directory's path, not `.`.

After the TUI exits, the app prints a resume hint whenever a session was established, using the active or most recently established session id.

## CLI Options

The installed `machine-god --help` command exposes these options:

Use `-h` or `--help` for help and `-V` or `--version` for the installed version. `machine-god help <command>` shows a subcommand's help.

| Option | Purpose |
| --- | --- |
| `-r, --resume [ID]` | Resume by session ID, or open the picker without an ID. |
| `-c, --continue` | Continue the latest session for the working directory and its git worktrees; start new if none exists. |
| `--model <MODEL>` | Set the initial session model without changing saved preferences. |
| `--effort <LEVEL>` | Set the initial session effort; availability depends on the model. |
| `--permission-mode <MODE>` | Set the initial session permission mode without changing saved preferences. |
| `--agent <NAME>` | Select the main-thread agent for the initial session. |
| `-n, --name <TEXT>` | Name a new session, or rename the session being resumed. |
| `--fork-session` | Resume under a new session ID, leaving the original unchanged. |
| `--add-dir <PATH>` | Add a directory Claude may access; repeatable. |
| `--settings <JSON_OR_FILE>` | Apply temporary settings as inline JSON or a JSON file. |
| `--mcp-config <JSON_OR_FILE>` | Add MCP servers from inline JSON or a file with an `mcpServers` object; repeatable. |
| `--strict-mcp-config` | Use only the MCP servers from `--mcp-config`. |
| `--system-prompt <TEXT>` | Replace the default system prompt for new sessions. |
| `--system-prompt-file <PATH>` | Read the replacement system prompt from a file. |
| `--append-system-prompt <TEXT>` | Append instructions to the system prompt for new sessions. |
| `--append-system-prompt-file <PATH>` | Read the appended system prompt instructions from a file. |
| `--no-update-check` | Disable startup update checks. |
| `-C, --dir <DIR>` | Run in a specific working directory, which must exist and be readable and searchable. |
| `--bridge-script <PATH>` | Use a specific Agent SDK bridge script, which must be a readable file. |
| `--enable-logs` | Add detailed info-level diagnostics to the always-on warning and error log. |
| `--diagnostics-preset <runtime\|session\|render\|bridge\|full>` | Use a named diagnostics filter. |
| `--log-file <PATH>` | Write tracing diagnostics to a specific file. |
| `--log-filter <FILTER>` | Use explicit tracing filter directives. |
| `--log-append` | Append to an explicit log file; without `--log-file`, use the legacy shared default log. |

See [Diagnostics](diagnostics.md) before enabling verbose logs.

## Support And Diagnostics

Use support commands when you need a repeatable snapshot of the local environment or diagnostic logs.

| Command | Purpose |
| --- | --- |
| `machine-god doctor` | Run installation, runtime, config path, log path, npm metadata, and credential checks. |
| `machine-god doctor --json` | Emit the diagnostics report as JSON. |
| `machine-god logs` | Show diagnostics log locations and useful follow-up commands. |
| `machine-god logs --tail <LINES>` | Print redacted lines from the latest discovered log. |
| `machine-god logs --bundle --yes` | Write a redacted ZIP debug bundle. |
| `machine-god config` | Show resolved config paths and file states. |
| `machine-god config show` | Show a concise redacted config summary. |
| `machine-god config export --output <PATH>` | Write a redacted config export without overwriting existing files. |

See [Diagnostics](diagnostics.md) for command options, logging presets, bundle contents and sharing guidance. These support commands do not open the chat UI.

## Shell Completions

`machine-god completions <shell>` prints a completion script for `bash`, `zsh`, `fish`, `powershell`, or `elvish`. It works with script, npm, archive, and source installations and does not start the bridge or require credentials. All five scripts suggest CLI commands and flags. Bash, Zsh, and Fish also suggest fixed choices such as effort levels; the generated PowerShell and Elvish scripts currently complete command and option names. They do not query live session IDs, model catalogs, or agents. The TUI's slash-command completion is separate.

For PowerShell, enable completions in the current session:

```powershell
machine-god completions powershell | Out-String | Invoke-Expression
```

Put that same line in your PowerShell `$PROFILE` to enable completions in future sessions. For Bash, run the following and add it to `~/.bashrc` for future shells:

```bash
source <(machine-god completions bash)
```

For Zsh, generate the script:

```zsh
mkdir -p ~/.zfunc
machine-god completions zsh > ~/.zfunc/_machine-god
```

Add `fpath=(~/.zfunc $fpath)` to `~/.zshrc` before its completion initialization. If completion is not already initialized, add `autoload -Uz compinit` followed by `compinit` after the `fpath` line.

For Fish:

```fish
mkdir -p ~/.config/fish/completions
machine-god completions fish > ~/.config/fish/completions/machine-god.fish
```

Regenerate scripts saved to disk after upgrading `machine-god`. The PowerShell and Bash startup lines above generate completions from the currently installed binary each time the shell starts.

## Man Pages

A man page is a local command reference opened in a terminal with the Unix `man` viewer.

Unix release archives include generated manuals under `share/man/man1/`, including a root page and pages for visible subcommands. The Unix installer links them into `share/man/man1/` beside the installation's `bin` directory, normally `~/.local/share/man/man1/`. Open the manual with:

```bash
man machine-god
man machine-god-config-show
```

If your man viewer does not search that directory, use `MANPATH="$HOME/.local/share/man:" man machine-god`; the trailing colon preserves its default search paths. Custom `--bin-dir` installations use the corresponding sibling `share/man` directory. Uninstall removes only manual links pointing into the script installation.

For npm, source, or manually extracted installations, generate the pages locally with the packaging command:

```bash
machine-god man ./man-pages
man ./man-pages/machine-god.1
```

The `man` generator is hidden from normal command help because it is primarily a packaging utility. It works on Windows too, although viewing the output requires a Unix-compatible man viewer. Help, completion scripts, and manual pages all derive from the same CLI definitions.
