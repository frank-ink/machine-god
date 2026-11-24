"""class_demand.py -- Regel CLASS_DEMAND_V1 (Entwurf ChatGPT Runde 3, 2026-11-24; Gewichte/Schwellen UNKALIBRIERT, eingefroren, nur Shadow).

S_c = 0.55*T_c + 0.20*G_c + 0.15*Z_c + 0.10*R_c, waehle S_c >= 0.50, max 4 Klassen (explizite zuerst, dann Score absteigend, dann alphabetisch,
Ueberlauf wird protokolliert), sonst ABSTAIN. T: explizite Nutzerintention 1, indirekter lexikalischer Hinweis 0.5, sonst 0. Z: dieselbe Klassifikation
auf dem aktiven Ziel (leer -> 0). Fehlt der Nutzertext, ist das Ziel der primaere Eingang (T aus dem Ziel, Z = 0).
G nur aus dem TATSAECHLICHEN Zellvertrag (register.v2_signals): reason <- G9 (nur wenn g9_valid), long <- G10, tool <- G6 (Code/Werkzeug-Heuristik),
code <- G6 nur bei hartem Code-Hinweis (Codeblock, def/class/import, traceback); json, de haben keinen GRID-Indikator -> 0.
R (Retina): 1 nur bei burst UND passendem relayten Ereignis UND semantischem Bezug im Text/Ziel; die Retina erzeugt NIE allein eine Klasse
(R wirkt nur, wenn die passende Intention T_c > 0 vorliegt). Keine Negationsbehandlung (erwartetes Gegenbeispiel 1 des Entwurfs)."""
import re

RULE_VERSION = "CLASS_DEMAND_V1"
CLASSES = ("code", "json", "de", "reason", "long", "tool")
W = {"T": 0.55, "G": 0.20, "Z": 0.15, "R": 0.10}
THRESH, MAX_CLASSES = 0.50, 4

# (explizit, indirekt) je Klasse, kleingeschrieben, Praefix-/Wortgrenzen-Muster DE+EN
_LEX = {
    "code": (r"\b(implementier\w*|debugg?\w*|kompilier\w*|refactor\w*|quellcode|schreib\w* (?:\w+ )?(?:funktion|skript|script|code|programm)|implement\w*|compile\w*|fix(?:e[sn]?)? (?:the |den |das )?bug)\b|```",
             r"\b(code|funktion|function|bug|fehler|traceback|test\w*|regex|skript|script|programm\w*|api)\b"),
    "json": (r"\bjson\b|\bschema\b|strukturiert\w* (?:ausgabe|format|antwort)",
             r"\b(yaml|csv|xml|tabelle|struktur\w*|felder|payload)\b"),
    "de": (r"\bauf deutsch\b|\bdeutsch\w* (?:antwort|ausgabe|text)|\bin german\b|\banswer in german\b",
           r"\b(und|der|die|das|nicht|ich|ist|mit|ein|eine|fuer|für|wie|was|du)\b.*\b(und|der|die|das|nicht|ich|ist|mit|ein|eine|fuer|für|wie|was|du)\b"),
    "reason": (r"\b(analysier\w*|vergleich\w*|begruend\w*|begründ\w*|beweis\w*|erklaer\w*|erklär\w*|analy[sz]e|compare|prove|justify|warum|why)\b",
               r"\b(wieso|weshalb|unterschied\w*|bewert\w*|pro und contra|abwaeg\w*|abwäg\w*|entscheid\w*|ursache\w*|hypothese\w*)\b"),
    "long": (r"\b(ausfuehrlich\w*|ausführlich\w*|vollstaendig\w*|vollständig\w*|komplett\w*|gesamtdokument|detailed|in depth|full (?:document|report)|bericht|dokument)\b",
             None),  # indirekt bei langem Text, siehe _words
    "tool": (r"\b(such[et]?|suche\w*|fuehr\w* aus|führ\w* aus|ausfuehr\w*|ausführ\w*|oeffne\w*|öffne\w*|bearbeite\w*|lies\w*|run|search|fetch|execute|edit|download\w*|installier\w*)\b",
             r"https?://|[/~][\w.-]+/[\w.-]+|\b(datei|file|ordner|folder|server|dienst|service)\b"),
}
_RX = {c: tuple(re.compile(p, re.I) if p else None for p in v) for c, v in _LEX.items()}
_HARD_CODE = re.compile(r"```|\b(def|class|import|traceback)\b", re.I)
_SCREEN = re.compile(r"bildschirm|\bapp\b|fenster|terminal|screen|window|programm", re.I)
_SEE = re.compile(r"person|mensch|objekt|kamera|raum|bild\b|sehen|siehst|room|camera|object", re.I)


def classify(text):
    """-> {klasse: 0|0.5|1, ...} (lexikalisch, ohne Negation)."""
    t, out = text or "", {}
    for c in CLASSES:
        ex, ind = _RX[c]
        v = 1.0 if ex.search(t) else 0.5 if ((ind.search(t) if ind else len(t.split()) > 200)) else 0.0
        out[c] = v
    return out


def retina_boost(text, goal, relay, burst):
    """R_c in {0,1}; nur bei burst + passendem relayten Ereignis + Bezug in Text/Ziel; nie ohne Intention (das prueft derive)."""
    ctx = "%s %s" % (text or "", goal or "")
    r = {c: 0.0 for c in CLASSES}
    if not burst:
        return r
    if "fokus_app" in relay and _SCREEN.search(ctx):
        r["tool"] = r["code"] = 1.0
    if {"person_kommt", "person_geht", "objekt_neu", "objekt_weg"} & set(relay) and _SEE.search(ctx):
        r["reason"] = 1.0
    return r


def derive(text, goal, grid, relay=(), burst=False):
    """grid: {"G6","G9","G10","g9_valid"}. -> dict(scores, selected, overflow, abstain, features)."""
    text, goal = (text or "").strip(), (goal or "").strip()
    t = classify(text if text else goal)
    z = classify(goal) if text else {c: 0.0 for c in CLASSES}
    g6, g9, g10 = (float(grid.get(k, 0.0) or 0.0) for k in ("G6", "G9", "G10"))
    g = {c: 0.0 for c in CLASSES}
    g["tool"], g["long"] = g6, g10
    g["reason"] = g9 if grid.get("g9_valid") else 0.0
    g["code"] = g6 if _HARD_CODE.search(text or goal) else 0.0
    rb = retina_boost(text, goal, relay, burst)
    scores = {}
    for c in CLASSES:
        rc = rb[c] if t[c] > 0 else 0.0  # Retina allein erzeugt nie eine Klasse
        scores[c] = round(W["T"] * t[c] + W["G"] * g[c] + W["Z"] * z[c] + W["R"] * rc, 4)
    ok = [c for c in CLASSES if scores[c] >= THRESH]
    ok.sort(key=lambda c: (-(t[c] == 1.0), -scores[c], c))  # explizite zuerst, Score absteigend, alphabetisch
    sel, over = ok[:MAX_CLASSES], ok[MAX_CLASSES:]
    return {"scores": scores, "selected": sel, "overflow": over, "abstain": not sel, "features": {"T": t, "Z": z, "G": g, "R": rb}}
