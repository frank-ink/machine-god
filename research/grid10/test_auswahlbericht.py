"""Test-Tor Auswahlbericht-Validator. Lauf: python3 -I test_auswahlbericht.py (Exit 0 = gruen)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auswahlbericht as A

CTX = {"frame_id": "f1", "response_id": "r1", "passed": {"e1": "fokus_app", "e2": "person_kommt", "e3": "objekt_neu"}}
RESP = "Das Terminal im Fokus zeigt den Build."


def E(**k):
    d = {"frame_id": "f1", "response_id": "r1", "event_id": "e1", "channel": "fokus_app", "task_class": "tool", "uptake": "used", "reason": "x", "answer_span": [4, 12]}
    d.update(k)
    return d


def _rej(entry):
    r = A.validate([entry], CTX, RESP)
    assert not r["accepted"] and len(r["rejected"]) == 1, r
    return r["rejected"][0]["reason"]


def t_gueltig_mention_und_unreported():
    r = A.validate([E()], CTX, RESP, {"model_id": "m-x"})
    a = r["accepted"][0]
    assert a["evidence"] == "mention" and r["unreported"] == ["e2", "e3"] and r["runtime"]["model_id"] == "m-x" and len(r["runtime"]["answer_hash"]) == 16
    assert A.referenced_channels(r) == ["fokus_app"]
    assert A.validate([E(answer_span=None)], CTX, RESP)["accepted"][0]["evidence"] == "claimed"


def t_erfundene_und_unbekannte():
    assert _rej(E(event_id="e9")) == "unknown_event"
    assert _rej(E(channel="person_geht")) == "channel_mismatch"
    assert _rej(E(answer_span=[30, 99])) == "invented_span"
    assert _rej(E(answer_span=[5, 5])) == "invented_span"
    assert _rej(E(answer_span=[-1, 3])) == "invented_span"
    assert _rej(E(answer_span=[True, 3])) == "invented_span"
    assert _rej(E(uptake="unused")) == "span_but_unused"
    assert _rej(E(uptake="maybe")) == "uptake"
    assert _rej(E(frame_id="f2")) == "frame"
    assert _rej(E(task_class="magie")) == "task_class"
    assert _rej(E(reason="x" * 400)) == "reason"


def t_modell_darf_keine_laufzeitfelder_setzen():
    assert _rej(E(model_id="evil")) == "schema"
    assert _rej({"event_id": "e1"}) == "schema"
    assert {x["reason"] for x in A.validate("kaputt", CTX, RESP)["rejected"]} == {"schema"}
    assert A.validate(None, CTX, RESP)["accepted"] == []


def t_widerspruch_wird_uncertain():
    r = A.validate([E(), E(uptake="unused", answer_span=None)], CTX, RESP)
    assert len(r["accepted"]) == 1 and r["accepted"][0]["uptake"] == "uncertain" and r["accepted"][0]["evidence"] == "none"
    assert A.referenced_channels(r) == []
    r = A.validate([E(), E()], CTX, RESP)  # identische Dublette
    assert len(r["accepted"]) == 1 and not r["rejected"]


def t_nur_used_zaehlt_fuer_rueckkanal():
    es = [E(), E(event_id="e2", channel="person_kommt", uptake="unused", answer_span=None), E(event_id="e3", channel="objekt_neu", uptake="uncertain", answer_span=None)]
    r = A.validate(es, CTX, RESP)
    assert A.referenced_channels(r) == ["fokus_app"] and r["unreported"] == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
