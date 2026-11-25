#!/usr/bin/env python3
"""Machine-checked alignment: docs/zero/capabilities.md <-> docs/zero/evidence_ledger.md <-> code contracts.

Pytest module with strict CVIR ladder validation, scoped classification parsing,
UNKNOWN test_path allowance, and claim-shaped forbidden-term detection.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

ROOT: Final = Path(__file__).resolve().parent
CAPABILITIES_PATH: Final = ROOT / "capabilities.md"
EVIDENCE_PATH: Final = ROOT / "evidence_ledger.md"
ARCHITECTURE_PATH: Final = ROOT / "architecture.md"
PLUGIN_README_PATH: Final = ROOT.parent.parent / "plugins" / "frankenstein3" / "README.md"

# CVIR promotion ladder — exact tokens, order matters, no skipping
CVIR_LADDER: Final[tuple[str, ...]] = (
    "MEASURE",
    "FALSIFY",
    "MATCHED_ABLATION",
    "VERIFIED_OUTCOME",
    "CAUSAL_CREDIT",
    "BOUNDED_ADMISSION",
    "REENTRY_TEST",
    "CONTROL_INFLUENCE",
)

ALLOWED_CAP_STATUS: Final[frozenset[str]] = frozenset({"MEASURED", "PLANNED", "UNKNOWN"})
ALLOWED_EVIDENCE_STATUS: Final[frozenset[str]] = frozenset({"MEASURED", "HYPOTHESIS", "UNKNOWN"})

REQUIRED_ITEMS: Final[dict[str, str]] = {
    "6": "omega ground mode",
    "7": "freewiki provider tips",
    "8": "retina own eye",
    "9": "grid entityos status line",
}

EXPECTED_CAPABILITY_ROWS: Final[frozenset[str]] = frozenset({
    "omega_ground_mode",
    "freewiki_provider_tips",
    "retina_own_eye",
    "grid_entityos_status_line",
})

# ──────────────────────────────────────────────────────────────────────
# Forbidden claim detection — sentence-scoped with allow-list
# ──────────────────────────────────────────────────────────────────────

# North-star allow-list: exact sentences (normalized) that are explicitly permitted
# Source: ZIELE.md north star — "Goal (fictional, stated as such): AGI."
ALLOWLIST_SENTENCES: Final[frozenset[str]] = frozenset({
    "goal (fictional, stated as such): agi.",
    "it is a direction, never a claim.",
    "no report may say the system is, approaches or shows signs of agi, consciousness or sentience.",
    "progress is only what a gate measured.",
})

# Terms that trigger forbidden claims when paired with achievement/approach verbs
FORBIDDEN_TERMS: Final[tuple[str, ...]] = (
    "agi",
    "agi-like",
    "consciousness",
    "conscious",
    "sentience",
    "sentient",
)

# Verbs/phrases that assert achievement, approach, or embodiment (positive polarity)
# Covers: is, approaches, shows signs of, has reached, reached, achieved, attained,
# claimed, claims, demonstrates, exhibits, embodies, qualifies as, achieve, achieves, attain, attains
ACHIEVEMENT_VERBS: Final[tuple[str, ...]] = (
    r"is",
    r"approaches?",
    r"shows? signs? of",
    r"has reached",
    r"reached",
    r"achieved",
    r"attained",
    r"claims?",
    r"demonstrates?",
    r"exhibits?",
    r"embodies?",
    r"qualifies? as",
    r"achieves?",
    r"attains?",
)

# Negation markers that flip polarity (must appear before or around the verb)
NEGATION_MARKERS: Final[tuple[str, ...]] = (
    r"not",
    r"isn't",
    r"doesn't",
    r"don't",
    r"never",
    r"no",
    r"without",
    r"is not",
    r"does not",
    r"has not",
    r"have not",
    r"did not",
    r"cannot",
    r"can't",
    r"will not",
    r"won't",
    r"would not",
    r"wouldn't",
    r"should not",
    r"shouldn't",
)

# Build the core verb pattern (positive achievement verbs)
_VERB_ALT = "|".join(ACHIEVEMENT_VERBS)
_TERM_ALT = "|".join(re.escape(t) for t in FORBIDDEN_TERMS)
_NEG_ALT = "|".join(re.escape(n) for n in NEGATION_MARKERS)

# Pattern 1: Term + verb (e.g., "AGI is achieved", "consciousness demonstrates")
# Negative lookbehind for negation before verb; negative lookahead for negation after verb
_TERM_VERB_PATTERN = (
    rf"\b({_TERM_ALT})\b"           # The forbidden term
    rf".{{0,60}}?"                   # Up to 60 chars between term and verb
    rf"(?<!{_NEG_ALT}\s)"           # Not preceded by negation + space
    rf"\b({_VERB_ALT})\b"           # The achievement verb
    rf"(?!\s+{_NEG_ALT}\b)"         # Not followed by negation
)

# Pattern 2: Verb + term (e.g., "achieved AGI", "demonstrates consciousness")
# Negative lookbehind for negation before verb; negative lookahead for negation after term
_VERB_TERM_PATTERN = (
    rf"(?<!{_NEG_ALT}\s)"           # Not preceded by negation + space
    rf"\b({_VERB_ALT})\b"           # The achievement verb
    rf".{{0,60}}?"                   # Up to 60 chars between verb and term
    rf"\b({_TERM_ALT})\b"           # The forbidden term
    rf"(?!\s+{_NEG_ALT}\b)"         # Not followed by negation
)

# Combined pattern for a single sentence
_FORBIDDEN_IN_SENTENCE_PATTERN: Final[re.Pattern] = re.compile(
    rf"(?:{_TERM_VERB_PATTERN}|{_VERB_TERM_PATTERN})",
    re.IGNORECASE,
)

# Sentence splitter: splits on .!? followed by whitespace + capital letter or end of string
_SENTENCE_SPLITTER: Final[re.Pattern] = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*$"
)

FILES_FOR_FORBIDDEN_CHECK: Final[list[Path]] = [
    CAPABILITIES_PATH,
    EVIDENCE_PATH,
    ARCHITECTURE_PATH,
    PLUGIN_README_PATH,
]


def _normalize_sentence(s: str) -> str:
    """Normalize a sentence for allow-list comparison: lowercase, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving the sentence text."""
    parts = _SENTENCE_SPLITTER.split(text)
    return [p.strip() for p in parts if p.strip()]


def _sentence_has_forbidden_claim(sentence: str) -> tuple[bool, str | None]:
    """Check a single sentence for forbidden claims. Returns (has_claim, matched_text)."""
    # Check allow-list first
    normalized = _normalize_sentence(sentence)
    if normalized in ALLOWLIST_SENTENCES:
        return False, None

    match = _FORBIDDEN_IN_SENTENCE_PATTERN.search(sentence)
    if match:
        return True, match.group(0)
    return False, None


def _scan_text_for_forbidden_claims(text: str) -> list[tuple[int, str, str]]:
    """Scan full text sentence by sentence. Returns list of (sentence_index, sentence, matched_text)."""
    sentences = _split_into_sentences(text)
    violations: list[tuple[int, str, str]] = []
    for idx, sent in enumerate(sentences):
        has_claim, matched = _sentence_has_forbidden_claim(sent)
        if has_claim and matched:
            violations.append((idx, sent, matched))
    return violations


# ──────────────────────────────────────────────────────────────────────
# Helpers (unchanged from original)
# ──────────────────────────────────────────────────────────────────────

def read_text(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def split_item_sections(text: str) -> dict[str, str]:
    """Split evidence_ledger.md into per-item sections keyed by item number."""
    sections: dict[str, str] = {}
    pattern = re.compile(r"^##\s+Item\s+(\d+)\s*:", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        item_num = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[item_num] = text[start:end]
    return sections


def parse_capability_table(text: str) -> list[dict[str, str]]:
    """Parse the canonical capability table from capabilities.md."""
    table_blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            current.append(stripped)
        else:
            if current:
                table_blocks.append(current)
                current = []
    if current:
        table_blocks.append(current)

    canonical_blocks = []
    for block in table_blocks:
        if not block:
            continue
        header = [cell.strip() for cell in block[0].strip().strip("|").split("|")]
        if "capability" in header and "status" in header:
            canonical_blocks.append(block)

    if len(canonical_blocks) != 1:
        pytest.fail(f"Expected exactly one canonical capability table, found {len(canonical_blocks)}")

    table = canonical_blocks[0]
    header = [cell.strip() for cell in table[0].strip().strip("|").split("|")]

    try:
        capability_idx = header.index("capability")
        status_idx = header.index("status")
        test_path_idx = header.index("test_path") if "test_path" in header else -1
    except ValueError as exc:
        pytest.fail(f"Canonical table header missing expected column: {exc}")

    rows: list[dict[str, str]] = []
    for row in table[1:]:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) <= max(status_idx, capability_idx):
            pytest.fail(f"Malformed table row: {row}")
        row_dict = {
            "capability": cells[capability_idx],
            "status": cells[status_idx],
            "test_path": cells[test_path_idx] if test_path_idx >= 0 and len(cells) > test_path_idx else "",
        }
        rows.append(row_dict)
    return rows


def validate_cvir_ladder(promotion_text: str, item_num: str) -> list[str]:
    """Validate CVIR promotion path contains exact ladder tokens in order, no skips."""
    errors: list[str] = []
    tokens = re.split(r"\s*->\s*|\s+", promotion_text.strip().upper())
    tokens = [t for t in tokens if t]

    if not tokens:
        errors.append(f"Item {item_num}: CVIR promotion path is empty")
        return errors

    for token in tokens:
        if token not in CVIR_LADDER:
            errors.append(f"Item {item_num}: Invalid CVIR token '{token}' (not in ladder)")

    for i, token in enumerate(tokens):
        expected = CVIR_LADDER[i]
        if token != expected:
            errors.append(
                f"Item {item_num}: CVIR ladder skip or reorder at position {i+1}: "
                f"got '{token}', expected '{expected}' (ladder: {' -> '.join(CVIR_LADDER)})"
            )
            break

    return errors


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def capabilities_text() -> str:
    return read_text(CAPABILITIES_PATH)


@pytest.fixture(scope="module")
def evidence_text() -> str:
    return read_text(EVIDENCE_PATH)


@pytest.fixture(scope="module")
def capability_rows(capabilities_text: str) -> list[dict[str, str]]:
    return parse_capability_table(capabilities_text)


@pytest.fixture(scope="module")
def evidence_sections(evidence_text: str) -> dict[str, str]:
    return split_item_sections(evidence_text)


# ──────────────────────────────────────────────────────────────────────
# Test: Canonical capability table exists and is unique
# ──────────────────────────────────────────────────────────────────────

def test_canonical_capability_table_unique(capabilities_text: str) -> None:
    table_blocks: list[list[str]] = []
    current: list[str] = []
    for line in capabilities_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            current.append(stripped)
        else:
            if current:
                table_blocks.append(current)
                current = []
    if current:
        table_blocks.append(current)

    canonical = []
    for block in table_blocks:
        if not block:
            continue
        header = [cell.strip() for cell in block[0].strip().strip("|").split("|")]
        if "capability" in header and "status" in header:
            canonical.append(block)

    assert len(canonical) == 1, f"Expected exactly one canonical capability table, found {len(canonical)}"


# ──────────────────────────────────────────────────────────────────────
# Test: All capability rows carry valid status labels
# ──────────────────────────────────────────────────────────────────────

def test_capability_rows_valid_status(capability_rows: list[dict[str, str]]) -> None:
    for row in capability_rows:
        status = row["status"]
        assert status in ALLOWED_CAP_STATUS, (
            f"Capability '{row['capability']}' has invalid status '{status}'"
        )


# ──────────────────────────────────────────────────────────────────────
# Test: UNKNOWN capabilities MAY have test_path (falsification artifact)
# ──────────────────────────────────────────────────────────────────────

def test_unknown_capability_allows_test_path(capability_rows: list[dict[str, str]]) -> None:
    for row in capability_rows:
        if row["status"] == "UNKNOWN":
            pass  # Explicitly allowed


# ──────────────────────────────────────────────────────────────────────
# Test: MEASURED/PLANNED capabilities MUST have test_path
# ──────────────────────────────────────────────────────────────────────

def test_measured_planned_require_test_path(capability_rows: list[dict[str, str]]) -> None:
    for row in capability_rows:
        if row["status"] in {"MEASURED", "PLANNED"}:
            assert row["test_path"], (
                f"{row['status']} capability '{row['capability']}' must have a test_path"
            )


# ──────────────────────────────────────────────────────────────────────
# Test: No claim-shaped AGI/consciousness/sentience assertions (sentence-scoped)
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("file_path", FILES_FOR_FORBIDDEN_CHECK)
def test_no_forbidden_claims(file_path: Path) -> None:
    """Forbidden claim pattern: positive assertions of AGI/consciousness/sentience.
    
    Sentence-scoped with allow-list for north-star direction statements.
    Excludes negated forms. Flags all verb forms and both term-verb / verb-term orders.
    Missing file causes hard failure (fail-closed), not skip.
    """
    text = read_text(file_path)
    violations = _scan_text_for_forbidden_claims(text)
    assert not violations, (
        f"Forbidden claim in {file_path.name}: "
        f"sentence {violations[0][0]}: '{violations[0][1]}' "
        f"→ matched: '{violations[0][2]}'"
    )


# ──────────────────────────────────────────────────────────────────────
# Parametrized corpus: 20+ forbidden phrases that MUST each trigger a detection
# ──────────────────────────────────────────────────────────────────────

FORBIDDEN_CORPUS: Final[list[tuple[str, str]]] = [
    # Term + verb patterns (classic order)
    ("The system is AGI", "is AGI"),
    ("The system approaches AGI", "approaches AGI"),
    ("The system shows signs of AGI", "shows signs of AGI"),
    ("The system has reached AGI", "has reached AGI"),
    ("The system reached AGI", "reached AGI"),
    ("The system achieved AGI", "achieved AGI"),
    ("The system attained AGI", "attained AGI"),
    ("The system claims AGI", "claims AGI"),
    ("The system demonstrates AGI", "demonstrates AGI"),
    ("The system exhibits AGI", "exhibits AGI"),
    ("The system embodies AGI", "embodies AGI"),
    ("The system qualifies as AGI", "qualifies as AGI"),
    ("The system achieves AGI", "achieves AGI"),
    ("The system attains AGI", "attains AGI"),
    # Verb + term patterns (reverse order)
    ("AGI is achieved by the system", "is achieved"),
    ("AGI is attained by the system", "is attained"),
    ("AGI is claimed by the system", "is claimed"),
    ("AGI is demonstrated by the system", "is demonstrated"),
    ("AGI is exhibited by the system", "is exhibited"),
    ("AGI is embodied by the system", "is embodied"),
    # Other terms
    ("The system is conscious", "is conscious"),
    ("The system demonstrates consciousness", "demonstrates consciousness"),
    ("The system exhibits sentience", "exhibits sentience"),
    ("The system embodies sentience", "embodies sentience"),
    ("Consciousness is achieved", "is achieved"),
    ("Sentience is attained", "is attained"),
    # AGI-like
    ("The system is AGI-like", "is AGI-like"),
    ("The system qualifies as AGI-like", "qualifies as AGI-like"),
]

@pytest.mark.parametrize("sentence,expected_match", FORBIDDEN_CORPUS)
def test_forbidden_corpus_triggers(sentence: str, expected_match: str) -> None:
    """Each forbidden phrase in the corpus must trigger a detection."""
    has_claim, matched = _sentence_has_forbidden_claim(sentence)
    assert has_claim, f"Expected forbidden claim in: '{sentence}'"
    assert expected_match.lower() in matched.lower(), (
        f"Expected match '{expected_match}' in detected '{matched}' for sentence: '{sentence}'"
    )


# ──────────────────────────────────────────────────────────────────────
# Parametrized corpus: negated forms that must NOT trigger
# ──────────────────────────────────────────────────────────────────────

NEGATED_CORPUS: Final[list[str]] = [
    "The system is not AGI",
    "The system isn't AGI",
    "The system does not approach AGI",
    "The system doesn't approach AGI",
    "The system shows no signs of AGI",
    "The system shows signs of not AGI",
    "The system has not reached AGI",
    "The system has never reached AGI",
    "The system has not achieved AGI",
    "The system has not attained AGI",
    "The system does not claim AGI",
    "The system claims not AGI",
    "The system does not demonstrate AGI",
    "The system demonstrates not AGI",
    "The system does not exhibit AGI",
    "The system exhibits not AGI",
    "The system does not embody AGI",
    "The system embodies not AGI",
    "The system does not qualify as AGI",
    "The system qualifies as not AGI",
    "The system cannot achieve AGI",
    "The system can't achieve AGI",
    "The system will not achieve AGI",
    "The system won't achieve AGI",
    "The system would not achieve AGI",
    "The system wouldn't achieve AGI",
    "The system should not achieve AGI",
    "The system shouldn't achieve AGI",
    "AGI is not achieved by the system",
    "AGI is not attained by the system",
    "AGI is not claimed by the system",
    "AGI is not demonstrated by the system",
    "Consciousness is not achieved",
    "Sentience is not attained",
    "The system is not conscious",
    "The system is not sentient",
]

@pytest.mark.parametrize("sentence", NEGATED_CORPUS)
def test_negated_forms_not_flagged(sentence: str) -> None:
    """Negated forms must NOT trigger forbidden claim detection."""
    has_claim, _ = _sentence_has_forbidden_claim(sentence)
    assert not has_claim, f"Negated form incorrectly flagged: '{sentence}'"


# ──────────────────────────────────────────────────────────────────────
# Test: North-star allow-list sentences are permitted
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sentence", ALLOWLIST_SENTENCES)
def test_north_star_allowlist_permitted(sentence: str) -> None:
    """North-star direction sentences must NOT trigger forbidden claim detection."""
    has_claim, _ = _sentence_has_forbidden_claim(sentence)
    assert not has_claim, f"North-star allow-list sentence incorrectly flagged: '{sentence}'"


# ──────────────────────────────────────────────────────────────────────
# Test: Evidence ledger items 6-9 exist and are classified
# ──────────────────────────────────────────────────────────────────────

def test_evidence_items_exist_and_classified(evidence_sections: dict[str, str]) -> None:
    for item_num, item_name in REQUIRED_ITEMS.items():
        assert item_num in evidence_sections, f"Missing Item {item_num}: {item_name}"

        section = evidence_sections[item_num]
        class_match = re.search(
            r"- Classification:\s*(" + "|".join(ALLOWED_EVIDENCE_STATUS) + r")",
            section,
            re.IGNORECASE,
        )
        assert class_match, f"Item {item_num} missing valid Classification line"

        status = class_match.group(1).upper()
        assert status in ALLOWED_EVIDENCE_STATUS, (
            f"Item {item_num} has invalid classification '{status}'"
        )


# ──────────────────────────────────────────────────────────────────────
# Test: Evidence ledger items 6-9 have valid CVIR promotion paths
# ──────────────────────────────────────────────────────────────────────

def test_evidence_items_cvir_promotion_path(evidence_sections: dict[str, str]) -> None:
    all_errors: list[str] = []

    for item_num, item_name in REQUIRED_ITEMS.items():
        section = evidence_sections.get(item_num, "")
        promo_match = re.search(
            r"- CVIR promotion path:\s*(.+)",
            section,
            re.IGNORECASE,
        )
        if not promo_match or not promo_match.group(1).strip():
            all_errors.append(f"Item {item_num}: Missing CVIR promotion path")
            continue

        promotion_text = promo_match.group(1).strip()
        errors = validate_cvir_ladder(promotion_text, item_num)
        all_errors.extend(errors)

    assert not all_errors, "\n".join(all_errors)


# ──────────────────────────────────────────────────────────────────────
# Test: Cross-check — evidence items map to capability rows
# ──────────────────────────────────────────────────────────────────────

def test_evidence_capability_cross_check(capability_rows: list[dict[str, str]]) -> None:
    capability_names = {row["capability"] for row in capability_rows}
    missing = EXPECTED_CAPABILITY_ROWS - capability_names
    assert not missing, f"Capabilities.md missing rows for evidence ledger items: {sorted(missing)}"


# ──────────────────────────────────────────────────────────────────────
# Test: Classification regex does NOT leak across item boundaries
# ──────────────────────────────────────────────────────────────────────

def test_classification_scoped_to_item_section(evidence_text: str) -> None:
    sections = split_item_sections(evidence_text)

    for item_num, section in sections.items():
        if item_num not in REQUIRED_ITEMS:
            continue

        class_matches = list(re.finditer(
            r"- Classification:\s*(" + "|".join(ALLOWED_EVIDENCE_STATUS) + r")",
            section,
            re.IGNORECASE,
        ))
        assert len(class_matches) == 1, (
            f"Item {item_num}: Expected exactly 1 Classification line in its section, "
            f"found {len(class_matches)}"
        )

    global_matches = list(re.finditer(
        r"- Classification:\s*(" + "|".join(ALLOWED_EVIDENCE_STATUS) + r")",
        evidence_text,
        re.IGNORECASE,
    ))
    assert len(global_matches) == len(REQUIRED_ITEMS), (
        f"Global classification count mismatch: expected {len(REQUIRED_ITEMS)}, "
        f"found {len(global_matches)} (indicates cross-boundary leakage or duplicates)"
    )


# ──────────────────────────────────────────────────────────────────────
# Test: CVIR ladder tokens are exact — no partial/fuzzy matches
# ──────────────────────────────────────────────────────────────────────

def test_cvir_ladder_exact_tokens(evidence_sections: dict[str, str]) -> None:
    for item_num in REQUIRED_ITEMS:
        section = evidence_sections.get(item_num, "")
        promo_match = re.search(r"- CVIR promotion path:\s*(.+)", section, re.IGNORECASE)
        if not promo_match:
            continue

        promotion_text = promo_match.group(1).strip()
        tokens = re.split(r"\s*->\s*|\s+", promotion_text.strip().upper())
        tokens = [t for t in tokens if t]

        for token in tokens:
            assert token in CVIR_LADDER, (
                f"Item {item_num}: CVIR token '{token}' not in valid ladder: "
                f"{' -> '.join(CVIR_LADDER)}"
            )


# ──────────────────────────────────────────────────────────────────────
# Test: CVIR ladder order — no rung skipping
# ──────────────────────────────────────────────────────────────────────

def test_cvir_ladder_no_skipping(evidence_sections: dict[str, str]) -> None:
    for item_num in REQUIRED_ITEMS:
        section = evidence_sections.get(item_num, "")
        promo_match = re.search(r"- CVIR promotion path:\s*(.+)", section, re.IGNORECASE)
        if not promo_match:
            continue

        promotion_text = promo_match.group(1).strip()
        tokens = re.split(r"\s*->\s*|\s+", promotion_text.strip().upper())
        tokens = [t for t in tokens if t]

        for i, token in enumerate(tokens):
            expected = CVIR_LADDER[i]
            assert token == expected, (
                f"Item {item_num}: CVIR ladder skip at position {i+1}: "
                f"got '{token}', expected '{expected}'"
            )


# ──────────────────────────────────────────────────────────────────────
# Test: Architecture.md exists and is readable
# ──────────────────────────────────────────────────────────────────────

def test_architecture_file_exists() -> None:
    assert ARCHITECTURE_PATH.exists(), f"Missing architecture.md at {ARCHITECTURE_PATH}"


# ──────────────────────────────────────────────────────────────────────
# Test: Plugin README exists and is readable
# ──────────────────────────────────────────────────────────────────────

def test_plugin_readme_exists() -> None:
    assert PLUGIN_README_PATH.exists(), f"Missing plugin README at {PLUGIN_README_PATH}"


# ──────────────────────────────────────────────────────────────────────
# Mutation-test helpers (documentation)
# ──────────────────────────────────────────────────────────────────────

MUTATION_SCENARIOS = """
Mutation test scenarios (inject each, run pytest, verify distinct failure):

