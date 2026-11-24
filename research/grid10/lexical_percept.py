"""lexical_percept.py -- Python port of OMEGA's omega_lexical_percept.go (2026-10-09) "lexical_fallback".

SOURCE (read-only reference): omega_lexical_percept.go (+ omega_grid_signal.go for the cell mapping).
Lexicons and formulas are copied VERBATIM (DE+EN); only syntax is Python. Byte-length comparisons of Go (len(string)) are kept via _blen().

WHAT THIS IS: deterministic SURFACE features of the user's message, NOT a semantic measurement. Label: "lexical_fallback". Lexicons are
"calibrated on nothing" (small on purpose, listed here so the mapping is auditable; only monotone in the stated feature).
SHADOW ONLY: used by register.v2_signals(extended=True) -> separate x-lane f3_grid_v2x_*. Never fed into prompt/context/GWT/behaviour.

Cell mapping (as omega_grid_signal.go DeriveGridSignalVector, lexical branch):
  G1 Abstraktion      = clamp(abstract_tokens / n * 4)            (nominalisation suffixes + abstract-concept lexicon; digit tokens = concrete)
  G2 Affekt           = clamp(0.35 emo + 0.15 '!' + 0.15 CAPS + 0.10 intens + 0.15 emoji)
  G3 Valenz-Spannung  = |clamp((pos-neg)/(pos+neg+0.5), -1, 1)|
  G4 Bindung          = (b+1)/2, b = clamp(personal/n*4 + 0.3 rel)  -> ALWAYS >= 0.5 for any non-empty text (lexical text cannot evidence aversion)
  G5 Endgueltigkeit   = clamp(0.25 definite + 0.15 (closing '.'/'!') - 0.15 hedge - 0.1 ('?' present))
  G9 Ueberraschung    = 1 - max Jaccard(content tokens, each of the last 8 user messages); no history -> g9_valid False -> 0 (never invented)

History for G9 is passed in by the caller (list of (digest, frozenset(token-hashes))); only hashes are ever stored, never prompt text.
Pure python, stdlib only, no I/O. Any error in the caller -> cell 0 (fail-silent there)."""
import hashlib
import math

LABEL = "lexical_fallback"
NOVELTY_RING = 8

ABSTRACT_STEMS = (
    "sinn", "wahrheit", "bewusstsein", "existenz", "realitaet", "realität", "wesen", "freiheit", "gerechtigkeit",
    "moral", "ethik", "ethisch", "philosoph", "metaphys", "ontolog", "erkenntnis", "vernunft", "geist", "seele",
    "unendlich", "ewig", "begriff", "konzept", "prinzip", "theorie", "idee", "natur", "zeit", "raum",
    "meaning", "truth", "conscious", "existence", "reality", "essence", "freedom", "justice", "ethic", "philosoph",
    "metaphys", "ontolog", "knowledge", "reason", "soul", "infinite", "eternal", "concept", "principle", "theory",
    "idea", "nature", "abstract", "universe", "universum", "dasein", "kausal", "causal")
ABSTRACT_SUFFIX = ("heit", "keit", "ung", "tion", "ismus", "taet", "tät", "ness", "ity", "ism", "schaft")
EMOTION_STEMS = (
    "lieb", "hass", "angst", "traurig", "trauer", "freu", "wuetend", "wütend", "zorn", "glueck", "glück", "gluecklich",
    "einsam", "vermiss", "weine", "weinen", "schmerz", "sorge", "sorgen", "veraerger", "verärger", "begeister", "furcht",
    "scham", "stolz", "eifersuch", "verzweif", "hoffnung", "panik", "wut", "herz", "sehnsucht", "schrecklich", "wunderbar",
    "love", "hate", "afraid", "fear", "sad", "happy", "angry", "anger", "lonely", "cry", "pain", "worry",
    "worried", "excited", "proud", "ashamed", "jealous", "desperate", "hope", "panic", "terrible", "wonderful", "heart")
INTENSIFIERS = ("sehr", "total", "extrem", "unglaublich", "so", "voll", "mega", "wahnsinn", "really", "very", "extremely",
                "incredibly", "totally", "absolutely", "so much", "too")
POSITIVE = ("lieb", "freu", "glueck", "glück", "gluecklich", "wunderbar", "toll", "super", "gut", "schoen", "schön",
            "danke", "begeister", "stolz", "hoffnung", "love", "happy", "wonderful", "great", "good", "thanks", "thank", "excited",
            "proud", "hope", "beautiful", "nice")
NEGATIVE = ("hass", "angst", "traurig", "trauer", "wuetend", "wütend", "zorn", "einsam", "schmerz", "sorge",
            "schlecht", "schrecklich", "verzweif", "panik", "furcht", "scham", "fehler", "problem", "kaputt", "error", "hate",
            "afraid", "fear", "sad", "angry", "lonely", "pain", "worry", "bad", "terrible", "panic", "broken", "wrong", "fail")
PERSONAL = frozenset((
    "ich", "mich", "mir", "mein", "meine", "meinem", "meinen", "meiner", "meines", "wir", "uns", "unser", "unsere", "du", "dich", "dir",
    "dein", "deine", "deinem", "deinen", "deiner", "i", "me", "my", "mine", "we", "us", "our", "you", "your", "yours", "i'm", "i've", "you're"))
RELATIONAL = ("freund", "familie", "mama", "papa", "mutter", "vater", "bruder", "schwester", "kind", "partner",
              "liebling", "schatz", "friend", "family", "mother", "father", "brother", "sister", "child", "partner", "darling")
