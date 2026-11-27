from dataclasses import dataclass
from typing import Dict, List

SIGNALS = ("cited", "used", "ignored", "corrected", "harmful")

@dataclass(frozen=True)
class Feedback:
    compile_id: str
    item_id: str
    signal: str
    weight: float
    ts: float

def parse_feedback(d: dict) -> Feedback:
    required = ("compile_id", "item_id", "signal", "weight", "ts")
    for k in required:
        if k not in d:
            raise ValueError(f"missing field: {k}")
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
    try:
        weight_f = float(weight)
    except (TypeError, ValueError):
        raise ValueError("weight must be numeric")
    if not (0.0 <= weight_f <= 1.0):
        raise ValueError("weight outside [0, 1]")
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        raise ValueError("ts must be numeric")
    return Feedback(compile_id, item_id, signal, weight_f, ts_f)

def _words_ge5(text: str) -> set:
    return {w for w in text.lower().split() if len(w) >= 5}

def attribute(selected: List[str], answer_text: str, item_texts: Dict[str, str], min_overlap: int = 3) -> Dict[str, str]:
    answer_lower = answer_text.lower()
    answer_words = set(answer_lower.split())
    result = {}
    for item_id in selected:
        if item_id in answer_text:
            result[item_id] = "cited"
        else:
            item_text = item_texts.get(item_id)
            if item_text is None:
                result[item_id] = "ignored"
            else:
                item_words = _words_ge5(item_text)
                overlap = item_words & answer_words
                if len(overlap) >= min_overlap:
                    result[item_id] = "used"
                else:
                    result[item_id] = "ignored"
    return result

def credit(signals: Dict[str, str]) -> Dict[str, float]:
    mapping = {
        "cited": 1.0,
        "used": 0.5,
        "ignored": 0.0,
        "corrected": -0.5,
        "harmful": -1.0,
    }
    result = {}
    for k, v in signals.items():
        if v not in mapping:
            raise ValueError(f"unknown signal: {v}")
        result[k] = mapping[v]
    return result