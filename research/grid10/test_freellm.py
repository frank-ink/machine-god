"""Tests freellm.py against a throwaway local OpenAI-compatible stub (no network, no key). Run: python3 test_freellm.py (exit 0 = green)."""
import http.server
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import freellm

SEEN = []


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.headers.get("Authorization"), body))
        if "response_format" in body and os.environ.get("STUB_REJECT_SCHEMA"):
            self.send_response(400)
            self.end_headers()
            return
        out = json.dumps({"choices": [{"message": {"content": "hallo"}}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
for k in ("MG_LLM_URL", "MG_LLM_MODEL", "MG_LLM_KEY"):
    os.environ.pop(k, None)

# 1 unconfigured: loud failure
assert not freellm.configured()
try:
    freellm.chat([{"role": "user", "content": "x"}])
    raise SystemExit("expected RuntimeError")
except RuntimeError:
    pass

# 2 configured: reply, bearer header, model id passed through
os.environ.update(MG_LLM_URL="http://127.0.0.1:%d/v1/chat/completions" % srv.server_address[1], MG_LLM_MODEL="any-free-model", MG_LLM_KEY="k-test")
assert freellm.chat([{"role": "user", "content": "x"}]) == "hallo"
assert SEEN[-1][0] == "Bearer k-test" and SEEN[-1][1]["model"] == "any-free-model"

# 3 schema accepted -> sent; schema rejected (400) -> plain retry without response_format
schema = {"type": "object"}
n = len(SEEN)
assert freellm.chat([{"role": "user", "content": "x"}], schema=schema) == "hallo" and "response_format" in SEEN[n][1]
os.environ["STUB_REJECT_SCHEMA"] = "1"
n = len(SEEN)
assert freellm.chat([{"role": "user", "content": "x"}], schema=schema) == "hallo"
assert "response_format" in SEEN[n][1] and "response_format" not in SEEN[n + 1][1]

# 4 role file: YAML header stripped
import tempfile
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
    f.write("---\nname: x\n---\nDu bist Pruefer.\n")
assert freellm.load_role(f.name) == "Du bist Pruefer."
os.unlink(f.name)
print("ALLE GRUEN (test_freellm: 4 Faelle)")
