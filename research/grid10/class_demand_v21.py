"""class_demand_v21.py -- Rule CLASS_DEMAND_V2.1 (Draft ChatGPT Round 8, 2026-11-25) = V2 + four lexicon fixes, V2 remains unchanged and frozen (hash in CHANGES).

CHANGES compared to V2 (found on development sample Pilot v1; thresholds, weights, classes, and interface unchanged):
 1 'ausfuehrlich' (detailed) is not a tool execution (ausfuehr(?!lich)).
 2 Separable verb 'fuehre X aus' (execute X, up to 4 words in between) counts as 'fuehr aus' (execute).
 3 Hyphen compounds are normalized to spaces before matching (same length, offsets preserved): 'Python-Funktion' (Python function) matches 'schreib .. funktion' (write .. function).
 4 Technical terms (binary search, Tiefensuche (depth-first search), Suchbaum (search tree), ...) are not action intents: are masked before matching (same length).
 Not fixed (remains task of INTENT_CORTEX): indirect/implicit intent.

Original V2 header: (Draft ChatGPT Round 5, 2026-11-25; start parameters are HYPOTHESES, frozen before calibration, shadow only).

Intention I_c from evidence levels E0=0 | E1=0.25 (keyword) | E2=0.65 (plausible need) | E3=1.0 (explicit/unambiguous need), lexical
(NO semantic judgment: the levels are regex approximations, quality only established through calibration). S_c = min(1, I_c + 0.15*G_c + 0.10*R_c), choose S_c >= 0.65,
max 4 (E3 first, then score, then name), overflow logged, otherwise ABSTAIN. G6 is NOT credited to code/tool; G only: reason <- G9 (if valid), long <- G10.
Long input alone = E0. Negation (<=4 words before hit) takes precedence -> class in negated_classes, I=0. de is NOT a competitor, but target_language.
Missing inputs (goal, retina) are reported as goal_present/retina_available=False, never valued as measured zero. Retina only reinforces with burst + semantic gate
(like V1) and never without E>=E2."""
import re

