# Interest organ

Gives Machine God interests that grow, fade and change, and lets it choose its own research topics.
Pure Bun (`bun:sqlite`), no npm dependencies.

## How it works

Each interest has weight `w`, novelty `n`, boredom `b` (all in [0,1]), `visits`, `last_visit`,
`origin` (seed | discovered | user) and `status` (active | dormant).

All constants live in one object, `C` in `model.ts`:

| rule | value |
|---|---|
| decay on every load | `w *= exp(-dt/14d)`, `b *= exp(-dt/2d)`; `w < 0.05` -> dormant (kept, revivable) |
| score | `w + 0.3*n - b` |
| choice | softmax(score/0.25) over active interests; with prob 0.15 pick the best-scored *discovered* interest with `visits == 0` |
| after a round (reward r) | `w += 0.3*(r-w)`, `b += 0.35*(1-b)`, `n *= 0.6`, `visits++` |
| discovered subtopic | new interest `w = 0.15 + 0.2*r`, `n = 1`; deduped by lowercased/trimmed/space-collapsed key; max 40 active (lowest score goes dormant) |
| `like` / `dislike` | same update with r=1 / r=0; new topic gets origin `user` |
| seed | `w = 0.5`, `n = 0.5` (existing dormant topic is revived) |

Dormant interests are never picked. They revive via `seed` or `like`. A subtopic that already exists
(active or dormant) is logged as `rediscover` and left unchanged. Every change is written to the `events`
table (`ts, kind, topic, delta`); `history` shows it.

## CLI

```
seed <topic...>      add seeds (one quoted string per topic)
list                 table sorted by score
pick                 choose a topic and print the top 5 probabilities (read-only)
run [--backend claude|chatgpt|dry] [--rounds N]
like <topic> | dislike <topic>
history [N]
reset --yes
```

With no seeds, `run` prints how to seed. No topics are invented.

## Backends

- `claude` (default): runs `claude -p --output-format json "<prompt>"` using your own login. Requires `claude` on PATH.
- `chatgpt`: `POST $MG_CHATGPT_BRIDGE_URL/chatgpt/send {prompt, timeout_s}` with `Authorization: Bearer $MG_CHATGPT_BRIDGE_TOKEN` (see `backend_chatgpt.ts`).
- `dry`: deterministic fake for tests.

The prompt contains only the topic. The model must end with `{"reward":0..1,"subtopics":[max 3]}`.
Malformed output counts as reward 0.3 with no subtopics. The reward is the model's own judgement, so it is
a noisy signal. Subtopics are model output and are length-limited and stripped of control characters.
Notes are saved to `<data dir>/notes/<date>-<slug>.md`.

## Data

`interest.db` in `~/.local/share/machine-god` (macOS `~/Library/Application Support/machine-god`,
Windows `%LOCALAPPDATA%\machine-god`). Override with `MG_DATA_DIR`. `MG_SEED=<int>` makes picks reproducible.

## Tests

`MG_DATA_DIR=$(mktemp -d) bun test` inside this directory.

## Limits

Time decay uses wall-clock time between loads. Reward comes only from the backend's self-report or from
`like`/`dislike`; the organ does not judge note quality itself.
