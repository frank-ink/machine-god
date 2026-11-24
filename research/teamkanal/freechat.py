#!/usr/bin/env python3
"""freechat.py - team-channel role 'Quittierer' (acknowledger) on any free-pool model. stdin = prompt, stdout = one reply.
No tools, no files: channel text can only produce a text answer. Exit 1 (no output) if the endpoint is not configured or down.
Endpoint via env MG_LLM_URL / MG_LLM_MODEL / MG_LLM_KEY (see ../grid10/freellm.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "grid10"))
import freellm

ROLE = ("ROLE: you are the 'Quittierer' (acknowledger) of a small dev team. Research members coordinate, the team lead builds and measures; "
        "you = receipts only. You cannot run commands. Do not promise results; say what you read, "
        "name the role the request belongs to (lead/builder/tester/measurer), and that the lead will answer. Never invent measurements. "
        "Never claim to have read, checked or verified anything except the message text itself. Plain text, at most 6 lines.")

try:
    body = freellm.chat([{"role": "system", "content": ROLE}, {"role": "user", "content": sys.stdin.read()[:6000]}], max_tokens=160, temperature=0.2, timeout=100).strip()
except Exception:
    sys.exit(1)
if not body:
    sys.exit(1)
print(body + "\n[free-pool model: " + freellm.model() + "]")
