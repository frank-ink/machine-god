"""ClayCode team core: vault keys (never exposed), NVIDIA NIM chat, ClayCode split and validation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HARNESS = os.path.expanduser("~/omegacv1-ship/harness")
KEYS_ENV = os.path.expanduser("~/.config/frank_vault/keys.env")
KEY_PATHS = (KEYS_ENV, os.path.expanduser("~/.last-resort/keys.env"))
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("CLAYTEAM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
_ROLE_NAMES = ("architekt", "forscher", "bauer", "pruefer", "waechter")
KEYSETS = {  # team A and team B use disjoint keys, so two teams can run in parallel
    "A": dict(zip(_ROLE_NAMES, ["NVIDIA_NIM_API_KEY"] + [f"NVIDIA{i}_API_KEY" for i in range(2, 6)])),
    "B": dict(zip(_ROLE_NAMES, [f"NVIDIA{i}_API_KEY" for i in range(6, 11)])),
}
ROLES = KEYSETS["A"]
_FENCE = re.compile(r"```[A-Za-z]*[ \t]*\n(.*?)```", re.S)


class ChatError(RuntimeError):
    """Raised on API failure; message never contains a key."""


def load_key(name: str, path: str | None = None) -> str:
    for p in ([path] if path else KEY_PATHS):
        v = _scan(name, p)
        if v:
            return v
    raise KeyError(name)  # name only, never a value


def _scan(name: str, path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("export "):
                s = s[7:].lstrip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() != name:
                continue
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            if v:
                return v
    return ""


def key_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _http_post(url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def chat(key: str, messages: list, model: str = DEFAULT_MODEL, max_tokens: int = 14000,
         temperature: float = 0.2, timeout: float = 120, _post=None, _sleep=time.sleep):
    """Return (text, usage, latency_ms). One retry after 10 s on 429/5xx."""
    post = _post or _http_post
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens,
                       "temperature": temperature}).encode()
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
               "Accept": "application/json"}
    t0 = time.perf_counter()
    for attempt in (0, 1):
        try:
            status, raw = post(NIM_URL, body, headers, timeout)
        except Exception as e:  # network errors: report type only
            status, raw = -1, type(e).__name__.encode()
        if status == 200:
            d = json.loads(raw)
            text = d["choices"][0]["message"].get("content") or ""
            return text, d.get("usage", {}), round((time.perf_counter() - t0) * 1000)
        if attempt == 0 and (status == 429 or status >= 500 or status == -1):
            _sleep(10)
            continue
        snippet = raw[:200].decode("utf-8", "replace").replace(key, "<redacted>")
        raise ChatError(f"HTTP {status}: {snippet}")
    raise ChatError("unreachable")


def split_reply(text: str) -> tuple[str, list[str]]:
    """Split a reply into ClayCode and python blocks. A fenced block that parses as ClayCode is ClayCode
    (models often wrap ClayCode in ```python fences); every other fenced block is python."""
    clay_parts, py_blocks = [], []
    for b in _FENCE.findall(text or ""):
        b = b.strip("\n")
        (clay_parts if b.strip() and validate(b)[0] else py_blocks).append(b)
    outside = _FENCE.sub("", text or "").strip()
    clay = "\n".join(x for x in [outside] + clay_parts if x.strip())
    return clay, py_blocks


def validate(clay_text: str) -> tuple[bool, str]:
    if not clay_text or not clay_text.strip():
        return False, "empty ClayCode"
    if HARNESS not in sys.path:
        sys.path.insert(0, HARNESS)
    from understanding import claycheck
    ok, err = claycheck.parse_ok(clay_text)
    return bool(ok), "" if ok else str(err)


GRAMMAR_HINT = (
    "ClayCode grammar (only these line forms are valid; no prose, no markdown outside the allowed python fences):\n"
    "rule NAME = EXPR      e.g. rule pass_if = ci_low >= min_effect\n"
    "needle NAME(args) -> Type   e.g. needle decide_v2(target, guards, min_effect) -> Decision\n"
    "invariant EXPR        e.g. invariant ci_low <= ci_high\n"
    "EXPR may use names, numbers, \"strings\", calls f(a, b), a.b, comparisons, 'or', ->. "
    "There is NO 'and', 'not', 'when', 'if' keyword and NO type annotations inside calls: "
    "write all_of(a, b), negate(a), if_then(cond, x, y) instead."
)


_STMT = re.compile(r"^\s*(rule|needle|invariant)\b")


def salvage(text: str) -> str:
    """Keep only single lines that are valid ClayCode statements on their own (fences included)."""
    keep = [ln.strip() for ln in (text or "").splitlines() if _STMT.match(ln) and validate(ln.strip())[0]]
    return "\n".join(dict.fromkeys(keep))
