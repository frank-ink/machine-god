# Integration

## 1. Archive files (repo path `interest/`)

Ship these in the install archive, runtime files only:

```
interest/model.ts
interest/store.ts
interest/research.ts
interest/backend_chatgpt.ts
interest/cli.ts
interest/README.md
```

Tests (`interest/interest.test.ts`) stay in the repo and need not ship.

## 2. Launcher subcommand

`machine-god interests <args>` must run the shipped bun against `cli.ts`:

```sh
# POSIX launcher
exec "$MG_HOME/bin/machine-god-bridge-bun" "$MG_HOME/interest/cli.ts" "$@"
```

```bat
:: Windows launcher
"%MG_HOME%\bin\machine-god-bridge-bun.exe" "%MG_HOME%\interest\cli.ts" %*
```

In the launcher's dispatch: `interests) shift; <the line above> ;;`. Exit code is passed through
(0 ok, 1 usage / no seeds, 2 backend failure). Adjust the bun path to however the install names it.

## 3. Wiring to the agent

- Autonomous topic choice: call `machine-god interests pick` (read-only) to see the choice, or schedule
  `machine-god interests run --rounds 1` (backend `claude` by default) to pick, research and record in one go.
- ChatGPT backend: export `MG_CHATGPT_BRIDGE_URL` and `MG_CHATGPT_BRIDGE_TOKEN` when the bridge is running,
  then `--backend chatgpt`. Contract assumed: `POST /chatgpt/send {prompt, timeout_s}` returns JSON with the
  answer in `text`, `reply`, `response` or `result` (or plain text). Adjust only `backend_chatgpt.ts` if it differs.
- No seeds ship by default. First run tells the user to `machine-god interests seed "..."`.

## 4. Checks after integrating

```sh
export MG_DATA_DIR=$(mktemp -d)
machine-god interests seed "a" "b"
machine-god interests run --backend dry --rounds 5
machine-god interests list && machine-god interests history
```

Rollback: remove the six files and the launcher case. User data is only `interest.db` and `notes/`
in the data dir; nothing else is touched.
