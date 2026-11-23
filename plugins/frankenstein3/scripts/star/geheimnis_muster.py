#!/usr/bin/env python3
"""geheimnis_muster.py -- EINE Mustersatz-Quelle fuer Geheimnisse (Tokens, Passwoerter, Schluessel).

Gemeinsam genutzt von:
  1. Schreib-Schwaerzung  (stern._mem_write, stern_zyklus, einrichtung)
  2. Abruf-/Ausgabefilter (stern.cmd_hook, stern_core.automatischer_abruf)
  3. Bereinigung          (stern.py geheimnis-schwaerzen --dry-run|--apply)

Regeln: Diese Datei gibt NIE einen Geheimniswert aus. Zaehlung nur je Art.
Erweiterbar: neuen Eintrag in PATTERNS anhaengen (art, regex, value_group).
value_group = Gruppe, die ersetzt wird (0 = ganzer Treffer).
"""
import math
import re
from collections import Counter

REDACT_FMT = "[REDACTED:{}]"

_B = r"(?<![A-Za-z0-9])"  # kein Wortzeichen davor

# Woerter, die als "Wert" hinter Passwort-Schluesselwort KEIN Geheimnis sind (Meta-Aussagen).
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

_VAL = r"([^\s\"'`,;<>(){}\[\]\\|]{4,})"  # Wert-Token (keine Quotes/Klammern/Backslash)

# (art, regex, value_group)
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
    # NAME_API_KEY=wert / NAME_TOKEN: wert (Env-Zeilen)
    ("env-key", re.compile(
        r"\b[A-Za-z][A-Za-z0-9_]*(?:API_?KEY|SECRET(?:_KEY)?|TOKEN|PASSWORD|PASSWD|ACCESS_KEY|PRIVATE_KEY|AUTH_KEY)\b"
        r"\s*[=:]\s*[\"']?([^\s\"'`,;<>(){}\[\]\\|$]{6,})", re.I), 1),
    # key=... in URLs
    ("url-key", re.compile(
        r"[?&](?:api_?key|apikey|key|token|access_token|auth|secret|password|passwd|pwd)=([^&\s\"'`<>]{6,})", re.I), 1),
    # Passwort-Schluesselwort + Trenner (:, =) + Wert (auch JSON "password": "wert")
    ("passwort", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|passwoerter|password|passwd|pwd|kennwort)[\"'`]?\s*[:=]\s*[\"'`]?" + _VAL), 1),
    # "Passwort <wert>" (nur Leerraum) -- streng: Wert braucht Ziffer/Symbol oder Gross+Klein, >=8
    ("passwort-ist", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|password|passwd|pwd|kennwort)[ \t]+[\"'`]?" + _VAL), 1),
    # "Passwort ist <wert>" -- strenger: Wert muss Ziffer/Symbol enthalten (Prosa-Schutz)
    ("passwort-ist", re.compile(
        r"(?i)(?<![A-Za-z0-9$])(?:passwort|password|passwd|pwd|kennwort)\s+(?:ist|lautet|is)\s*:?\s*[\"'`]?" + _VAL), 1),
]

# Hochentropie-Token neben token/key/secret (vorsichtig)
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


def _value_ok(art: str, v: str) -> bool:
    if _is_placeholder(v):
        return False
    if art in ("passwort", "passwort-ist"):
        if v[0] in "&/~." or re.fullmatch(r"[a-z]+(?:_[a-z]+)+", v) or v.lower().startswith(("getpass", "input", "prompt")):
            return False  # Pfad, HTML-Entity, Code-Bezeichner
    if art in ("passwort", "passwort-ist", "env-key", "url-key"):
        core = v.strip(".,:!?)")
        if core.lower() in _STOP:
            return False
        if art == "passwort-ist":
            # Prosa-Schutz: Ziffer oder Symbol noetig
            if not (re.search(r"[0-9!@#$%^&*_+=~/\\]", core)
                    or (re.search(r"[a-z]", core) and re.search(r"[A-Z]", core) and len(core) >= 8)):
                return False
        if art in ("env-key", "url-key") and re.fullmatch(r"[A-Za-z_]+", core) and len(core) < 12:
            return False  # Name statt Wert (z.B. TOKEN=value_name)
    return True


def _spans(text: str):
    """Liefert Liste (start, end, art) aller zu schwaerzenden Wertbereiche (ueberlappungsfrei)."""
    if not text:
        return []
    found = []
    for art, rx, g in PATTERNS:
        for m in rx.finditer(text):
            if not _value_ok(art, m.group(g)):
                continue
            found.append((m.start(g), m.end(g), art))
    # Hochentropie neben Kontextwort
    for m in _HE_TOK.finditer(text):
        tok = m.group(1)
        if tok.lower().startswith("redacted"):
            continue
        if not (re.search(r"[a-z]", tok) and re.search(r"[A-Z]", tok) and re.search(r"[0-9]", tok)):
            continue
        if re.fullmatch(r"[0-9a-fA-F]+", tok):
            continue
        if "/" in tok and tok.count("/") >= 2:
            continue  # Pfad
        if _entropy(tok) < 4.0:
            continue
        segs = [x for x in re.split(r"[-_]", tok) if x]
        if len(segs) >= 3 and sum(x.isalpha() for x in segs) * 2 >= len(segs):
            continue  # Bezeichner/Modellname, kein Token
        a = max(0, m.start(1) - 40)
        ctx = text[a:m.start(1)] + " " + text[m.end(1):m.end(1) + 20]
        if _HE_CTX.search(ctx):
            found.append((m.start(1), m.end(1), "hochentropie"))
    found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    out, last = [], -1
    for s, e, art in found:
        if s >= last:
            out.append((s, e, art))
            last = e
        elif e > last:  # teilweise Ueberlappung: erweitern
            ps, pe, pa = out[-1]
            out[-1] = (ps, e, pa)
            last = e
    return out


def redact(text):
    """-> (neuer_text, Counter art->anzahl). Idempotent. Nicht-str unveraendert."""
    if not isinstance(text, str) or not text:
        return text, Counter()
    sp = _spans(text)
    if not sp:
        return text, Counter()
    cnt = Counter()
    buf, pos = [], 0
    for s, e, art in sp:
        buf.append(text[pos:s])
        buf.append(REDACT_FMT.format(art))
        cnt[art] += 1
        pos = e
    buf.append(text[pos:])
    return "".join(buf), cnt


def scan(text) -> Counter:
    return redact(text)[1]


def contains_secret(text) -> bool:
    return bool(isinstance(text, str) and _spans(text))


def redact_obj(o):
    """Rekursiv ueber dict/list/str (fuer _mem_write)."""
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
    """Abruf-/Ausgabefilter: jede Zeile mit Geheimnismuster wird durch Hinweis ersetzt
    (nicht nur geschwaerzt -- nichts Treffer-Naechstes wird ausgegeben)."""
    if not isinstance(text, str) or not text:
        return text
    if not _spans(text):
        return text
    # PEM-Bloecke mehrzeilig: erst schwaerzen, dann zeilenweise pruefen
    text = redact(text)[0] if any(a == "pem" for _, _, a in _spans(text)) else text
    out = []
    for line in text.split("\n"):
        if _spans(line):
            lead = line[: len(line) - len(line.lstrip())]
            out.append(f"{lead}[Zeile unterdrueckt: Geheimnismuster]")
        else:
            out.append(line)
    return "\n".join(out)
