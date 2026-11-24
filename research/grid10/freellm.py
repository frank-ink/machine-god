#!/usr/bin/env python3
"""freellm.py -- provider-neutral chat call for any OpenAI-compatible endpoint (free-pool models, local servers). Stdlib only.

Env:  MG_LLM_URL    full chat-completions URL, e.g. https://<provider>/v1/chat/completions
      MG_LLM_MODEL  model id of that provider
      MG_LLM_KEY    optional bearer token; read from the environment only, never written or logged
CLI:  python3 freellm.py [--system ROLE.md] [--max N] < prompt     (a leading YAML header of the role file is stripped)
Nothing here is tied to one provider. Without MG_LLM_URL/MG_LLM_MODEL every call raises, so callers fail loudly instead of guessing."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request


def model():
    return os.environ.get("MG_LLM_MODEL", "")


def configured():
    return bool(os.environ.get("MG_LLM_URL") and model())


def _post(body, timeout):
    headers = {"Content-Type": "application/json"}
    if os.environ.get("MG_LLM_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["MG_LLM_KEY"]
    req = urllib.request.Request(os.environ["MG_LLM_URL"], json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def chat(messages, max_tokens=450, temperature=0, schema=None, timeout=120):
    """-> reply text. With `schema` a strict json_schema is requested first; providers that reject it (HTTP 400/422) get a plain call."""
    if not configured():
        raise RuntimeError("MG_LLM_URL / MG_LLM_MODEL not set")
    body = {"model": model(), "temperature": temperature, "max_tokens": max_tokens, "messages": messages}
    if schema:
        rf = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
        try:
            return _post({**body, "response_format": rf}, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise
    return _post(body, timeout)


def load_role(path):
    text = open(path, encoding="utf-8").read()
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", help="role file used as system prompt")
    ap.add_argument("--max", type=int, default=450)
    a = ap.parse_args()
    msgs = ([{"role": "system", "content": load_role(a.system)}] if a.system else []) + [{"role": "user", "content": sys.stdin.read()}]
    try:
        print(chat(msgs, max_tokens=a.max))
    except Exception as e:
        print("freellm: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
