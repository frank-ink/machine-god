#!/usr/bin/env python3
"""secret_pattern.py -- A pattern source for secrets (tokens, passwords, keys).

Shared by:
  1. Write redaction  (star_cli._mem_write, star_cycle, setup)
  2. Retrieval/output filter (star_cli.cmd_hook, star_core.automatic_retrieval)
  3. Cleanup          (star_cli.py secret-redact --dry-run|--apply)

Rules: This file never outputs a secret value. Count only by type.
Extensible: append new entry to PATTERNS (type, regex, value_group).
value_group = group that gets replaced (0 = entire match).
"""
import math
import re
from collections import Counter

REDACT_FMT = "[REDACTED:{}]"

_B = r"(?<![A-Za-z0-9])"  # no word character before

# Words that are NOT a secret when they appear as the "value" after a password keyword (meta statements). German language data: kept in German on purpose.
# lang-data:de begin
_STOP = {
    "nicht", "kein", "keine", "keins", "keiner", "nie", "niemals", "unbekannt", "leer", "none",
    "null", "nil", "true", "false", "ja", "nein", "gesetzt", "vorhanden", "falsch", "richtig",
    "falsche", "falscher", "falsches", "korrekt", "gespeichert", "geaendert", "geändert", "noetig",
    "nötig", "erforderlich", "required", "optional", "wrong", "correct", "empty", "unknown",
    "hier", "dort", "und", "oder", "der", "die", "das", "ein", "eine", "wie", "was", "wo", "im",
    "in", "auf", "fuer", "für", "von", "mit", "ohne", "bei", "zu", "the", "a", "an", "is", "not",
    "no", "or", "and", "for", "of", "to", "set", "changed", "stored", "saved", "hash", "hashed",
    "abgefragt", "abgelehnt", "gesperrt", "abgelaufen", "expired", "invalid", "ungueltig",
    "ungültig", "gueltig", "gültig", "geheim", "secret", "xxx", "xxxx", "xxxxx", "todo", "tbd",
    "redacted", "wird", "werden", "bleibt", "steht", "stehen", "liegt", "liegen", "lautet",
    "sollte", "muss", "kann", "darf", "braucht", "benoetigt", "benötigt",
}
# lang-data:de end

_VAL = r"([^\s\"'`,;<>(){}\[\]\\|]{4,})"  # Value token (no quotes/brackets/backslash)

# (kind, regex, value_group)
PATTERNS = [
    ("runpod", re.compile(_B + r"(rpa_[A-Za-z0-9]{20,})"), 1),
    ("github", re.compile(_B + r"((?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,})"), 1),
    ("github", re.compile(_B + r"(github_pat_[A-Za-z0-9_]{30,})"), 1),
    ("anthropic-openai", re.compile(_B + r"(sk-(?:ant-|proj-|svcacct-)?[A-Za-z0-9_\-]{20,})"), 1),
    ("groq", re.compile(_B + r"(gsk_[A-Za-z0-9]{20,})"), 1),
    ("nvidia", re.compile(_B + r"(nvapi-[A-Za-z0-9_\-]{20,})"), 1),
    ("google", re.compile(_B + r"(AIza[0-9A-Za-z_\-]{35})"), 1),
    ("slack", re.compile(_B + r"(xox[abposr]-[A-Za-z0-9\-]{10,})"), 1),
    ("aws", re.compile(_B + r"((?:AKIA|ASIA)[0-9A-Z]{16})(?![A-Za-z0-9])"), 1),
    ("jwt", re.compile(_B + r"(eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})"), 1),
    ("pem", re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----.*?-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----)", re.S), 1),
    ("pem", re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----[A-Za-z0-9+/=\\n\s]{40,})"), 1),
    ("bearer", re.compile(r"(?i)\b(?:authorization\s*[:=]\s*)?bearer\s+([A-Za-z0-9._~+/\-]{16,}=*)"), 1),
    ("auth-header", re.compile(r"(?i)\bauthorization\s*[:=]\s*(?:basic|token)\s+([A-Za-z0-9._~+/\-]{8,}=*)"), 1),
    # NAME_API_KEY=value / NAME_TOKEN: value (env lines)
    ("env-key", re.compile(
        r"\b[A-Za-z][A-Za-z0-9_]*(?:API_?KEY|SECRET(?:_KEY)?|TOKEN|PASSWORD|PASSWD|ACCESS_KEY|PRIVATE_KEY|AUTH_KEY)\b"
        r"\s*[=:]\s*[\"']?([^\s\"'`,;<>(){}\[\]\\|$]{6,})", re.I), 1),
    # key=... in URLs
    ("url-key", re.compile(
        r"[?&](?:api_?key|apikey|key|token|access_token|auth|secret|password|passwd|pwd)=([^&\s\"'`<>]{6,})", re.I), 1),
    # lang-data:de begin (German password keywords: passwort/kennwort/lautet are matched in German user text)
    # Passwort-Schluesselwort + Trenner (:, =) + Wert (auch JSON "password": "wert")
    ("passwort", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|passwoerter|password|passwd|pwd|kennwort)[\"'`]?\s*[:=]\s*[\"'`]?" + _VAL), 1),
    # "Passwort <wert>" (nur Leerraum) -- streng: Wert braucht Ziffer/Symbol oder Gross+Klein, >=8
    ("passwort-ist", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|password|passwd|pwd|kennwort)[ \t]+[\"'`]?" + _VAL), 1),
    # "Passwort ist <wert>" -- strenger: Wert muss Ziffer/Symbol enthalten (Prosa-Schutz)
    ("passwort-ist", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|password|passwd|pwd|kennwort)\s+(?:ist|lautet|is)\s*:?\s*[\"'`]?" + _VAL), 1),
    # lang-data:de end
]

