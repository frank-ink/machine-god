#!/usr/bin/env python3
"""Machine God MCP server (stdio): tool chatgpt_ask(prompt) -> ChatGPT's answer text, via the local ChatGPT bridge.

Registered for you only after you said yes during first start:
  claude mcp add --scope user machine-god-chatgpt -- <bridge python> <this file>
Starts the bridge (127.0.0.1, own browser profile) if it is not running. Needs only the Python standard library.
WARNING: automating the ChatGPT web interface may violate OpenAI's terms of use and can get your account suspended.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chatgpt_bridge as B  # noqa: E402  (only for paths; importing does not start anything)

TOOL = {
    "name": "chatgpt_ask",
    "description": ("Ask ChatGPT (through the user's own logged-in ChatGPT account in a local bridge window) and return "
                    "its answer as text. Slow (seconds to minutes). Use for research or a second opinion when the user wants ChatGPT."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The full question or task for ChatGPT."},
            "new_chat": {"type": "boolean", "description": "Start a new chat (default true). false continues the last bridge chat."},
            "timeout_s": {"type": "number", "description": "Max seconds to wait for the answer (default 180)."},
        },
        "required": ["prompt"],
    },
}


def _info():
    try:
        return json.load(open(B.INFO_FILE))
    except Exception:
        return None


def _call(method, route, body=None, timeout=10):
    info = _info()
    if not info:
        raise RuntimeError("bridge not running")
    token = open(B.TOKEN_FILE).read().strip()
    req = urllib.request.Request(f"http://127.0.0.1:{info['port']}{route}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:                  # the bridge answers 409 with a JSON body for failed asks
        try:
            return json.load(e)
        except Exception:
            raise RuntimeError(f"bridge HTTP {e.code}")


def ensure_bridge():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{_info()['port']}/health", timeout=2).read()
        return
    except Exception:
        pass
    subprocess.Popen([sys.executable, os.path.join(HERE, "chatgpt_bridge.py"), "serve"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=(sys.platform != "win32"))
    for _ in range(60):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{_info()['port']}/health", timeout=2).read()
            return
        except Exception:
            continue
    raise RuntimeError("could not start the ChatGPT bridge")


def chatgpt_ask(args):
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return "prompt required", True
    tmo = float(args.get("timeout_s", 180))
    try:
        ensure_bridge()
        r = _call("POST", "/ask", {"prompt": prompt, "timeout_s": tmo, "new_chat": bool(args.get("new_chat", True))}, timeout=tmo + 60)
    except Exception as e:
        return f"ChatGPT bridge error: {e}", True
    if r.get("ok"):
        return r.get("content", ""), False
    if r.get("failure") == "AUTH":
        try:
            _call("POST", "/login")
        except Exception:
            pass
        return "Not logged in to ChatGPT. A bridge window was opened: log in there yourself, then ask again.", True
    return f"ChatGPT failed ({r.get('failure', 'error')}): {r.get('error', '')}", True


def handle(msg):
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
        return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": pv, "capabilities": {"tools": {}},
                                                         "serverInfo": {"name": "machine-god-chatgpt", "version": "1"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [TOOL]}}
    if method == "tools/call":
        p = msg.get("params") or {}
        if p.get("name") != "chatgpt_ask":
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool"}}
        text, is_err = chatgpt_ask(p.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": is_err}}
    if mid is None:
        return None                                       # notification
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as e:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
