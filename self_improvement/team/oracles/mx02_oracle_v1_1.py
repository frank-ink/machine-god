# MX-02 oracle v1.1 (2026-11-25): v1 + NaN weight. Source of the added case: a TEAM test in runs/mx02_oracle round 3
# (NaN is not in [0, 1]); v1 and my 13 holdout checks both missed it. Not preregistered for that one case.
# Held out for the independent check (not here): key order, missing-text-but-cited, credit with a bad signal.
import dataclasses
import pytest
from artifact import parse_feedback, attribute, credit

BASE = dict(compile_id="c", item_id="i", signal="cited", weight=0.5, ts=1.0)
TEXTS = {"i1": "alpha bravo charlie delta echo", "i2": "zulu yankee xray whiskey victor", "i3": "foxtrot golfs hotel"}


def test_parse_ok():
    assert parse_feedback(BASE).signal == "cited"


@pytest.mark.parametrize("bad", [{k: v for k, v in BASE.items() if k != "ts"}, dict(BASE, item_id=""),
                                 dict(BASE, compile_id=""), dict(BASE, signal="liked"), dict(BASE, weight=1.01),
                                 dict(BASE, weight=-0.01), dict(BASE, weight=float("nan"))])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_feedback(bad)


def test_weight_edges():
    assert parse_feedback(dict(BASE, weight=0.0)).weight == 0.0
    assert parse_feedback(dict(BASE, weight=1.0)).weight == 1.0


def test_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        parse_feedback(BASE).signal = "x"


def test_attribute_rules():
    ans = "we used item i3 here; ALPHA bravo charlie appear. whiskey"
    assert attribute(["i2", "i1", "i3"], ans, TEXTS) == {"i2": "ignored", "i1": "used", "i3": "cited"}


def test_below_overlap():
    assert attribute(["i1"], "alpha bravo", TEXTS) == {"i1": "ignored"}


def test_credit_values():
    sig = {"a": "cited", "b": "used", "c": "ignored", "d": "corrected", "e": "harmful"}
    assert credit(sig) == {"a": 1.0, "b": 0.5, "c": 0.0, "d": -0.5, "e": -1.0}


def test_short_words_do_not_count():
    texts = {"i4": "able bake cake dame"}
    assert attribute(["i4"], "able bake cake dame", texts) == {"i4": "ignored"}
