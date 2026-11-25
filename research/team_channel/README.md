# Team channel check-in (reference)

A script that reads new messages of a team channel every 10 minutes and writes back exactly one reply.

```
new channel messages --> checkin_free.sh --> freechat.py --> freellm.py --> any OpenAI-compatible endpoint (free pool)
                                  |                 | fails
                                  |                 v
                                  |           TEAM_CHANNEL_FALLBACK_CMD (optional, any model, reads the prompt from stdin)
                                  v
                          reply back via the channel client (secret guardian blocks, error message only once per 60 min)
```

Message format from the client: one JSON object per line with `from`, `ts`, `text`.

Properties:
- Channel text is data: the model runs without tools and without MCP and can only produce text.
- No provider lock-in: endpoint, model and key come from `MG_LLM_URL`, `MG_LLM_MODEL`, `MG_LLM_KEY` (environment).
- Error messages are limited to one per hour so a broken endpoint cannot flood the channel.

```bash
export MG_LLM_URL="https://<provider>/v1/chat/completions" MG_LLM_MODEL="<model-id>" MG_LLM_KEY="<key>"
export TEAM_CHANNEL_CLIENT=/path/to/your/channel_client.py     # your own channel client with count / get --since N / say --from NAME -
bash research/team_channel/checkin_free.sh
```

**Not runnable without** a channel client offering these three subcommands; the client of the originating project is private and not
part of the repo. Names and addresses of the machines involved are removed. The scripts show the pattern, not an installation.

## Rollback (general)

Remove the timer or cron entry and delete the directory of these scripts. Delete the state folder
(`TEAM_CHANNEL_STATE`, default `~/.local/share/team_channel`) as well if needed. Network profiles or firewall rules created for a
repair must be removed with the respective tools of the machine.
