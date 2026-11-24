"""Test-Tor CLASS_DEMAND_V2 (Shadow). Lauf: python3 -I test_class_demand_v2.py (Exit 0 = gruen). Prueft Vertrag und Invarianten der Spezifikation, NICHT semantische Guete (die kommt aus der Kalibrierung)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import class_demand_v2 as v

G0 = {"G9": 0.0, "G10": 0.0, "g9_valid": False}
FIELDS = {"rule_version", "turn_origin", "target_language", "language_source", "language_confidence", "goal_present", "goal_id", "retina_available",
          "evidence_level_by_class", "evidence_refs_by_class", "negated_classes", "grid_contribution_by_class", "retina_contribution_by_class",
          "scores_by_class", "selected_classes", "abstain", "abstain_reason", "overflow"}


def t_pflichtfelder_und_abstain():
    o = v.derive("hallo", "", G0)
    assert FIELDS <= set(o) and o["abstain"] and o["abstain_reason"] == "no_class_qualified" and o["goal_present"] is False and o["retina_available"] is False
    assert v.derive("", "", G0)["abstain_reason"] == "no_input"


def t_stufen_und_schwelle():
    assert v.derive("Gib mir das als JSON", "", G0)["selected_classes"] == ["json"]  # E3
    assert v.derive("Fix den bug im Modul parser.py", "", G0)["evidence_level_by_class"]["code"] == "E2"
    o = v.derive("Das json format ist interessant", "", G0)  # reine Erwaehnung = E1 (0.25) < 0.65, auch mit maximaler GRID/Retina-Hilfe
    assert o["evidence_level_by_class"]["json"] == "E1" and o["abstain"]
    o = v.derive("Ich habe ein Problem mit dem Server", "", {"G9": 1, "G10": 1, "g9_valid": True}, relay=["fokus_app"], burst=True, retina_available=True)
    assert o["scores_by_class"]["tool"] == 0.25 and o["abstain"]  # E1 + max. Verstaerkung: nicht einmal Verstaerkung greift


def t_lange_eingabe_allein_ist_e0():
    o = v.derive("wort " * 400, "", {"G9": 0, "G10": 1.0, "g9_valid": False})
    assert o["evidence_level_by_class"]["long"] == "E0" and o["abstain"]


def t_negation_vorrang_und_satzteil():
    o = v.derive("Schreibe KEINEN code, nur erklaere", "", G0)
    assert "code" not in o["selected_classes"] and "code" in o["negated_classes"] and "reason" in o["selected_classes"]
    assert "reason" not in o["negated_classes"]  # Verneinung endet am Komma


def t_g6_wird_nicht_zugerechnet():
    o = v.derive("hallo", "", {"G6": 1.0, "G9": 0, "G10": 0, "g9_valid": False})
    assert o["abstain"] and o["grid_contribution_by_class"]["code"] == 0.0 and o["grid_contribution_by_class"]["tool"] == 0.0


def t_grid_und_retina_verstaerken_nur_semantik():
    base = v.derive("Warum ist das so?", "", G0)["scores_by_class"]["reason"]
    boosted = v.derive("Warum ist die Person im Raum?", "", {"G9": 1.0, "G10": 0, "g9_valid": True}, relay=["person_kommt"], burst=True, retina_available=True)
    assert abs(boosted["scores_by_class"]["reason"] - min(1.0, base + 0.15 + 0.10)) < 1e-9
    nob = v.derive("Warum ist die Person im Raum?", "", G0, relay=["person_kommt"], burst=False, retina_available=True)
    assert nob["retina_contribution_by_class"]["reason"] == 0.0
    assert v.derive("hallo", "", G0, relay=["person_kommt"], burst=True, retina_available=True)["abstain"]  # Retina allein nie


def t_max4_ueberlauf_und_reihenfolge():
    t = "analysiere das ausfuehrlich, schreibe eine funktion, gib das als json, suche die datei im ordner"
    o = v.derive(t, "", {"G9": 1, "G10": 1, "g9_valid": True})
    assert len(o["selected_classes"]) <= 4 and set(o["selected_classes"]) | set(o["overflow"]) == {c for c, s in o["scores_by_class"].items() if s >= v.THETA}


def t_endogen_ohne_nutzertext():
    o = v.derive("", "implementiere den parser", G0, goal_id="g1")
    assert o["turn_origin"] == "endogenous" and o["selected_classes"] == ["code"] and o["goal_present"] and o["goal_id"] == "g1"
    o = v.derive("hallo", "implementiere den parser", G0)  # Nutzertext primaer, Ziel nur als Z-Evidenz
    assert o["turn_origin"] == "user" and o["abstain"] and o["goal_evidence_by_class"]["code"] == "E3"


def t_zielsprache():
    assert v.target_language("antworte auf englisch bitte")[:2] == ("en", "explicit")
    assert v.target_language("das ist nicht so einfach wie ich dachte")[:2] == ("de", "inferred")
    assert v.target_language("ok") == (None, "unknown", 0.0)
    assert "de" not in v.CLASSES  # kein Wettbewerber


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
