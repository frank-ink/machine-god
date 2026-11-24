"""intent_cortex.py -- INTENT_CORTEX_V1 (Entwurf ChatGPT Runde 9/10, 2026-11-25), SHADOW. Semantisches Evidenzorgan: liefert NUR Evidenz, keine Entscheidung und keine Ausfuehrung.

Schema je Klasse: class, evidence_level E0..E3, evidence_spans (muessen woertlich im Eingabetext stehen), implicit_intent, negation, confidence, reason.
Auswahl (nur Vorschlag an spaetere Router-Schicht): Klasse nicht negiert, Stufe >= E2, confidence >= 0.5, mind. ein gueltiger Span; sonst ABSTAIN.
Aufruf gegen den konfigurierten OpenAI-kompatiblen Endpunkt (MG_LLM_URL/MG_LLM_MODEL/MG_LLM_KEY, siehe freellm.py; jedes Free-Pool-Modell); fester Aufrufpfad, kein Werkzeug, kein Schreiben ausser dem Shadow-Ledger (nur Hash des Textes, nie der Text selbst).
Der Text geht an den konfigurierten Endpunkt: fuer private Texte einen lokalen Endpunkt setzen. 'llm' ist austauschbar."""
import hashlib
import json
import re
import time
import freellm

RULE_VERSION = "INTENT_CORTEX_V1"
CLASSES = ("code", "json", "reason", "long", "tool")
LEVELS = ("E0", "E1", "E2", "E3")
MIN_CONF, MIN_LEVEL = 0.5, 2
LOG = "create table if not exists f3_intent_log(id integer primary key autoincrement, ts real, text_hash text, model text, rule_version text, valid integer, selected text, abstain integer, raw text)"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False,
    "required": ["class", "evidence_level", "evidence_spans", "implicit_intent", "negation", "confidence", "reason"],
    "properties": {"class": {"enum": list(CLASSES)}, "evidence_level": {"enum": list(LEVELS)}, "evidence_spans": {"type": "array", "items": {"type": "string"}},
                   "implicit_intent": {"type": "boolean"}, "negation": {"type": "boolean"}, "confidence": {"type": "number"}, "reason": {"type": "string"}}}}}}
PROMPT = """Du bist ein Evidenzorgan. Du entscheidest NICHTS, du belegst nur, welche Faehigkeiten die Nachricht des Nutzers braucht.
Klassen: code = Programmcode schreiben/aendern/debuggen; json = Ausgabe in festem maschinenlesbarem JSON-Format; reason = mehrschrittiges Rechnen, Beweisen, Abwaegen, Schlussfolgern;
long = sehr langer Text/Dokument/Verlauf verarbeiten; tool = in der Welt etwas nachsehen/ausfuehren/oeffnen/suchen/starten/senden/loeschen (Dateien, Befehle, Netz, Dienste).
Stufen: E0 kein Hinweis, E1 nur Stichwort, E2 plausibler Bedarf (auch ohne Stichwort, aus der Absicht), E3 eindeutiger Bedarf.
Pflicht: evidence_spans sind WOERTLICHE Ausschnitte der Nachricht. negation=true, wenn die Nachricht die Faehigkeit ausdruecklich ablehnt (z.B. kein Code, nichts ausfuehren).
Nur Wortvorkommen ohne Absicht (ein Hund heisst Json, Code-Review war anstrengend, Suche nach dem Sinn des Lebens) ist E1 oder weniger. Smalltalk, Wissensfragen, Uebersetzungen: keine Klasse nennen.
Gib nur Klassen mit Evidenz an. reason hoechstens 12 Woerter. Antworte ausschliesslich mit JSON gemaess Schema."""


def _ask_local(text, timeout=120):
    msgs = [{"role": "system", "content": PROMPT}, {"role": "user", "content": "Nachricht:\n" + text}]
    return freellm.chat(msgs, max_tokens=450, schema=SCHEMA, timeout=timeout)


def validate(raw, text):
    """-> (items|None, fehler[]). Streng: Struktur, Enumerationen, Spans woertlich im Text, confidence in [0,1]."""
    try:
        d = json.loads(raw)
        items = d["items"]
        assert isinstance(items, list)
    except Exception as e:
        return None, ["json:" + type(e).__name__]
    err, out = [], []
    for i, it in enumerate(items):
        try:
            assert set(it) == {"class", "evidence_level", "evidence_spans", "implicit_intent", "negation", "confidence", "reason"}, "felder"
            assert it["class"] in CLASSES and it["evidence_level"] in LEVELS, "enum"
            assert isinstance(it["evidence_spans"], list) and all(isinstance(s, str) for s in it["evidence_spans"]), "spans"
            assert isinstance(it["implicit_intent"], bool) and isinstance(it["negation"], bool) and isinstance(it["reason"], str), "typ"
            assert isinstance(it["confidence"], (int, float)) and not isinstance(it["confidence"], bool) and 0 <= it["confidence"] <= 1, "confidence"
            bad = [s for s in it["evidence_spans"] if not s or s not in text]
            assert not bad, "span_nicht_im_text"
            out.append(it)
        except AssertionError as e:
            err.append("item%d:%s" % (i, e))
    return out, err


def select(items):
    """Vorschlag: nur nicht negierte Klassen mit Stufe >= E2, confidence >= 0.5 und gueltigem Span, je Klasse die staerkste Evidenz."""
    best = {}
    for it in items:
        if it["negation"] or LEVELS.index(it["evidence_level"]) < MIN_LEVEL or it["confidence"] < MIN_CONF or not it["evidence_spans"]:
            continue
        c = it["class"]
        if c not in best or (LEVELS.index(it["evidence_level"]), it["confidence"]) > (LEVELS.index(best[c]["evidence_level"]), best[c]["confidence"]):
            best[c] = it
    return sorted(best)


def analyse(text, llm=None, conn=None, now=None):
    """-> {valid, errors, items, selected, abstain, rule_version}. Fehlerhafte Antwort: valid=False, selected=[] (ABSTAIN), nie geraten."""
    try:
        raw = (llm or _ask_local)(text)
    except Exception as e:
        raw = ""; err0 = ["llm:" + type(e).__name__]
    else:
        err0 = []
    items, err = validate(raw, text) if raw else (None, err0)
    ok = items is not None and not err
    sel = select(items or []) if ok else []
    res = {"valid": ok, "errors": err, "items": items or [], "selected": sel, "abstain": not sel, "rule_version": RULE_VERSION}
    if conn is not None:
        conn.execute(LOG)
        conn.execute("insert into f3_intent_log(ts,text_hash,model,rule_version,valid,selected,abstain,raw) values(?,?,?,?,?,?,?,?)",
                     (time.time() if now is None else now, hashlib.sha256(text.encode()).hexdigest()[:16], freellm.model() or "unconfigured", RULE_VERSION, int(ok), json.dumps(sel), int(not sel), raw[:4000]))
        conn.commit()
    return res