RULE_VERSION = "CLASS_DEMAND_V2.1"
CLASSES = ("code", "json", "reason", "long", "tool")
E = {0: 0.0, 1: 0.25, 2: 0.65, 3: 1.0}
WG, WR, THETA, MAX_CLASSES = 0.15, 0.10, 0.65, 4
_NEG = re.compile(r"\b(kein\w*|nicht|ohne|nie|niemals|no|not|don'?t|without|never|statt|anstatt)\b", re.I)
# per class: (E3, E2, E1) pattern, case-insensitive
_P = {
    "code": (r"```|\b(implementier\w*|debugg?\w*|kompilier\w*|refactor\w*|quellcode|implement\w*|compile\w*|traceback|stack ?trace)\b|\bschreib\w* (?:\w+ ){0,2}(?:funktion|skript|script|code|programm|test)\b",
             r"\b(fix\w*|repar\w+|patch\w*|bau\w*|aender\w*|änder\w*|erweiter\w*|port\w*)\b(?:\W+\w+){0,6}?\W+(code|skript|script|modul|funktion|klasse|test\w*|\.py|\.rs|\.go|\.js|bug|fehler)\b|\bexit code\b|\bsyntax ?error\b",
             r"\b(code|funktion|function|bug|skript|script|regex|programm\w*|api)\b"),
    "json": (r"\bals json\b|\bjson[- ]?schema\b|strukturiert\w* (?:ausgabe|format|antwort)|\b(?:gib|liefer\w*|antworte|ausgabe|output|return)\b(?:\W+\w+){0,4}?\W+json\b",
             r"\bjson[- ]?(?:ausgabe|objekt|antwort|datei|format\w*)\b(?=.*\b(?:gib|liefer\w*|erzeug\w*|erstell\w*|gener\w*|bitte)\b)|\b(ausgabeformat|serialisier\w*|payload|als (?:tabelle|csv|yaml|xml))\b",
             r"\bjson\b|\b(yaml|csv|xml|schema|felder|tabelle)\b"),
    "reason": (r"\b(analysier\w*|vergleich\w*|begruend\w*|begründ\w*|beweis\w*|analy[sz]e|compare|prove|justify)\b",
               r"\b(warum|wieso|weshalb|why|unterschied\w*|ursache\w*|was spricht|vor- und nachteile|pro und contra|bewert\w*|abwaeg\w*|abwäg\w*|erklaer\w*|erklär\w*)\b",
               r"\b(grund|hypothese\w*|annahme|folgt|entscheid\w*)\b"),
    "long": (r"\b(ausfuehrlich\w*|ausführlich\w*|vollstaendig\w*|vollständig\w*|komplett\w*|gesamtdokument|in depth|full (?:document|report)|detailed (?:report|document))\b",
             r"\b(bericht|dokument\w*|zusammenfass\w*|fass\w* zusammen|summari[sz]e|report)\b",
             r"\b(detail\w*|umfangreich\w*)\b"),
    "tool": (r"\b(such\w*|f(?:ue|ü)hr\w*(?:\W+\w+){0,4}?\W+aus|ausfuehr(?!lich)\w*|ausführ(?!lich)\w*|oeffne\w*|öffne\w*|bearbeite\w*|lies|lese|download\w*|installier\w*|run|search|fetch|execute|edit)\b(?:\W+\w+){0,5}?\W+(datei\w*|ordner|url|server|seite|web\w*|terminal|befehl|command|file\w*|folder|repo\w*|dienst|service)\b",
             r"\b(such\w*|f(?:ue|ü)hr\w*(?:\W+\w+){0,4}?\W+aus|oeffne\w*|öffne\w*|ausfuehr(?!lich)\w*|ausführ(?!lich)\w*|download\w*|installier\w*|search|fetch|execute|run)\b|https?://",
             r"\b(datei\w*|file\w*|ordner|folder|server|dienst|service|pfad)\b"),
}
_RX = {c: tuple(re.compile(p, re.I) for p in ps) for c, ps in _P.items()}
_LANG = re.compile(r"\b(?:auf|in)\s+(deutsch|englisch|french|franzoesisch|spanisch|german|english)\b|\banswer in (german|english|french)\b|\bantworte auf (deutsch|englisch)\b", re.I)
_DE = set("und der die das nicht ich ist mit ein eine fuer für wie was du es zu den dem von auf im".split())
_EN = set("and the is are not you with for this that what how to of in it".split())
_SCREEN = re.compile(r"bildschirm|\bapp\b|fenster|terminal|screen|window|programm", re.I)
_SEE = re.compile(r"person|mensch|objekt|kamera|raum|bild\b|sehen|siehst|room|camera|object", re.I)
_SEMANTIC = {"fokus_app": _SCREEN, "person_kommt": _SEE, "person_geht": _SEE, "objekt_neu": _SEE, "objekt_weg": _SEE}
_RETINA_CLASS = {"fokus_app": ("tool", "code"), "person_kommt": ("reason",), "person_geht": ("reason",), "objekt_neu": ("reason",), "objekt_weg": ("reason",)}


_TECH = re.compile(r"\b(?:binary|linear|depth[- ]first|breadth[- ]first|binaere|binäre|lineare)[- ]?(?:search|suche)\b|\b(?:tiefen|breiten)suche\b|\bsuch(?:baum|algorithmus|raum)\b|\bsearch (?:tree|algorithm|space|engine)\b", re.I)


def normalize(text):
    """Same length as input (evidence offsets remain valid): hyphens between words -> spaces, technical terms masked."""
    t = re.sub(r"(?<=\w)-(?=\w)", " ", text or "")
    return _TECH.sub(lambda m: "x" * len(m.group(0)), t)


