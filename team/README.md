# Dev team (reference)

Five roles as **model-neutral prompts**: a lead (the main session) plus four members. The files are plain markdown role descriptions
(with a small YAML header); they work with any chat model, including free-pool models.

| Role | File | Task |
|---|---|---|
| Architect | `agents/team-architect.md` | design, interfaces, test plan, failure paths; writes no code |
| Builder | `agents/team-builder.md` | root cause first, then minimal build |
| Reviewer | `agents/team-reviewer.md` | independent review of diff and tests, never one's own work |
| Reviewer+ | `agents/team-reviewer-plus.md` | second review only for non-trivial changes, with a stronger model if one is configured |
| Guardian | `agents/team-guardian.md` | security, secrets, destructive actions, approval gates |

Documents: `TEAM.md` (rules), `GRF-FRAME.md` (eight thinking principles of the Generative Reality Framework as working rules),
`GOAL.md` (metrics and an honest translation of the goal).

## Use with a free-pool model

Any OpenAI-compatible endpoint is enough; there is no provider lock-in.

```bash
export MG_LLM_URL="https://<provider>/v1/chat/completions"   # any OpenAI-compatible endpoint
export MG_LLM_MODEL="<model-id>"
export MG_LLM_KEY="<key>"                                     # environment only, never in a file
echo "Review this diff: ..." | python3 research/grid10/freellm.py --system team/agents/team-reviewer.md
```

`freellm.py` strips the YAML header of the role file and uses the rest as the system prompt. In another tool
(agent harness, chat client) simply paste the text of the role file as the system prompt.

## Notes

- The roles refer to gstack skills (`gstack-plan-eng-review`, `gstack-investigate`, `gstack-review`, `gstack-cso`,
  `gstack-careful`) by **name only** and optionally. gstack is a separate project with its own license and not part of this repo.
- The roles are a way of working, not evidence of performance. `GOAL.md` states explicitly: no AGI indicator is shown as fulfilled.
- Rollback: simply delete the copied files again; the roles write nothing outside their task.
