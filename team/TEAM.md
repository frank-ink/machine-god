# Dev-Team (5): Lead + 4 Members, Claude Code, Thinking Framework team/GRF-FRAME.md
Lead = the main session (FranKenstein): decides, measures, reports to the user; skills: gstack-office-hours (questions/levers). Research is done by the second machine + ChatGPT (channel), not the team.
Architect  team-architect  gstack-plan-eng-review   Design, interfaces, test plan, error paths
Builder      team-builder      gstack-investigate        Root cause first (forensics), then minimal build; Text/Code generation first via Free-Pool
Reviewer     team-reviewer    gstack-review             Diff/Tests independent, looks for what can break; never review own work
Reviewer+    team-reviewer-plus (stronger model, if configured)  only for non-trivial changes, AFTER tests + Free-Review, task with exact paths, report <=9 lines (token-neutral)
Guardian     team-guardian   gstack-cso, gstack-careful Security, secrets, destructive actions, user approval
Rules: Free-Tokens first (one Free-Pool model via an OpenAI-compatible endpoint, see research/grid10/freellm.py), spawn member only when tool/measurement needed; each member reports briefly with evidence (test:<exit>, file:<path>:<sha>). Money/Trading read-only. ship/push/external only with the user.
Teardown: delete the copied files again (see team/README.md)