DEFINITE = ("endgueltig", "endgültig", "definitiv", "immer", "nie", "niemals", "nichts", "alles", "muss", "genau",
            "fertig", "ausschliesslich", "ausschließlich", "unbedingt", "garantiert", "final", "definitely", "always", "never", "must",
            "exactly", "only", "absolutely", "certainly", "done", "nothing", "everything")
HEDGE = ("vielleicht", "eventuell", "koennte", "könnte", "koennten", "könnten", "wohl", "ungefaehr", "ungefähr",
         "etwa", "irgendwie", "moeglicherweise", "möglicherweise", "maybe", "perhaps", "might", "could", "probably", "somewhat",
         "sort of", "kind of", "roughly", "possibly")


def _blen(s):
    """Go len(string) = UTF-8 byte length (kept so thresholds behave like the Go original)."""
    return len(s.encode("utf-8"))


def _tokens(s):
    """lexTokens: lower-case, split on everything that is not letter/digit/apostrophe."""
    out, cur = [], []
    for ch in s.lower():
        if ch.isalpha() or ch.isdecimal() or ch == "'":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _has_prefix_any(tok, stems):
    for st in stems:
        if _blen(st) >= 4:
            if tok.startswith(st):
                return True
        elif tok == st:  # short stems must match whole words
            return True
    return False


def _has_suffix_any(tok, sufs):
    for sf in sufs:
        if _blen(tok) > _blen(sf) + 2 and tok.endswith(sf):
            return True
    return False


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _has_digit(t):
    return any(c.isdecimal() for c in t)


def content_tokens(prompt):
    """set of tokens with byte length >= 4 (the Jaccard basis)."""
    return {t for t in _tokens(prompt) if _blen(t) >= 4}


def _h(tok):
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()[:8]


def digest(prompt):
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:16]


def history_entry(prompt):
    """(digest, sorted list of token HASHES) -- what may be stored between hook processes. No plain text."""
    return digest(prompt), sorted(_h(t) for t in content_tokens(prompt))


def lexical_axes(text, history=None):
    """-> dict G1..G5, G9 in [0,1] (cell values as omega_grid_signal.go builds them), 'g9_valid', 'label'.
    history: iterable of (digest, iterable of token-hashes) of the previous user messages (<=8 used; same digest as `text` is skipped = idempotent).
    Empty/blank text -> all 0, g9_valid False (Go: ComputeLexicalPercept returns zero value; grid code needs non-blank prompt)."""
    res = {"G1": 0.0, "G2": 0.0, "G3": 0.0, "G4": 0.0, "G5": 0.0, "G9": 0.0, "g9_valid": False, "label": LABEL}
    text = text or ""
    toks = _tokens(text)
    if not toks or not text.strip():
        return res
    n = float(len(toks))
    content = set()
    abstract = emo = intens = pos = neg = personal = rel = definite = hedge = 0
    for t in toks:
        if _blen(t) >= 4:
            content.add(t)
        if not _has_digit(t) and (_has_prefix_any(t, ABSTRACT_STEMS) or _has_suffix_any(t, ABSTRACT_SUFFIX)):
            abstract += 1
        if _has_prefix_any(t, EMOTION_STEMS):
            emo += 1
        if _has_prefix_any(t, INTENSIFIERS):
            intens += 1
        if _has_prefix_any(t, POSITIVE):
            pos += 1
        if _has_prefix_any(t, NEGATIVE):
            neg += 1
        if t in PERSONAL:
            personal += 1
        if _has_prefix_any(t, RELATIONAL):
            rel += 1
        if _has_prefix_any(t, DEFINITE):
            definite += 1
        if _has_prefix_any(t, HEDGE):
            hedge += 1
    excl = text.count("!")
    caps = 0
    for w in text.split():
        if len(w) >= 3 and w.upper() == w and any(c.isalpha() for c in w):
            caps += 1
    emoji = sum(1 for ch in text if 0x1F300 <= ord(ch) <= 0x1FAFF)
    abstraktion = _clamp(abstract / n * 4)
    intensitaet = _clamp(0.35 * emo + 0.15 * excl + 0.15 * caps + 0.10 * intens + 0.15 * emoji)
    valenz = _clamp((pos - neg) / (pos + neg + 0.5), -1.0, 1.0)
    bindung = _clamp(personal / n * 4 + 0.3 * rel)
    trimmed = text.strip()
    end = 0.15 if (trimmed.endswith(".") or trimmed.endswith("!")) else 0.0
    q = 0.1 if "?" in trimmed else 0.0
    endg = _clamp(0.25 * definite + end - 0.15 * hedge - q)
    res["G1"] = _clamp(abstraktion)
    res["G2"] = _clamp(intensitaet)
    res["G3"] = _clamp(abs(valenz))
    res["G4"] = _clamp((bindung + 1) / 2)
    res["G5"] = _clamp(endg)
    # novelty vs. the last 8 user messages (hashes), skipping an identical digest
    d = digest(text)
    best, anyh = 0.0, False
    hset = {_h(t) for t in content}
    for hd, hs in list(history or [])[-NOVELTY_RING:]:
        if hd == d:
            continue
        anyh = True
        hs = set(hs)
        inter = len(hset & hs)
        union = len(hset) + len(hs) - inter
        if union > 0:
            best = max(best, inter / union)
    if anyh and content:
        res["G9"], res["g9_valid"] = _clamp(1.0 - best), True
    return res