def evidence(text):
    """-> (level_per_class, refs_per_class [[start,end,level]], negated). Highest level wins; negated hits don't count, class is reported."""
    text = normalize(text)
    lvl, refs, neg = {}, {}, []
    for c in CLASSES:
        best, ref, negated = 0, [], False
        for i, rx in enumerate(_RX[c]):
            for m in rx.finditer(text):
                clause = re.split(r"[,;.:!?\n]", text[:m.start()])[-1]  # Negation only takes effect in the same clause
                if _NEG.search(" ".join(clause.split()[-4:]) + " " + m.group(0)):
                    negated = True
                    continue
                st = 3 - i
                if st > best:
                    best, ref = st, [[m.start(), m.end(), st]]
        lvl[c], refs[c] = best, ref
        if negated and best == 0:
            neg.append(c)
    return lvl, refs, neg


def target_language(text):
    m = _LANG.search(text or "")
    if m:
        w = next(g for g in m.groups() if g).lower()
        return {"deutsch": "de", "german": "de", "englisch": "en", "english": "en", "french": "fr", "franzoesisch": "fr", "spanisch": "es"}.get(w, w), "explicit", 0.95
    ws = re.findall(r"[a-zäöüß]+", (text or "").lower())
    if len(ws) < 4:
        return None, "unknown", 0.0
    d, e = sum(w in _DE for w in ws), sum(w in _EN for w in ws)
    if d == e:
        return None, "unknown", 0.0
    return ("de" if d > e else "en"), "inferred", round(min(0.9, abs(d - e) / len(ws) * 3 + 0.3), 2)


def derive(text, goal="", grid=None, relay=(), burst=False, goal_id=None, retina_available=False, turn_origin=None):
    """grid: {"G9","G10","g9_valid"} (G6 deliberately not used). -> mandatory field dict (see Draft Round 5)."""
    text, goal, grid = (text or "").strip(), (goal or "").strip(), grid or {}
    origin = turn_origin or ("user" if text else "endogenous")
    src = text if origin == "user" else goal
    lvl, refs, neg = evidence(src) if src else ({c: 0 for c in CLASSES}, {c: [] for c in CLASSES}, [])
    zl = evidence(goal)[0] if goal and origin == "user" else {c: 0 for c in CLASSES}
    gc = {c: 0.0 for c in CLASSES}
    gc["long"] = float(grid.get("G10", 0.0) or 0.0)
    gc["reason"] = float(grid.get("G9", 0.0) or 0.0) if grid.get("g9_valid") else 0.0
    rc = {c: 0.0 for c in CLASSES}
    if burst and retina_available:
        for ch in relay:
            if ch in _SEMANTIC and _SEMANTIC[ch].search(src + " " + goal):
                for c in _RETINA_CLASS[ch]:
                    rc[c] = 1.0
    sc, gcon, rcon = {}, {}, {}
    for c in CLASSES:
        ok = lvl[c] >= 2  # Reinforcement only on existing semantic evidence (E1 + max. reinforcement = 0.50 < theta)
        gcon[c], rcon[c] = round(WG * gc[c], 4) if ok else 0.0, round(WR * rc[c], 4) if ok else 0.0
        sc[c] = round(min(1.0, E[lvl[c]] + gcon[c] + rcon[c]), 4)
    okc = sorted((c for c in CLASSES if sc[c] >= THETA), key=lambda c: (-(lvl[c] == 3), -sc[c], c))
    sel, over = okc[:MAX_CLASSES], okc[MAX_CLASSES:]
    tl, tls, tlc = target_language(src)
    return {"rule_version": RULE_VERSION, "turn_origin": origin, "target_language": tl, "language_source": tls, "language_confidence": tlc,
            "goal_present": bool(goal), "goal_id": goal_id, "retina_available": bool(retina_available), "evidence_level_by_class": {c: "E%d" % lvl[c] for c in CLASSES},
            "evidence_refs_by_class": refs, "negated_classes": neg, "grid_contribution_by_class": gcon, "retina_contribution_by_class": rcon,
            "scores_by_class": sc, "selected_classes": sel, "abstain": not sel, "abstain_reason": None if sel else ("no_input" if not src else "no_class_qualified"),
            "overflow": over, "goal_evidence_by_class": {c: "E%d" % zl[c] for c in CLASSES}}
