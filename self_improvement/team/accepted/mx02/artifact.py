# artifact.py
from dataclasses import dataclass
from typing import Dict, List
import re


SIGNALS = ("cited", "used", "ignored", "corrected", "harmful")


@dataclass(frozen=True)
class Feedback:
    compile_id: str
    item_id: str
    signal: str
    weight: float
    ts: float


def parse_feedback(d: dict) -> Feedback:
    required_fields = ("compile_id", "item_id", "signal", "weight", "ts")
    for field in required_fields:
        if field not in d:
            raise ValueError(f"missing field: {field}")

    compile_id = d["compile_id"]
    item_id = d["item_id"]
    signal = d["signal"]
    weight = d["weight"]
    ts = d["ts"]

    if not compile_id:
        raise ValueError("empty compile_id")
    if not item_id:
        raise ValueError("empty item_id")
    if signal not in SIGNALS:
        raise ValueError(f"invalid signal: {signal}")
    if not (0.0 <= weight <= 1.0):
        raise ValueError("weight out of range")

    return Feedback(compile_id=compile_id, item_id=item_id, signal=signal, weight=weight, ts=ts)


def _extract_words(text: str) -> set:
    words = re.findall(r'\b\w+\b', text.lower())
    return {w for w in words if len(w) >= 5}


def attribute(selected: List[str], answer_text: str, item_texts: Dict[str, str], min_overlap: int = 3) -> Dict[str, str]:
    answer_lower = answer_text.lower()
    answer_words = _extract_words(answer_text)
    result = {}

    for item_id in selected:
        if item_id in answer_text:
            result[item_id] = "cited"
        elif item_id in item_texts:
            item_words = _extract_words(item_texts[item_id])
            overlap = len(item_words & answer_words)
            if overlap >= min_overlap:
                result[item_id] = "used"
            else:
                result[item_id] = "ignored"
        else:
            result[item_id] = "ignored"

    return result


def credit(signals: Dict[str, str]) -> Dict[str, float]:
    credit_map = {
        "cited": 1.0,
        "used": 0.5,
        "ignored": 0.0,
        "corrected": -0.5,
        "harmful": -1.0,
    }
    result = {}
    for item_id, signal in signals.items():
        if signal not in credit_map:
            raise ValueError(f"unknown signal: {signal}")
        result[item_id] = credit_map[signal]
    return result