"""Tests V2.1 (Draft ChatGPT Round 8): four lexicon corrections, V2 unchanged, interface unchanged. Run: python3 -I test_class_demand_v21.py"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import class_demand_v2 as v2
import class_demand_v21 as v21

PILOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pilot", "tasks_synthetic_v1.json")
sel = lambda m, t: set(m.derive(t)["selected_classes"])


def t_v2_unchanged():
    h = hashlib.sha256(open(v2.__file__, "rb").read()).hexdigest()
    assert h.startswith("0508993a") and h.endswith("cbf3926") and v2.RULE_VERSION == "CLASS_DEMAND_V2" and v21.RULE_VERSION == "CLASS_DEMAND_V2.1"


def t_verbose_is_not_a_tool():
    t = "Schreibe einen ausfuehrlichen Bericht ueber die Geschichte der Eisenbahn."
    assert "tool" in sel(v2, t) and "tool" not in sel(v21, t) and "long" in sel(v21, t)
    assert "tool" in sel(v21, "Bitte ausfuehren: das Skript im Terminal")  # echte Ausfuehrung bleibt Werkzeug


def t_separable_verb():
    t = "Debugge die Funktion in main.py, fuehre die Tests aus und erklaere, warum sie scheitern."
    assert "tool" not in sel(v2, t) and "tool" in sel(v21, t)
    assert "tool" not in sel(v21, "Fuehre die Tests nicht aus, erklaere nur den Fehler im Terminal.")  # Negation still has precedence


def t_hyphen_compounds():
    t = "Schreibe eine Python-Funktion, die eine Liste sortiert."
    assert "code" not in sel(v2, t) and "code" in sel(v21, t)
    assert v21.normalize("a-b Python-Funktion") == "a b Python Funktion" and len(v21.normalize("x-y")) == 3


def t_technical_term_is_not_an_action():
    t = "Implementiere einen Binary-Search in Rust."
    assert "tool" in sel(v2, t) and "tool" not in sel(v21, t) and "code" in sel(v21, t)
    assert "tool" in sel(v21, "Suche die Datei config.yaml im Ordner")  # echte Suche bleibt Werkzeug
    n = "Tiefensuche und Breitensuche vergleichen"
    assert len(v21.normalize(n)) == len(n)


def t_interface_equal():
    a, b = v2.derive("Analysiere und erklaere das Problem"), v21.derive("Analysiere und erklaere das Problem")
    assert set(a) == set(b) and a["selected_classes"] == b["selected_classes"]
    e = v21.derive("", goal="Resolve knowledge gap: foo", turn_origin="endogenous", goal_id="g1")
    assert e["turn_origin"] == "endogenous"


def t_unaffected_pilot_tasks_identical():
    T = json.load(open(PILOT))
    diff = sorted(t["id"] for t in T if sel(v2, t["text"]) != sel(v21, t["text"]))
    assert diff == [1, 2, 7, 22, 27]  # only the cases of the four corrections change, nothing else


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=2)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