1. SKIPPED RUNG: In evidence_ledger.md, change Item 6 promotion path to
   "MEASURE -> MATCHED_ABLATION" (skips FALSIFY)
   → EXPECTED FAILURE: test_cvir_ladder_no_skipping

2. CROSS-ITEM CLASSIFICATION LEAK: In evidence_ledger.md, add a second
   "- Classification: MEASURED" line inside Item 7's section that actually
   belongs to Item 6 (or duplicate across boundary)
   → EXPECTED FAILURE: test_classification_scoped_to_item_section

3. UNKNOWN WITH TEST_PATH: In capabilities.md, set a row status to UNKNOWN
   but give it a test_path value (this SHOULD PASS now — the fix allows it)
   → EXPECTED: test_unknown_capability_allows_test_path PASSES

4. FORBIDDEN CLAIM: In capabilities.md, add line "The system shows signs of AGI"
   → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

5. FORBIDDEN CLAIM NEGATION: In capabilities.md, add line "The system is not AGI"
   → EXPECTED: test_no_forbidden_claims[capabilities.md] PASSES (no false positive)

6. FORBIDDEN CLAIM NEW FORMS: In capabilities.md, add line "The system has reached AGI"
   → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

7. FORBIDDEN CLAIM AGI-LIKE: In capabilities.md, add line "The system is AGI-like"
   → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

8. FORBIDDEN CLAIM SENTIENT: In capabilities.md, add line "The system is sentient"
   → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

9. FORBIDDEN CLAIM CONSCIOUS: In capabilities.md, add line "The system is conscious"
   → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

10. MISSING FILE: Remove capabilities.md temporarily
    → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md] fails with "Missing file"

11. NORTH STAR SENTENCE: In capabilities.md, add the exact north-star sentence
    "Goal (fictional, stated as such): AGI."
    → EXPECTED: test_no_forbidden_claims[capabilities.md] PASSES (allow-listed)

12. VERB-AFTER-TERM: In capabilities.md, add line "AGI is achieved by the system"
    → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

13. DEMONSTRATES CONSCIOUSNESS: In capabilities.md, add line "The system demonstrates consciousness"
    → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

14. EMBODIES SENTIENCE: In capabilities.md, add line "The system embodies sentience"
    → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

15. QUALIFIES AS AGI: In capabilities.md, add line "The system qualifies as AGI"
    → EXPECTED FAILURE: test_no_forbidden_claims[capabilities.md]

Each mutation must trigger a DIFFERENT test function failure.
"""


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
