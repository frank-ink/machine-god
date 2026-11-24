"""auswahlbericht.py -- Validator fuer den strukturierten Auswahlbericht (Rueckkanal Antwort -> Thalamus, Entwurf ChatGPT Runde 2/4, 2026-11-24).

Rein, ohne DB und ohne Wirkung. Das Modell meldet je uebergebenem Ereignis, ob es in die Antwort einfloss; die Laufzeit prueft gegen das, was TATSAECHLICH
uebergeben wurde, und haengt model_id/Zeit/Antwort-Hash selbst an (nie vom Modell). Regeln:
- nur Felder des Schemas; unbekannte Felder -> Eintrag verworfen (kein model_id vom Modell)
- event_id muss in `passed` sein, channel muss zum uebergebenen Ereignis passen, frame_id/response_id muessen zum Turn passen
- answer_span = [start, ende) in der Antwort; ausserhalb der Antwort oder leer -> erfundene Referenz, Eintrag verworfen
- Widerspruch (gleiche event_id used UND unused) -> beide uncertain; identische Dubletten werden zusammengefasst
- evidence: 'mention' (used + echter Span: beweist Erwaehnung, NICHT Verursachung) | 'claimed' (used ohne Span) | 'none'
- fehlende Ereignisse -> `unreported` (nicht als unused gewertet)"""
import hashlib
import time

FIELDS = {"frame_id", "response_id", "event_id", "channel", "task_class", "uptake", "reason", "answer_span"}
UPTAKE = ("used", "unused", "uncertain")
CLASSES = ("code", "json", "de", "reason", "long", "tool")
MAX_REASON = 300


def _check(e, ctx, resp):
    if not isinstance(e, dict) or set(e) - FIELDS or not {"event_id", "channel", "uptake"} <= set(e):
        return "schema"
    if e.get("frame_id", ctx["frame_id"]) != ctx["frame_id"] or e.get("response_id", ctx["response_id"]) != ctx["response_id"]:
        return "frame"
    if e["event_id"] not in ctx["passed"]:
        return "unknown_event"
    if ctx["passed"][e["event_id"]] != e["channel"]:
        return "channel_mismatch"
    if e["uptake"] not in UPTAKE:
        return "uptake"
    if e.get("task_class") is not None and e["task_class"] not in CLASSES:
        return "task_class"
    r = e.get("reason")
    if r is not None and (not isinstance(r, str) or len(r) > MAX_REASON):
        return "reason"
    s = e.get("answer_span")
    if s is not None:
        if (not isinstance(s, (list, tuple)) or len(s) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in s)
                or not 0 <= s[0] < s[1] <= len(resp)):
            return "invented_span"
        if e["uptake"] == "unused":
            return "span_but_unused"
    return None


def validate(entries, ctx, response_text, runtime=None):
    """ctx: {"frame_id","response_id","passed": {event_id: channel}}. -> {"accepted","rejected","unreported","runtime"}.
    runtime: vom Aufrufer gesetzt (model_id, ...); model_id etc. werden NIE aus entries uebernommen."""
    resp, acc, rej = response_text or "", {}, []
    for e in entries or []:
        err = _check(e, ctx, resp)
        if err:
            rej.append({"reason": err, "event_id": e.get("event_id") if isinstance(e, dict) else None})
            continue
        a = {k: e.get(k) for k in FIELDS}
        a["frame_id"], a["response_id"] = ctx["frame_id"], ctx["response_id"]
        a["answer_span"] = list(a["answer_span"]) if a["answer_span"] else None
        a["evidence"] = ("mention" if a["answer_span"] else "claimed") if a["uptake"] == "used" else "none"
        prev = acc.get(a["event_id"])
        if prev is None:
            acc[a["event_id"]] = a
        elif {prev["uptake"], a["uptake"]} == {"used", "unused"}:  # Widerspruch
            prev["uptake"], prev["evidence"], prev["reason"] = "uncertain", "none", "contradiction"
        elif prev != a:  # abweichende Dublette gleicher Richtung: erster gilt, Rest protokolliert
            rej.append({"reason": "duplicate", "event_id": a["event_id"]})
    rt = dict(runtime or {})
    rt.setdefault("ts", time.time())
    rt["answer_hash"] = hashlib.sha256(resp.encode("utf-8", "replace")).hexdigest()[:16]
    return {"accepted": list(acc.values()), "rejected": rej, "unreported": [i for i in ctx["passed"] if i not in acc], "runtime": rt}


def referenced_channels(result):
    """Kanaele fuer RetinaThalamus.receive_feedback: nur used (mention oder claimed); uncertain/unused/unreported zaehlen nicht."""
    return sorted({a["channel"] for a in result["accepted"] if a["uptake"] == "used"})