# High-entropy token next to token/key/secret (cautious)
_HE_CTX = re.compile(r"(?i)(?:token|key|secret|apikey|bearer)")
_HE_TOK = re.compile(r"(?<![A-Za-z0-9+/_\-])([A-Za-z0-9+/_\-]{32,})(?![A-Za-z0-9+/_\-])")


def _entropy(s: str) -> float:
    c = Counter(s)
    n = len(s)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def _is_placeholder(v: str) -> bool:
    lv = v.lower()
    return (
        lv.startswith("[redacted")
        or lv.startswith("$")
        or lv.startswith("%")
        or lv.startswith("<")
        or lv.startswith("{")
        or "redacted" in lv
        or lv.startswith(("os.environ", "getenv", "environ", "process.env", "args.", "self."))
        or set(lv) <= set("x*.-_#•")
        or lv.strip(".,:!?)") in _STOP
    )


def _value_ok(kind: str, v: str) -> bool:
    if _is_placeholder(v):
        return False
    if kind in ("password", "password-is"):
        if v[0] in "&/~." or re.fullmatch(r"[a-z]+(?:_[a-z]+)+", v) or v.lower().startswith(("getpass", "input", "prompt")):
            return False  # Path, HTML entity, code identifier
    if kind in ("password", "password-is", "env-key", "url-key"):
        core = v.strip(".,:!?)")
        if core.lower() in _STOP:
            return False
        if kind == "password-is":
            # Prose protection: digit or symbol required
            if not (re.search(r"[0-9!@#$%^&*_+=~/\\]", core)
                    or (re.search(r"[a-z]", core) and re.search(r"[A-Z]", core) and len(core) >= 8)):
                return False
        if kind in ("env-key", "url-key") and re.fullmatch(r"[A-Za-z_]+", core) and len(core) < 12:
            return False  # Name instead of value (e.g. TOKEN=value_name)
    return True


def _spans(text: str):
    """Returns list (start, end, type) of all value ranges to be redacted (non-overlapping)."""
    if not text:
        return []
    found = []
    for kind, rx, g in PATTERNS:
        for m in rx.finditer(text):
            if not _value_ok(kind, m.group(g)):
                continue
            found.append((m.start(g), m.end(g), kind))
    # High-entropy next to context word
    for m in _HE_TOK.finditer(text):
        tok = m.group(1)
        if tok.lower().startswith("redacted"):
            continue
        if not (re.search(r"[a-z]", tok) and re.search(r"[A-Z]", tok) and re.search(r"[0-9]", tok)):
            continue
        if re.fullmatch(r"[0-9a-fA-F]+", tok):
            continue
        if "/" in tok and tok.count("/") >= 2:
            continue  # Path
        if _entropy(tok) < 4.0:
            continue
        segs = [x for x in re.split(r"[-_]", tok) if x]
        if len(segs) >= 3 and sum(x.isalpha() for x in segs) * 2 >= len(segs):
            continue  # Identifier/model name, not a token
        a = max(0, m.start(1) - 40)
        ctx = text[a:m.start(1)] + " " + text[m.end(1):m.end(1) + 20]
        if _HE_CTX.search(ctx):
            found.append((m.start(1), m.end(1), "high_entropy"))
    found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    out, last = [], -1
    for s, e, kind in found:
        if s >= last:
            out.append((s, e, kind))
            last = e
        elif e > last:  # partial overlap: extend
            ps, pe, pa = out[-1]
            out[-1] = (ps, e, pa)
            last = e
    return out


def redact(text):
    """-> (new_text, Counter type->count). Idempotent. Non-str unchanged."""
    if not isinstance(text, str) or not text:
        return text, Counter()
    sp = _spans(text)
    if not sp:
        return text, Counter()
    cnt = Counter()
    buf, pos = [], 0
    for s, e, kind in sp:
        buf.append(text[pos:s])
        buf.append(REDACT_FMT.format(kind))
        cnt[kind] += 1
        pos = e
    buf.append(text[pos:])
    return "".join(buf), cnt


def scan(text) -> Counter:
    return redact(text)[1]


def contains_secret(text) -> bool:
    return bool(isinstance(text, str) and _spans(text))


def redact_obj(o):
    """Recursively iterate over dict/list/str (for _mem_write)."""
    if isinstance(o, str):
        return redact(o)[0]
    if isinstance(o, dict):
        return {redact(k)[0] if isinstance(k, str) else k: redact_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_obj(v) for v in o]
    if isinstance(o, tuple):
        return tuple(redact_obj(v) for v in o)
    return o


def filter_output(text):
    """Retrieval/output filter: any line with a secret pattern is replaced by a notice
    (not just redacted -- no next match is output)."""
    if not isinstance(text, str) or not text:
        return text
    if not _spans(text):
        return text
    # PEM blocks multi-line: first redact, then check line by line
    text = redact(text)[0] if any(a == "pem" for _, _, a in _spans(text)) else text
    out = []
    for line in text.split("\n"):
        if _spans(line):
            lead = line[: len(line) - len(line.lstrip())]
            out.append(f"{lead}[Line suppressed: secret pattern]")
        else:
            out.append(line)
    return "\n".join(out)
