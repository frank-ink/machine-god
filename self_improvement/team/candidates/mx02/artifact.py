# artifact.py
import re
from dataclasses import dataclass
from typing import Dict, List

SIGNALS = ("cited", "used", "ignored", "corrected", "harmful")

CREDIT_MAP = {
    "cited": 1.0,
    "used": 0.5,
    "ignored": 0.0,
    "corrected": -0.5,
    "harmful": -1.0,
}

WORD_PATTERN = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class Feedback:
    compile_id: str
    item_id: str
    signal: str
    weight: float
    ts: float


def parse_feedback(d: dict) -> Feedback:
    required = ("compile_id", "item_id", "signal", "weight", "ts")
    for field in required:
        if field not in d:
            raise ValueError(f"missing field: {field}")
    compile_id = d["compile_id"]
    item_id = d["item_id"]
    signal = d["signal"]
    weight = d["weight"]
    ts = d["ts"]
    if not compile_id:
        raise ValueError("compile_id must be non-empty")
    if not item_id:
        raise ValueError("item_id must be non-empty")
    if signal not in SIGNALS:
        raise ValueError(f"invalid signal: {signal}")
    if not (0.0 <= weight <= 1.0):
        raise ValueError("weight must be in [0, 1]")
    return Feedback(compile_id, item_id, signal, float(weight), float(ts))


def word_overlap(item_text: str, answer_text: str, min_overlap: int) -> bool:
    item_words = set(
        w.lower()
        for w in WORD_PATTERN.findall(item_text)
        if len(w) >= 5
    )
    answer_words = set(
        w.lower()
        for w in WORD_PATTERN.findall(answer_text)
        if len(w) >= 5
    )
    return len(item_words & answer_words) >= min_overlap


def attribute(
    selected: List[str],
    answer_text: str,
    item_texts: Dict[str, str],
    min_overlap: int = 3,
) -> Dict[str, str]:
    result = {}
    for item_id in selected:
        if item_id in answer_text:
            result[item_id] = "cited"
        elif item_id not in item_texts:
            result[item_id] = "ignored"
        elif word_overlap(item_texts[item_id], answer_text, min_overlap):
            result[item_id] = "used"
        else:
            result[item_id] = "ignored"
    return result


def credit(signals: Dict[str, str]) -> Dict[str, float]:
    result = {}
    for item_id, signal in signals.items():
        if signal not in CREDIT_MAP:
            raise ValueError(f"unknown signal: {signal}")
        result[item_id] = CREDIT_MAP[signal]
    return result