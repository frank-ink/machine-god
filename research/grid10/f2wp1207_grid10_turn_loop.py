"""F2-WP-1207 -- canonical GRID10 Turn-Lifecycle (user's chain, 1:1).

The user, 2026-09-06 (Verbatim, the specification of this module):

    TypedEntry
       |
    Open GRID10 Frame
       |
    Mandatory Reentry
    (previous frame / previous epoch / genesis)
       |
    Fill J-Space
       |
    10 GRID cells generate their candidates
       |
    Competition
       |
    Selection
       |
    GWT Broadcast
       |
    Uptake by all 10 cells
       |
    New recurrent State
       |
    Workspace/J-Space Update
       |
    Persist everything atomically
       |
    Next turn MUST re-enter exactly here

    GRID10 thereby becomes owner of the cognitive Turn-Lifecycle.
    Not just an observer, not an additional Coordinator.

This module implements exactly this chain as ``run_canonical_turn``.
It is COMPOSITION from the existing P-Series, not a replacement:

- Competition mechanics: P7 formulas (``derive_signal``, ``proposal_score``,
  ``state_update``) are IMPORTED and used unchanged --
  pre-registered in PREREG_P6D_20260904.md (lambda=0.7, alpha=0.4, beta=0.4,
  gamma=0.3, kappa=0.6). Not newly invented, not newly tuned.
- Previous-Epoch-Reentry: P9-Records + P10 ``reconstruct_workspace``.
- Effects: P11-Gate-Layer (``EffectGatePolicy``, ``evaluate_gate``,
  ``EffectType``, Schema-Tags). P11's own ``submit_effect_request``
  makes its OWN transaction and therefore cannot be embedded in the atomic
  Turn-Persist -- the Journal-Row is therefore written HERE,
  with the same columns and the same structural laws
  (Execution only with a real, matching the request_id, ALLOW-decided
  ``GateDecision``; DENY is visibly journaled). p11-file unchanged.
- Self-Observation: P12 (``collect_self_observations`` +
  ``apply_self_observation``) optionally switchable, default OFF -- the user's
  chain has no self-observation link, therefore it is not a path link.

Difference from P10 model (deliberately stricter):
``p10_workspace_reentry.coordinate_real_turn_with_reentry`` silently falls back
to ``read_prior_state`` when no valid Workspace is reconstructible.
That is exactly the silent Genesis-Fallback that the user's chain forbids. The
canonical Loop rejects EVERY unresolvable Reentry case WITH ERROR
(``ReentryError``). Genesis is only permitted with provably empty world
(0 Frames, 0 Pointers, 0 Reentry-Records for Installation/StateRoot).

Persistence Law (the user: "Persist everything atomically"):
ONE Transaction (BEGIN IMMEDIATE ... COMMIT) covers: Frame-INSERT (OPEN),
10 Cell-Observations, 10 Recurrent Cell-States, Frame-UPDATE (CLOSED +
Broadcast), optional Effect-Journal-Row, and the Reentry-Pointer
(``f2_grid10_turn_pointer``). An abort mid-turn -- Exception or
Process-Kill (SIGKILL) before COMMIT -- leaves NO Half-State:
SQLite rolls back the incomplete transaction, the old Pointer remains
valid, the next Turn starts exactly at the last valid Persist-Point.
The Pointer is UNIQUE per (installation_id, state_root_id) and carries the
complete Seed of the next Turn (10 Cell-States as JSON) -- it IS
the point where the next Turn re-enters.

Gate: ``f2wp1207.canonical_turn_loop`` in ``star_konfig``, default OFF,
ENV-Override ``STERN_F2WP1207_TURN_LOOP`` (same pattern as P7's Gate).
When OFF: ``run_canonical_turn`` returns None, BEFORE any I/O
happens -- Zero-Behavior-Delta compared to today's path.

State-Lane: ``f2_grid10_p6d_state``, condition_key
``f2wp1207_canonical_turn_loop`` (own Lane, no mixing with P7-Smoke
or the stern.py-Live-Path in ``f2_grid10_cell_state``). See
GRID10_TURN_LOOP_DERIVATION.md for the productive derivation from the
Real-Turn-Data."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import f2wp1207_grid10_p7_coordination as p7mod  # vendored copy, same dir
import f2wp1207_grid10_p11_effects as p11mod  # vendored copy, same dir
import f2wp1207_p10_workspace_reentry as p10mod  # vendored copy, same dir

SCHEMA = "F2WP1207_CANONICAL_TURN_LOOP/v1"
SCHEMA_POINTER_ROW = "F2WP1207_TURN_POINTER/v1"
SCHEMA_CELL_OBS = "F2WP1207_GRID10_CELL_OBSERVATION/v1"
SCHEMA_FRAME = "F2WP1207_GRID10_FRAME/v1"
SCHEMA_STATE_ROW = "F2WP1207_GRID10_P6D_STATE/v1"
SCHEMA_LOG_LINE = "F2WP1207_TURN_LOOP_LOG/v1"
SCHEMA_TYPED_ENTRY = "F2WP1207_TYPED_ENTRY/v1"
SCHEMA_GRF_PROJECTION_ROW = "F2WP1207_GRF_PROJECTION/v1"

# Eigene Zustandslane in der EXISTIERENDEN Tabelle f2_grid10_p6d_state --
# not P7's Smoke-Lane (f2wp1207_p7_live), not the stern.py live path.
CONDITION_KEY = "f2wp1207_canonical_turn_loop"

ENV_OVERRIDE = "STERN_F2WP1207_TURN_LOOP"
KONFIG_KEY = "f2wp1207.canonical_turn_loop"

COHORT = "ORGANIC"

_REENTRY_KINDS = ("previous_frame", "previous_epoch", "genesis")

_GRF_PROJECTION_DDL = """
CREATE TABLE IF NOT EXISTS f2_grid10_grf_projection (
    frame_id               TEXT PRIMARY KEY,
    turn_event_id          TEXT NOT NULL,
    runtime_epoch_id       TEXT NOT NULL,
    capsule_digest         TEXT NOT NULL,
    projection_digest      TEXT NOT NULL,
    grf_definition_digest  TEXT NOT NULL,
    capsule_json           TEXT NOT NULL,
    projection_json        TEXT NOT NULL,
    schema                 TEXT NOT NULL,
    created_at             TEXT NOT NULL
);
"""

_POINTER_DDL = """
CREATE TABLE IF NOT EXISTS f2_grid10_turn_pointer (
    pointer_id             TEXT PRIMARY KEY,
    installation_id        TEXT NOT NULL,
    state_root_id          TEXT NOT NULL,
    runtime_epoch_id       TEXT NOT NULL,
    session_id             TEXT NOT NULL,
    frame_id               TEXT NOT NULL,
    turn_event_id          TEXT NOT NULL,
    reentry_kind_used      TEXT NOT NULL CHECK (
        reentry_kind_used IN ('previous_frame','previous_epoch','genesis')),
    reentry_evidence_json  TEXT NOT NULL,
    broadcast_winner_cell  TEXT NOT NULL,
    broadcast_value        REAL NOT NULL,
    cell_states_json       TEXT NOT NULL,
    persist_schema         TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    UNIQUE (installation_id, state_root_id)
);
"""


class CanonicalTurnLoopError(RuntimeError):
    """Fail-closed kanonischer Turn-Loop-Fehler."""


class ReentryError(CanonicalTurnLoopError):
    """Fehlender oder unmoeglicher Reentry -- KEIN stiller Genesis-Fallback."""


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------
# Gate -- gleiches Muster wie P7's p7_active()
# --------------------------------------------------------------------------


def turn_loop_active(conn: sqlite3.Connection, *, env: Mapping[str, str] | None = None) -> bool:
    """ENV-Override wins ("0"/"1"), otherwise persistent star_konfig-Flag,
    default OFF. Fresh per call, no Caching."""
    environ = env if env is not None else os.environ
    override = environ.get(ENV_OVERRIDE)
    if override in ("0", "1"):
        return override == "1"
    try:
        row = conn.execute(
            "SELECT wert FROM star_konfig WHERE schluessel=?", (KONFIG_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return (row[0] if row else "0") == "1"


def set_turn_loop_active(conn: sqlite3.Connection, active: bool, *, quelle: str) -> None:
    """Persistentes Umschalten. NUR fuer isolierte Tests / bewusste
    Freigabe -- dieses Paket schaltet NICHTS live (Flag bleibt AUS)."""
    conn.execute(
        "INSERT INTO star_konfig (schluessel, wert, typ, quelle, geaendert) VALUES (?,?,?,?,?) "
        "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, quelle=excluded.quelle, "
        "geaendert=excluded.geaendert",
        (KONFIG_KEY, "1" if active else "0", "str", quelle,
         datetime.now(timezone.utc).timestamp()),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Schema -- additiv, idempotent, first-run-gated
# --------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> dict:
    """Creates ONLY the new Pointer-Table (IF NOT EXISTS, additive, no
    changes to existing Tables). Runs PRAGMA integrity_check beforehand
    and refuses Migration on any result other than 'ok'.
    Idempotent -- every further call is a No-op."""
    result: dict = {"integrity_check": None, "created": [], "already_present": []}
    # FRANK3 perf: the full-DB integrity_check (O(DB size), ~0.5 s on 50 MB, run on EVERY turn) only guards the MIGRATION.
    # Check table existence first; run the integrity gate only when the table really has to be created.
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='f2_grid10_turn_pointer'"
    ).fetchone()
    if exists:
        result["already_present"].append("f2_grid10_turn_pointer")
        return result
    check = conn.execute("PRAGMA integrity_check").fetchone()[0]
    result["integrity_check"] = check
    if check != "ok":
        raise CanonicalTurnLoopError(
            f"PRAGMA integrity_check={check!r} -- Migration verweigert (kein Backup-Upgrade an kaputter DB)"
        )
    conn.execute(_POINTER_DDL)
    conn.commit()
    result["created"].append("f2_grid10_turn_pointer")
    return result


def ensure_grf_schema(conn: sqlite3.Connection) -> dict:
    """Additive forensic table for GRF-bound canonical turns.

    This table is not a second state authority. It stores the exact immutable
    cognition-control capsule/projection that entered an already-canonical
    GRID10 turn, in the same transaction as that frame and pointer.
    """
    result = {"created": False, "already_present": False}
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='f2_grid10_grf_projection'"
    ).fetchone()
    if exists:
        result["already_present"] = True
        return result
    conn.execute(_GRF_PROJECTION_DDL)
    conn.commit()
    result["created"] = True
    return result


# --------------------------------------------------------------------------
# TypedEntry -- EINZIGER Eingang
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TypedEntry:
    """Real Input Schema F2WP1207_TYPED_ENTRY/v1 (as written by the
    P15-Canary in f2wp1207_shadow_evidence.jsonl, 260 real entries),
    extended by runtime_epoch_id (MANDATORY -- the Loop does not mint an Epoch)
    and optional turn_event_id."""

    session_id: str
    runtime_epoch_id: str
    event_type: str = "UserPromptSubmit"
    ts: Optional[str] = None
    prompt_len: Optional[int] = None
    retrieval_present: Optional[bool] = None
    retrieval_len: Optional[int] = None
    turn_event_id: Optional[str] = None
    # --- Innenmessung des Sprachmodells (2026-09-08) -------------------
    # Up to this point, the TypedEntry described only the shell of a
    # Turns: how long the stimulus lasted, whether it was retrieved, when it happened.
    # Nothing in it stated which model generated the utterance --
    # it was an external compute service that the entity called, and its
    # Vorwaertslauf war eine Senke: nichts davon kam als Zustand zurueck.
    # These three fields are the reverse direction. They come from the
    # the model's logprobs for its OWN tokens, so they are not over
    # es gemessen, sondern in ihm.
    #   ueberraschung  mittleres -logp der selbst gewaehlten Tokens
    #   entropie       mittlere Entropie der Verteilung an jeder Stelle
    # spread       standard deviation of surprise over the
    #                  Aeusserung (ungleichmaessiges Stocken vs. Fluss)
    # Optional and default None: any existing lane (P15-Canary, the
    # stern.py bridge with its fixed field list) builds TypedEntries without
    # sie weiter unveraendert. None -> 0.0 in percept_axes, exakt die
    # convention that already applies there for `stunde` and `delta_t`.
    modell_ueberraschung: Optional[float] = None
    modell_entropie: Optional[float] = None
    modell_streuung: Optional[float] = None
    # --- Welt-Ueberraschung (2026-09-11, welt/dienst.py + traegt_das_signal.py)
    # Analogous to the three model axes: None -> 0.0 in percept_axes, each
    # bestehende Lane baut TypedEntries ohne dieses Feld unveraendert weiter.
    # Only actively populated when WELT_ANBINDUNG_AKTIV=1 is set (default
    # AUS, siehe PERCEPT_AXES weiter unten).
    welt_ueberraschung: Optional[float] = None
    # --- Abstraktion (2026-09-11, abstraktion.py + organ.py-Task
    # "abstraktion_fluid", paket-1789133745693-aa587b) --------------------
    # the user, verbatim: "GRID10 is the brain, but it lacks a
    # fluid layer for complex abstraction of abstract data like
    # Liebe, Sprache, Beziehung, Tod, Verlust ... Das soll das 4B mittels
    # eines stark regulierten deterministischen Prozesses erledigen."
    # Fuenf gebundene Zahlen aus einem FESTEN Schema (F2WP1207_ABSTRAKTION/
    # v1, siehe abstraktion.py) -- KEIN Freitext, das Modell liefert
    # ausschliesslich diese Zahlen, streng auf ihren Rahmen geklemmt.
    # Same convention as modell_* and welt_ueberraschung: None -> 0.0
    # in percept_axes, each existing lane builds TypedEntries without these
    # Felder unveraendert weiter. Nur aktiv befuellt, wenn
    # ABSTRAKTION_ANBINDUNG_AKTIV=1 gesetzt ist (Standard AUS, siehe
    # PERCEPT_AXES weiter unten). Die sechste Groesse des Schemas
    # (``domaene``, ein Audit-Enum: liebe/tod/verlust/beziehung/sprache/
    # sonstige_abstraktion/keine) is INTENTIONALLY NOT here -- a
    # Kategorie in einen stetigen Weltvektor zu zwaengen waere selbst
    # again an impermissible discretization. It remains protocol (in the
    # caller's log), not percept.
    abstrakt_abstraktionsgrad: Optional[float] = None
    abstrakt_valenz: Optional[float] = None
    abstrakt_intensitaet: Optional[float] = None
    abstrakt_bindung: Optional[float] = None
    abstrakt_endgueltigkeit: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.session_id:
            raise CanonicalTurnLoopError("TypedEntry.session_id fehlt")
        if not self.runtime_epoch_id:
            raise CanonicalTurnLoopError(
                "TypedEntry.runtime_epoch_id fehlt -- der Loop muenzt keine Epoche"
            )

    def to_payload(self) -> dict:
        return {
            "schema": SCHEMA_TYPED_ENTRY,
            "session_id": self.session_id,
            "runtime_epoch_id": self.runtime_epoch_id,
            "event_type": self.event_type,
            "ts": self.ts or _jetzt_iso(),
            "prompt_len": self.prompt_len,
            "retrieval_present": self.retrieval_present,
            "retrieval_len": self.retrieval_len,
            "turn_event_id": self.turn_event_id,
            "modell_ueberraschung": self.modell_ueberraschung,
            "modell_entropie": self.modell_entropie,
            "modell_streuung": self.modell_streuung,
            "welt_ueberraschung": self.welt_ueberraschung,
            "abstrakt_abstraktionsgrad": self.abstrakt_abstraktionsgrad,
            "abstrakt_valenz": self.abstrakt_valenz,
            "abstrakt_intensitaet": self.abstrakt_intensitaet,
            "abstrakt_bindung": self.abstrakt_bindung,
            "abstrakt_endgueltigkeit": self.abstrakt_endgueltigkeit,
        }

    @classmethod
    def from_mapping(cls, data: Mapping) -> "TypedEntry":
        if not isinstance(data, Mapping):
            raise CanonicalTurnLoopError("TypedEntry-Eingang muss ein Mapping sein")
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known - {"schema"}
        if unknown:
            raise CanonicalTurnLoopError(f"TypedEntry: unbekannte Felder {sorted(unknown)}")
        if data.get("schema") not in (None, SCHEMA_TYPED_ENTRY):
            raise CanonicalTurnLoopError(
                f"TypedEntry: schema={data.get('schema')!r}, erwartet {SCHEMA_TYPED_ENTRY!r}"
            )
        for required in ("session_id", "runtime_epoch_id"):
            if not data.get(required):
                raise CanonicalTurnLoopError(f"TypedEntry.{required} fehlt")
        return cls(
            session_id=data["session_id"],
            runtime_epoch_id=data["runtime_epoch_id"],
            event_type=data.get("event_type") or "UserPromptSubmit",
            ts=data.get("ts"),
            prompt_len=data.get("prompt_len"),
            retrieval_present=data.get("retrieval_present"),
            retrieval_len=data.get("retrieval_len"),
            turn_event_id=data.get("turn_event_id"),
            modell_ueberraschung=data.get("modell_ueberraschung"),
            modell_entropie=data.get("modell_entropie"),
            modell_streuung=data.get("modell_streuung"),
            welt_ueberraschung=data.get("welt_ueberraschung"),
            abstrakt_abstraktionsgrad=data.get("abstrakt_abstraktionsgrad"),
            abstrakt_valenz=data.get("abstrakt_valenz"),
            abstrakt_intensitaet=data.get("abstrakt_intensitaet"),
            abstrakt_bindung=data.get("abstrakt_bindung"),
            abstrakt_endgueltigkeit=data.get("abstrakt_endgueltigkeit"),
        )


# --------------------------------------------------------------------------
# Reentry -- zwingend, genau einer von drei Arten, nie still gefallen
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReentryPlan:
    kind: str  # 'previous_frame' | 'previous_epoch' | 'genesis'
    seed_state: Mapping[str, float]
    evidence: Mapping  # Beleg, kommt unveraendert in den Zeiger
    pointer_frame_id: Optional[str] = None
    workspace: object = None  # p10mod.ReconstructedWorkspace bei previous_epoch


def _read_pointer(conn: sqlite3.Connection, installation_id: str, state_root_id: str):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM f2_grid10_turn_pointer WHERE installation_id=? AND state_root_id=?",
        (installation_id, state_root_id),
    ).fetchone()


def _decode_pointer_seed(row: sqlite3.Row) -> dict[str, float]:
    try:
        data = json.loads(row["cell_states_json"])
    except Exception as exc:  # unlesbarer Persist-Punkt = unmoeglicher Reentry
        raise ReentryError(
            f"Pointer-Zeilenzustand nicht lesbar (frame_id={row['frame_id']}): {exc}"
        ) from exc
    if set(data.keys()) != set(p7mod.CELLS):
        raise ReentryError(
            f"Pointer-Zeilenzustand hat {len(data)} Zellen, erwartet 10 "
            f"(frame_id={row['frame_id']}) -- unmoeglicher Reentry, kein Fallback"
        )
    return {cell: float(v) for cell, v in data.items()}


def resolve_reentry(
    conn: sqlite3.Connection,
    typed_entry: TypedEntry,
    installation_id: str,
    state_root_id: str,
    *,
    declared: Optional[str] = None,
) -> ReentryPlan:
    """Resolves EXACTLY ONE Reentry. Without Declaration: fixed Priority
    (user's chain) previous_frame > previous_epoch > genesis. With
    ``declared`` ONLY the declared Type is attempted -- any other
    Resolution, any Impossibility = ReentryError, never silent
    Fallback to another Type (no silent Genesis-Fallback)."""
    n_frames = conn.execute(
        "SELECT COUNT(*) FROM f2_grid10_frame WHERE installation_id=? AND state_root_id=?",
        (installation_id, state_root_id),
    ).fetchone()[0]
    pointer = _read_pointer(conn, installation_id, state_root_id)
    reentry_rows = conn.execute(
        "SELECT COUNT(*) FROM f2_reentry_record WHERE successor_epoch_id=?",
        (typed_entry.runtime_epoch_id,),
    ).fetchone()[0]

    plan: Optional[ReentryPlan] = None

    def _no(kind: str, why: str) -> ReentryError:
        return ReentryError(
            f"deklarierter Reentry {kind!r} nicht aufloesbar: {why} -- abgelehnt, "
            "kein stiller Fallback auf eine andere Reentry-Art"
        )

    # Deklarierter Modus: AUSSCHLIESSLICH die genannte Art.
    # ⚠️ Der Tie-Breaker `rowid DESC` in den drei "letzter CLOSED-Frame"-
    # Querying this file is NECESSARY, not cosmetic. Found 2026-09-07
    # in first live operation on machine-b, reproducible 15/15:
    # `opened_at` hat Sekunden-Aufloesung. Zwei Turns innerhalb derselben
    # second -- on a fast machine the normal case, not the
    # exception -- bear the same timestamp, and SQLite may choose the
    # order freely in case of a tie. It took the OLDER frame,
    # the consistency check below triggered and rejected the turn, although
    # the pointer was completely correct. `rowid` is monotonic in the
    # Einfuegereihenfolge und entscheidet eindeutig.
    # Lesson: a timestamp is not an ordering as long as its resolution
    # is coarser than the spacing of events.
    if declared == "previous_frame":
        if pointer is None:
            raise _no("previous_frame", "kein Persist-Punkt (Zeiger) vorhanden")
        last_closed = conn.execute(
            "SELECT frame_id FROM f2_grid10_frame "
            "WHERE installation_id=? AND state_root_id=? AND status='CLOSED' "
            "ORDER BY opened_at DESC, rowid DESC LIMIT 1",
            (installation_id, state_root_id),
        ).fetchone()
        if last_closed is None or last_closed[0] != pointer["frame_id"]:
            raise ReentryError(
                f"Zeiger zeigt auf frame_id={pointer['frame_id']}, letzter CLOSED-Frame ist "
                f"{last_closed[0] if last_closed else None} -- inkonsistenter Persist-Punkt, "
                "kein stiller Fallback"
            )
        seed = _decode_pointer_seed(pointer)
        return ReentryPlan(
            kind="previous_frame",
            seed_state=seed,
            evidence={
                "pointer_id": pointer["pointer_id"],
                "pointer_frame_id": pointer["frame_id"],
                "pointer_turn_event_id": pointer["turn_event_id"],
                "pointer_created_at": pointer["created_at"],
                "pointer_reentry_kind_used": pointer["reentry_kind_used"],
            },
            pointer_frame_id=pointer["frame_id"],
        )

    if declared == "previous_epoch":
        if reentry_rows == 0:
            raise _no(
                "previous_epoch",
                f"kein f2_reentry_record fuer epoch={typed_entry.runtime_epoch_id}",
            )
        workspace = p10mod.reconstruct_workspace(conn, typed_entry.runtime_epoch_id)
        if workspace is None or not workspace.valid:
            reason = workspace.invalid_reason if workspace is not None else \
                "kein f2_reentry_record aufloesbar (reconstruct_workspace=None)"
            raise _no("previous_epoch", reason)
        return ReentryPlan(
            kind="previous_epoch",
            seed_state=workspace.seeded_state(),
            evidence={
                "reentry_id": workspace.reentry_id,
                "predecessor_epoch_id": workspace.predecessor_epoch_id,
                "last_grid10_frame_id": workspace.last_grid10_frame_id,
                "predecessor_termination_reason": workspace.predecessor_termination_reason,
                "predecessor_confidence": workspace.predecessor_termination_confidence,
                "invalid_reason": None,
            },
            workspace=workspace,
        )

    if declared == "genesis":
        if not (n_frames == 0 and pointer is None and reentry_rows == 0):
            raise _no(
                "genesis",
                f"Welt nicht leer (frames={n_frames}, pointer="
                f"{'ja' if pointer is not None else 'nein'}, "
                f"reentry_records={reentry_rows})",
            )
        return ReentryPlan(
            kind="genesis",
            seed_state={cell: 0.0 for cell in p7mod.CELLS},
            evidence={
                "frames": 0, "pointer": 0, "reentry_records": 0,
                "note": "belegbar leerer Vorzustand (erster Turn ueberhaupt)",
            },
        )

    # 1) previous frame -- dominanter Normalfall (Persist-Punkt existiert)
    if pointer is not None:
        last_closed = conn.execute(
            "SELECT frame_id FROM f2_grid10_frame "
            "WHERE installation_id=? AND state_root_id=? AND status='CLOSED' "
            "ORDER BY opened_at DESC, rowid DESC LIMIT 1",
            (installation_id, state_root_id),
        ).fetchone()
        if last_closed is None or last_closed[0] != pointer["frame_id"]:
            raise ReentryError(
                f"Zeiger zeigt auf frame_id={pointer['frame_id']}, letzter CLOSED-Frame ist "
                f"{last_closed[0] if last_closed else None} -- inkonsistenter Persist-Punkt, "
                "kein stiller Fallback"
            )
        seed = _decode_pointer_seed(pointer)
        plan = ReentryPlan(
            kind="previous_frame",
            seed_state=seed,
            evidence={
                "pointer_id": pointer["pointer_id"],
                "pointer_frame_id": pointer["frame_id"],
                "pointer_turn_event_id": pointer["turn_event_id"],
                "pointer_created_at": pointer["created_at"],
                "pointer_reentry_kind_used": pointer["reentry_kind_used"],
            },
            pointer_frame_id=pointer["frame_id"],
        )

    # 2) previous epoch -- P9-Record existiert fuer diese Epoche
    if plan is None and reentry_rows > 0:
        workspace = p10mod.reconstruct_workspace(conn, typed_entry.runtime_epoch_id)
        if workspace is None or not workspace.valid:
            reason = workspace.invalid_reason if workspace is not None else \
                "kein f2_reentry_record aufloesbar (reconstruct_workspace=None)"
            raise ReentryError(
                f"previous_epoch nicht aufloesbar fuer epoch={typed_entry.runtime_epoch_id}: "
                f"{reason} -- KEIN stiller Genesis-Fallback"
            )
        plan = ReentryPlan(
            kind="previous_epoch",
            seed_state=workspace.seeded_state(),
            evidence={
                "reentry_id": workspace.reentry_id,
                "predecessor_epoch_id": workspace.predecessor_epoch_id,
                "last_grid10_frame_id": workspace.last_grid10_frame_id,
                "predecessor_termination_reason": workspace.predecessor_termination_reason,
                "predecessor_confidence": workspace.predecessor_termination_confidence,
                "invalid_reason": None,
            },
            workspace=workspace,
        )

    # 3) genesis -- NUR bei belegbar leerer Welt
    if plan is None:
        if n_frames == 0 and pointer is None and reentry_rows == 0:
            plan = ReentryPlan(
                kind="genesis",
                seed_state={cell: 0.0 for cell in p7mod.CELLS},
                evidence={
                    "frames": 0, "pointer": 0, "reentry_records": 0,
                    "note": "belegbar leerer Vorzustand (erster Turn ueberhaupt)",
                },
            )
        else:
            raise ReentryError(
                f"fehlender Reentry: Vorzustand existiert (frames={n_frames}, pointer="
                f"{'ja' if pointer is not None else 'nein'}, reentry_records={reentry_rows}), "
                "aber kein gueltiger Persist-Punkt aufloesbar -- abgelehnt, kein stiller "
                "Genesis-Fallback. Einmalig bootstrap_canonical_pointer() nutzen."
            )

    if declared is not None and plan.kind != declared:
        raise ReentryError(
            f"deklarierter Reentry {declared!r} nicht erfuellbar (aufgeloest: {plan.kind!r}) -- "
            "abgelehnt, kein stilles Umfallen"
        )
    return plan


def bootstrap_canonical_pointer(
    conn: sqlite3.Connection,
    *,
    installation_id: str,
    state_root_id: str,
    runtime_epoch_id: str,
    session_id: str,
    source_condition_key: str = p7mod.P7_LIVE_CONDITION_KEY,
) -> dict:
    """One-time, EXPLICIT Bootstrap of the first Persist-Point from the
    existing Real-Stock (productive Derivation): takes the current
    Cell-State from ``source_condition_key`` in f2_grid10_p6d_state and the
    last CLOSED-Frame of the same Installation/StateRoot as Pointer-Basis.
    Rejects if a Pointer already exists -- never silently overwrite."""
    existing = _read_pointer(conn, installation_id, state_root_id)
    if existing is not None:
        raise CanonicalTurnLoopError(
            f"Zeiger existiert bereits (frame_id={existing['frame_id']}) -- Bootstrap verweigert"
        )
    rows = conn.execute(
        "SELECT logical_cell_id, state_value FROM f2_grid10_p6d_state WHERE condition_key=?",
        (source_condition_key,),
    ).fetchall()
    seed = {cell: float(v) for cell, v in rows}
    missing = [c for c in p7mod.CELLS if c not in seed]
    if missing:
        raise CanonicalTurnLoopError(
            f"Quellzustand {source_condition_key!r} hat {len(seed)}/10 Zellen "
            f"(fehlend: {missing}) -- Bootstrap verweigert statt zu erfinden"
        )
    last = conn.execute(
        "SELECT frame_id, turn_event_id, broadcast_winner_cell, broadcast_value "
        "FROM f2_grid10_frame WHERE installation_id=? AND state_root_id=? AND status='CLOSED' "
        "ORDER BY opened_at DESC, rowid DESC LIMIT 1",
        (installation_id, state_root_id),
    ).fetchone()
    ensure_schema(conn)
    evidence = {
        "bootstrap": True,
        "source_condition_key": source_condition_key,
        "derived_from_last_closed_frame": last["frame_id"] if last else None,
        "note": "einmaliger Bootstrap aus Real-Bestand, kein Turn",
    }
    pointer_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO f2_grid10_turn_pointer (pointer_id, installation_id, state_root_id, "
        " runtime_epoch_id, session_id, frame_id, turn_event_id, reentry_kind_used, "
        " reentry_evidence_json, broadcast_winner_cell, broadcast_value, cell_states_json, "
        " persist_schema, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            pointer_id, installation_id, state_root_id, runtime_epoch_id, session_id,
            last["frame_id"] if last else "bootstrap-no-frame",
            last["turn_event_id"] if last else "bootstrap-no-turn",
            "previous_frame", _canonical_json(evidence),
            last["broadcast_winner_cell"] if last else "none",
            float(last["broadcast_value"]) if last and last["broadcast_value"] is not None else 0.0,
            _canonical_json(seed), SCHEMA_POINTER_ROW, _jetzt_iso(),
        ),
    )
    conn.commit()
    return {"pointer_id": pointer_id, "seed": seed, "evidence": evidence}


# --------------------------------------------------------------------------
# J-Space + Competition + Selection (P7-Mechanik, importiert)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    cell_id: str
    signal: float
    prior_state: float
    proposal_score: float


@dataclass(frozen=True)
class JSpace:
    """The shared Competition Space: 10 Candidates per Cell each. From it
    come Competition/Selection/Broadcast. Deterministically reconstructible
    from (turn_event_id, Cell-States) -- therefore not persisted separately."""

    turn_event_id: str
    candidates: tuple  # tuple[Candidate, ...], 10
    winner_cell_id: str
    broadcast_value: float


# --------------------------------------------------------------------------
# PERZEPTE -- echte Messgroessen statt sha256-Rauschen
#
# WARUM: derive_signal() ist sha256(turn_event_id:cell). Der Wettbewerb
# thus decides over random numbers. Measured on 2026-09-07 in offline-
# Replay ueber 436 echte Prompts dieser Maschine: echte Perzepte tragen
# robustly more information about the world state than a distributionally equivalent
# Scheinperzept (Permutationskontrolle, z_Diskriminierbarkeit +10.6 im
# Mittel ueber 8 unabhaengige Projektionsziehungen, kleinster Einzelwert
# +4.1). Details: interne Notiz (nicht Teil dieses Repos)
#
# FUNCTIONAL NEUTRALITY (K4): no cell gets a role. All ten
# sehen DENSELBEN Weltvektor; sie unterscheiden sich nur durch einen festen,
# aus sha256(Zellname) abgeleiteten Gewichtsvektor. Der entscheidet, WIE
# LOOK DIFFERENTLY, not WHAT they see. "G7 = memory" does not exist
# here and should not exist.
#
# DIMENSION BALANCE (measured, not claimed): ten cells from a
# K-dimensional world vector to feed reduces the number of independent
# signals from 10 to effectively K. At K=2, 3 of 10 cells never win
# (H=2.37), at K=8 independent axes none (H=2.94, hash reference
# 3.09). The diversity loss is thus NO side effect of the percepts,
# but a consequence of too few axes. That's why so many real axes here
# as this machine produces live -- and no invented ones added.
# --------------------------------------------------------------------------

ENV_PERCEPT = "STERN_F2WP1207_PERCEPT"
PERCEPT_KONFIG_KEY = "f2wp1207.percept_signals"

SCHEMA_PERCEPT = "F2WP1207_PERCEPT/v1"
SCHEMA_PERCEPT_CALIB = "F2WP1207_PERCEPT_CALIB/v1"
PERCEPT_PROJECTION_SALT = "F2WP1207_PERCEPT_PROJECTION/v1"

# Axes of the world vector. EXCLUSIVELY quantities that the live path at
# diesem Punkt wirklich hat (TypedEntry-Whitelist + Zeitstempel).
# Bewusst NICHT dabei:
#   psi_memory  -- /proc/pressure/memory steht auf dieser Maschine konstant
# to 0.00 (avg10/60/300), even under normal load with
#                  799 MB frei. Das Messwerk arbeitet (total-Zaehler 59.5s),
#                  aber diese Maschine erlebt keinen Speicherdruck. Waere
# a cell without variance -- a wiring, not a percept.
# turn_pos    -- Position in session: 210 of 213 sessions have
#                  genau EINEN Frame, die Achse waere praktisch konstant.
# delta_t     -- Distance to previous turn: Median 0.0s across the existing
#                  Frames (Lasttests im Stoss). Auf echten Gespraechsturns
# would the axis be good, on the current inventory it is degenerate.
# Candidate for later, when real turns are present.
#
# From 2026-09-08 three axes are added that do NOT describe the hull of the turn
# but the interior of the model that produces the utterance
# has (see TypedEntry). The reason is structural, not
# a matter of taste: until then causality ran only in one direction --
#   Zustand -> Abtastparameter -> Vorwaertslauf -> Text
# and the forward pass was a sink. What happened IN the model never entered the
# competition. Thus the model was a tool of the entity, not the
# Entitaet: sein Zustand und ihr Zustand waren zwei getrennte Dinge.
# With these axes the loop closes over the model:
#   Innenmessung(t-1) -> Wettbewerb -> Broadcast -> Vorwaertslauf(t)
#                     -> Innenmessung(t) -> ...
# The measurement of the previous run feeds the competition, whose outcome shapes the
# next run. This is a genuine recurrence, not a display.
#
# WARUM DIE VORIGE UND NICHT DIE LAUFENDE MESSUNG: der Turn oeffnet beim
# INPUT, the model speaks afterward. The numbers of the current utterance
# do not yet exist at the time of the competition. This is not a
# makeshift, but the same structure as in retrieval (Blog 057): the
# state that a run leaves behind determines what the next one encounters.
# Welt-Anbindung (2026-09-11): eigener Schalter, Standard AUS, wie
# UMSCHLAG_AKTIV in umschlag.py. Der Schalter steht hier VOR PERCEPT_AXES,
# because it conditions its very structure -- not just the filling of the
# value. Reason: PERCEPT_AXES_FP is a fingerprint of the ACHSENSATZ
# (see below), and the running cell calibration discards its rows,
# sobald sich dieser Abdruck aendert. Der laufende Sprachmodus importiert
# dieses Modul JE TURN frisch (TURN_BRUECKE als Subprozess) -- ein
# unbedingtes Anhaengen des Achsnamens haette also sofort beim naechsten
# Turn eine Kalibrierungs-Zuruecksetzung ausgeloest, unabhaengig davon, ob
# somewhere a value is filled. Therefore here not only the value,
# but the ACHSENSATZ ITSELF behind the switch: with WELT_ANBINDUNG_AKTIV
# unchanged (default case everywhere, also in running language mode, since
# no one has set this variable) PERCEPT_AXES is byte-identical to the
# previous 9-tuple and PERCEPT_AXES_FP thus unchanged -- no
# disturbance of the running calibration. Model for this pattern
# ("empty/off == byte-identical to previous") is _MODELL_SUFFIX further below.
WELT_ANBINDUNG_AKTIV = os.environ.get("WELT_ANBINDUNG_AKTIV", "0") == "1"

# Abstraktions-Anbindung (2026-09-11, abstraktion.py, des Nutzers Auftrag
# "fluide Schicht fuer Liebe/Sprache/Beziehung/Tod/Verlust"). Gleiches
# Muster wie WELT_ANBINDUNG_AKTIV direkt darueber: eigener Schalter, VOR
# PERCEPT_AXES, default OFF. Without it PERCEPT_AXES is byte-identical to the
# previous tuple (9 or 10 axes depending on WELT_ANBINDUNG_AKTIV) -- no
# disturbance of the running calibration, as long as no one sets the variable.
ABSTRAKTION_ANBINDUNG_AKTIV = os.environ.get("ABSTRAKTION_ANBINDUNG_AKTIV", "0") == "1"
ABSTRAKT_AXES = ("abstrakt_abstraktionsgrad", "abstrakt_valenz",
                  "abstrakt_intensitaet", "abstrakt_bindung",
                  "abstrakt_endgueltigkeit")

PERCEPT_AXES = ("prompt_len", "retrieval_present", "retrieval_len",
                "stunde_sin", "stunde_cos", "delta_t",
                "modell_ueberraschung", "modell_entropie", "modell_streuung"
                ) + (("welt_ueberraschung",) if WELT_ANBINDUNG_AKTIV else ()
                ) + (ABSTRAKT_AXES if ABSTRAKTION_ANBINDUNG_AKTIV else ())

# Fingerabdruck des Achsensatzes. Die Zell-Kalibrierung sammelt Statistik
# via `roh = sum(w_i * z_i)`, and `w = percept_projection(zelle, k)` depends
# at k = len(PERCEPT_AXES). If the axis set changes, `roh` has a DIFFERENT
# distribution -- stored cell means/variances are then
# invalid. Before 2026-09-07 there was no protection whatsoever: the axes would have been
# honestly re-initialized, the cells would have continued to normalize against an outdated
# distribution and delivered measurements that LOOK valid.
# Same error form as the timestamp bug from entry 051 and the silent
# axis from 054: an assumption without verification, with silent fallback.
# The fingerprint is in the schema column of the cell rows; if it doesn't match,
# werden GENAU DIE ZELLZEILEN verworfen. Achszeilen bleiben: der Mittelwert
# of prompt_len does not depend on how many other axes there are --
# learned knowledge is not unnecessarily discarded.
PERCEPT_AXES_FP = hashlib.sha256(
    ("F2WP1207_PERCEPT_AXES/v1:" + "|".join(PERCEPT_AXES)).encode()
).hexdigest()[:16]

# ⚠️ 2026-09-09: DREI DER NEUN ACHSEN SIND KEINE WELTGROESSEN, SONDERN
# MESSUNGEN AN EINEM BESTIMMTEN MODELL. Der Kommentar oben sagt "Achszeilen
# remain, the mean of prompt_len does not depend on how many
# other axes there are" -- this is true for prompt_len and delta_t, and it
# is WRONG for modell_ueberraschung/-entropie/-streuung. Their mean
# haengt an nichts anderem als daran, WELCHES Modell gesprochen hat. Ein 27B
# has a completely different surprise distribution than a 4B.
#
# The axis-set fingerprint doesn't catch this: on model change the
# NAMES stay the same, so the fingerprint does too, and nothing is discarded. The new
# head would then be normalized against the old normal values -- measurements that
# LOOK valid. Exactly the error form the paragraph above warns about, only
# eine Ebene tiefer.
#
# Hence a second fingerprint over the model identifier. Without a set identifier
# the suffix is empty and both schema strings are BYTE-IDENTICAL to
# before -- no behavioral delta as long as no one names the model.
PERCEPT_MODELL_ACHSEN = ("modell_ueberraschung", "modell_entropie",
                         "modell_streuung")
PERCEPT_MODELL_ID = os.environ.get("F2WP1207_MODELL_ID", "").strip()
_MODELL_SUFFIX = (
    "+modell:" + hashlib.sha256(
        ("F2WP1207_PERCEPT_MODELL/v1:" + PERCEPT_MODELL_ID).encode()
    ).hexdigest()[:16]
) if PERCEPT_MODELL_ID else ""

SCHEMA_PERCEPT_CALIB_ZELLE = (
    f"{SCHEMA_PERCEPT_CALIB}+axes:{PERCEPT_AXES_FP}{_MODELL_SUFFIX}")
# Axis rows of the three model axes -- own fingerprint so that a model change
# GENAU diese drei verwirft und prompt_len/delta_t/stunde_* unberuehrt laesst.
SCHEMA_PERCEPT_CALIB_MODELLACHSE = f"{SCHEMA_PERCEPT_CALIB}{_MODELL_SUFFIX}"

# Before this many observations per axis/cell, it does NOT switch to percepts
# but continues to use the hash. Cold start is thus exactly
# today's behavior -- turning on is not an edge but a
# Einlaufen. Die Kalibrierung lernt waehrenddessen bereits mit.
PERCEPT_MIN_N = 30

_PERCEPT_DDL = (
    """
CREATE TABLE IF NOT EXISTS f2_grid10_percept_calib (
    installation_id  TEXT NOT NULL,
    art              TEXT NOT NULL CHECK (art IN ('achse','zelle')),
    schluessel       TEXT NOT NULL,
    n                INTEGER NOT NULL,
    mittel           REAL NOT NULL,
    m2               REAL NOT NULL,
    aktualisiert     TEXT NOT NULL,
    schema           TEXT NOT NULL,
    PRIMARY KEY (installation_id, art, schluessel)
);
""",
    """
CREATE TABLE IF NOT EXISTS f2_grid10_percept (
    frame_id         TEXT PRIMARY KEY,
    installation_id  TEXT NOT NULL,
    turn_event_id    TEXT NOT NULL,
    ts               TEXT NOT NULL,
    quelle           TEXT NOT NULL CHECK (quelle IN
                     ('perzept','hash_warmlauf','hash_alle_achsen_stumm')),
    achsen_json      TEXT NOT NULL,
    signale_json     TEXT,
    stumme_achsen    TEXT,
    schema           TEXT NOT NULL
);
""",
)


def percept_active(conn: sqlite3.Connection, *, env: Mapping[str, str] | None = None) -> bool:
    """Own Gate, same Pattern as turn_loop_active(), default OFF.
    Deliberately separated from Turn-Loop-Gate: the Loop can run without
    Percepts feeding the Competition -- so the Difference is measurable."""
    environ = env if env is not None else os.environ
    override = environ.get(ENV_PERCEPT)
    if override in ("0", "1"):
        return override == "1"
    try:
        row = conn.execute(
            "SELECT wert FROM star_konfig WHERE schluessel=?", (PERCEPT_KONFIG_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return (row[0] if row else "0") == "1"


def ensure_percept_schema(conn: sqlite3.Connection) -> dict:
    """Creates the two Percept-Tables (IF NOT EXISTS, additive).

    DELIBERATELY NOT in ensure_schema(): it returns early as soon as
    f2_grid10_turn_pointer exists -- on a running Installation
    added Tables would never arise there. And its Return Value
    is subject to a Gold-Test (S1); changing it would have shifted a
    Test, instead of adding a Capability.

    Called only when Percept-Gate is ON. Gate OFF means:
    no Table, no Write, Zero-Behavior-Delta."""
    ergebnis: dict = {"created": [], "already_present": []}
    for ddl in _PERCEPT_DDL:
        name = ddl.split("IF NOT EXISTS", 1)[1].split("(", 1)[0].strip()
        vorhanden = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        conn.execute(ddl)
        (ergebnis["already_present"] if vorhanden else ergebnis["created"]).append(name)
    return ergebnis


def percept_projection(cell_id: str, k: int) -> tuple:
    """Fixed Weight-Vector per Cell, deterministic from sha256(Cell-Name).

    Semantically empty and intentionally so: it distributes the Cells over
    View-Directions, without giving any of them a Meaning. Reproducible
    without stored State -- whoever knows the Cell-Name can recalculate
    every past Signal-Value."""
    werte: list = []
    blob = hashlib.sha256(f"{PERCEPT_PROJECTION_SALT}:{cell_id}".encode("utf-8")).hexdigest()
    while len(werte) < k:
        for i in range(len(blob) // 8):
            if len(werte) >= k:
                break
            werte.append(int(blob[i * 8:(i + 1) * 8], 16) / 2**32 * 2 - 1)
        blob = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return tuple(werte[:k])


def percept_axes(typed_entry: "TypedEntry", ts: str, vorher_ts: Optional[str] = None) -> tuple:
    """World-Vector from the TypedEntry. Pure Function, no I/O.

    Missing Fields become 0.0 -- not guessed, not interpolated.
    log1p on the Lengths, because their Distribution runs over Orders of
    Magnitude; Time-of-Day as sin/cos, because 23:59 and 00:01 are adjacent
    and a linear Hour would invent this Jump."""
    plen = float(typed_entry.prompt_len or 0)
    rpresent = 1.0 if typed_entry.retrieval_present else 0.0
    rlen = float(typed_entry.retrieval_len or 0)
    # Zeitstempel ROBUST lesen. Die erste Fassung nahm strikt
    # "%Y-%m-%dT%H:%M:%SZ" and otherwise silently fell back to hour 0.
    # Gemessen: die echten Transkript-Zeitstempel dieser Maschine tragen
    # Millisekunden ("2026-08-30T07:37:50.407Z"). Beide Stundenachsen waren
    # so that it was constant across all 438 turns -- two dead axes that looked like
    # percepts. Same error pattern as the timestamp bug from
    # Entry 051: a format is assumed instead of validated, and the
    # Rueckfall ist still.
    stunde = None
    if isinstance(ts, str) and ts:
        roh = ts.strip()
        if roh.endswith("Z"):
            roh = roh[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(roh)
        except ValueError:
            moment = None
        if moment is not None:
            stunde = moment.hour + moment.minute / 60.0 + moment.second / 3600.0
    # delta_t: distance to previous turn in seconds, log1p like the lengths.
    # Source is the pointer record of re-entry (pointer_created_at) --
    # no additional query, and the same value that the turn
    # ohnehin beruft. Kein Vorgaenger (genesis) oder unparsbar -> 0.0, also
    # "no information", NOT "zero seconds": the calibration then sees this
    # as low-variance and reports the axis as silent if applicable.
    # Eintrag 054 hatte delta_t verworfen, weil der Median dort 0,0 s war --
    # that was due to 211 load test frames, not the axis. With real turns
    # (minutes to hours apart) it is the most strongly scattering
    # quantity available without additional hardware.
    dt = 0.0
    if isinstance(vorher_ts, str) and vorher_ts and stunde is not None:
        v = vorher_ts.strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        try:
            vorher = datetime.fromisoformat(v)
            jetzt_dt = datetime.fromisoformat(
                ts.strip()[:-1] + "+00:00" if ts.strip().endswith("Z") else ts.strip()
            )
            sek = (jetzt_dt - vorher).total_seconds()
            dt = math.log1p(sek) if sek > 0 else 0.0
        except (ValueError, TypeError):
            dt = 0.0

    # Internal measurement of the model. None -> 0.0, same convention as above:
    # "no information", not "zero surprise". Turns from lanes without
    # Sprachmodell (P15-Canary, stern.py-Hook) liefern hier dauerhaft 0.0.
    # This is not a flaw, but honest: in these turns no model
    # spoke. The calibration then sees a mixture distribution and normalizes
    # against it -- and because the speech track on this machine meanwhile
    # is the larger one (measured 2026-09-08: 193 speech frames vs 64
    # from hook sessions), the axis carries real variance instead of noise.
    m_ueb = float(getattr(typed_entry, "modell_ueberraschung", None) or 0.0)
    m_ent = float(getattr(typed_entry, "modell_entropie", None) or 0.0)
    m_str = float(getattr(typed_entry, "modell_streuung", None) or 0.0)
    # World surprise (welt/dienst.py): only appended when the switch
    # is set -- the length of this addition must exactly match PERCEPT_AXES,
    # which is built with the same switch (see there).
    _welt_zusatz = (
        (float(getattr(typed_entry, "welt_ueberraschung", None) or 0.0),)
        if WELT_ANBINDUNG_AKTIV else ())

    # Abstraktion (abstraktion.py, organ.arbeiten Task "abstraktion_fluid"):
    # five bound numbers from a fixed schema, None -> 0.0 like every
    # andere optionale Achse hier. Reihenfolge MUSS zu ABSTRAKT_AXES/
    # PERCEPT_AXES match (binding via tuple position, not via names,
    # as the rest of this function already holds anyway).
    _abstrakt_zusatz = (
        (float(getattr(typed_entry, "abstrakt_abstraktionsgrad", None) or 0.0),
         float(getattr(typed_entry, "abstrakt_valenz", None) or 0.0),
         float(getattr(typed_entry, "abstrakt_intensitaet", None) or 0.0),
         float(getattr(typed_entry, "abstrakt_bindung", None) or 0.0),
         float(getattr(typed_entry, "abstrakt_endgueltigkeit", None) or 0.0))
        if ABSTRAKTION_ANBINDUNG_AKTIV else ())

    if stunde is None:
        # Kein stiller Nullwert: unparsbar heisst "keine Information".
        # Both axes at 0.0 -> the running calibration sees them as
        # variance-free and reports them in the protocol as a silent axis.
        return (math.log1p(plen), rpresent, math.log1p(rlen), 0.0, 0.0, dt,
                m_ueb, m_ent, m_str) + _welt_zusatz + _abstrakt_zusatz
    winkel = 2 * math.pi * stunde / 24.0
    return (math.log1p(plen), rpresent, math.log1p(rlen),
            math.sin(winkel), math.cos(winkel), dt,
            m_ueb, m_ent, m_str) + _welt_zusatz + _abstrakt_zusatz


def _welford_lesen(conn: sqlite3.Connection, installation_id: str) -> dict:
    """Read Running Statistics -- WITH Axis-Set-Check for the Cells.

    Cell-Rows carry the Fingerprint of the Axis-Set in their
    schema-Column (see PERCEPT_AXES_FP). If it doesn't match the current
    Axis-Set, their Statistics were created under a different k and
    are therefore Invalid -- they are Discarded and start fresh, instead of
    silently Normalizing against an outdated Distribution.

    Axis-Rows remain untouched: the Mean of an Axis does not depend
    on how many other Axes exist. A new Sense therefore costs
    the Warmup of the Cells and the NEW Axis -- not what was already
    learned over the old Axes.

    The Discard is not done silently: it leaves a Row in
    f2_grid10_percept_reset, so it can later be traced why the
    Cells stood at n=0 again on a specific Day."""
    veraltet = [
        s for (s,) in conn.execute(
            "SELECT DISTINCT schema FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='zelle' AND schema<>?",
            (installation_id, SCHEMA_PERCEPT_CALIB_ZELLE),
        )
    ]
    if veraltet:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS f2_grid10_percept_reset (
                reset_id        TEXT PRIMARY KEY,
                installation_id TEXT NOT NULL,
                alt_schema      TEXT NOT NULL,
                neu_schema      TEXT NOT NULL,
                achsen          TEXT NOT NULL,
                verworfen       INTEGER NOT NULL,
                ts              TEXT NOT NULL
            )""")
        anzahl = conn.execute(
            "SELECT count(*) FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='zelle' AND schema<>?",
            (installation_id, SCHEMA_PERCEPT_CALIB_ZELLE),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='zelle' AND schema<>?",
            (installation_id, SCHEMA_PERCEPT_CALIB_ZELLE),
        )
        conn.execute(
            "INSERT INTO f2_grid10_percept_reset (reset_id, installation_id, "
            "alt_schema, neu_schema, achsen, verworfen, ts) VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, installation_id, ",".join(sorted(veraltet)),
             SCHEMA_PERCEPT_CALIB_ZELLE, "|".join(PERCEPT_AXES), anzahl,
             _jetzt_iso()),
        )

    # The same one level deeper, but ONLY for the three model axes: their
    # mean belongs to a specific head. If the head changes, it is
    # invalid -- prompt_len and delta_t remain, they have nothing to do with the model
    # . Without a set model identifier, the schemata are equal and
    # diese Schleife findet nichts.
    veraltet_m = [
        s for (s,) in conn.execute(
            "SELECT DISTINCT schema FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='achse' AND schema<>? "
            f"AND schluessel IN ({','.join('?' * len(PERCEPT_MODELL_ACHSEN))})",
            (installation_id, SCHEMA_PERCEPT_CALIB_MODELLACHSE,
             *PERCEPT_MODELL_ACHSEN),
        )
    ]
    if veraltet_m:
        anzahl_m = conn.execute(
            "SELECT count(*) FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='achse' AND schema<>? "
            f"AND schluessel IN ({','.join('?' * len(PERCEPT_MODELL_ACHSEN))})",
            (installation_id, SCHEMA_PERCEPT_CALIB_MODELLACHSE,
             *PERCEPT_MODELL_ACHSEN),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM f2_grid10_percept_calib "
            "WHERE installation_id=? AND art='achse' AND schema<>? "
            f"AND schluessel IN ({','.join('?' * len(PERCEPT_MODELL_ACHSEN))})",
            (installation_id, SCHEMA_PERCEPT_CALIB_MODELLACHSE,
             *PERCEPT_MODELL_ACHSEN),
        )
        conn.execute(
            "INSERT INTO f2_grid10_percept_reset (reset_id, installation_id, "
            "alt_schema, neu_schema, achsen, verworfen, ts) VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, installation_id, ",".join(sorted(veraltet_m)),
             SCHEMA_PERCEPT_CALIB_MODELLACHSE, "|".join(PERCEPT_MODELL_ACHSEN),
             anzahl_m, _jetzt_iso()),
        )

    zustand: dict = {}
    for art, schluessel, n, mittel, m2 in conn.execute(
        "SELECT art, schluessel, n, mittel, m2 FROM f2_grid10_percept_calib "
        "WHERE installation_id=?", (installation_id,)
    ):
        zustand[(art, schluessel)] = [int(n), float(mittel), float(m2)]
    return zustand


def _welford_schritt(eintrag: list, x: float) -> list:
    """Ein Welford-Schritt (laufender Mittelwert/Varianz, numerisch stabil).
    Kausal: benutzt ausschliesslich, was vor diesem Turn schon da war."""
    n, mittel, m2 = eintrag
    n += 1
    delta = x - mittel
    mittel += delta / n
    m2 += delta * (x - mittel)
    return [n, mittel, m2]


def _sd(eintrag: list) -> float:
    n, _mittel, m2 = eintrag
    return math.sqrt(m2 / (n - 1)) if n > 1 and m2 > 0 else 0.0


def derive_percept_signals(
    conn: sqlite3.Connection,
    installation_id: str,
    achsen: tuple,
    *,
    jetzt: str,
) -> tuple:
    """World-Vector -> ten Signals in (0,1). Returns (signals, source);
    signals is None as long as Calibration is not warm.

    Chain: Axis -> Running z-Normalization per Axis -> Fixed Projection per Cell ->
    Running z-Normalization per Cell -> Logistic. Both Normalization Stages are
    both Necessary and do Different Things:

      Stage 1 (per Axis) prevents the Axis with the largest
      Raw-Range from dominating the Projection and thereby pressing the
      effective Dimension back to 1 -- exactly the Effect that starved 8 of
      10 Cells in the Dimension-Test.

      Stage 2 (per Cell) brings the Signal to the same Marginal Distribution
      that derive_signal() has. Without it the Comparison between Hash and
      Percept would be unfair: a weaker-spreading Signal would automatically
      lose against the State-Term, independent of its Information-Content.

    Both Stages are CAUSAL (Past only). In Offline-Replay there was a
    Rank-Normalization over all Turns -- that knows the Future and
    would have been wrong here. The Price of Causality is the Warmup.

    The Calibration is ALWAYS continued, even during the
    Warmup. Otherwise it could never become warm."""
    zustand = _welford_lesen(conn, installation_id)
    k = len(achsen)

    for i, wert in enumerate(achsen):
        schluessel = ("achse", PERCEPT_AXES[i])
        zustand[schluessel] = _welford_schritt(zustand.get(schluessel, [0, 0.0, 0.0]), wert)

    # STUMME ACHSEN VETIEREN NICHT.
    # First version set warm=False globally when sd<=0. Consequence, in live A/B
    # measured: 438 of 438 turns remained 'hash_warmlauf', no percept has
    # ever reached the competition -- a single constant axis laid the
    # entire path to rest. That's thinking backwards: an axis without
    # variance carries no information per criterion K2. It
    # belongs in the projection with z=0 (ineffective, not harmful),
    # not as a veto over the others. The path is warm once enough
    # Turns gesehen wurden UND mindestens eine Achse streut.
    z_achsen = []
    stumm = []
    genug = True
    for i in range(k):
        eintrag = zustand[("achse", PERCEPT_AXES[i])]
        sd = _sd(eintrag)
        if eintrag[0] < PERCEPT_MIN_N:
            genug = False
        if sd <= 0.0:
            stumm.append(PERCEPT_AXES[i])
            z_achsen.append(0.0)
        else:
            z_achsen.append((achsen[i] - eintrag[1]) / sd)
    warm = genug and len(stumm) < k

    signale = {}
    for cell in p7mod.CELLS:
        w = percept_projection(cell, k)
        roh = sum(w[i] * z_achsen[i] for i in range(k))
        schluessel = ("zelle", cell)
        zustand[schluessel] = _welford_schritt(zustand.get(schluessel, [0, 0.0, 0.0]), roh)
        eintrag = zustand[schluessel]
        sd = _sd(eintrag)
        if eintrag[0] < PERCEPT_MIN_N or sd <= 0.0:
            warm = False
            signale[cell] = None
        else:
            z = (roh - eintrag[1]) / sd
            # Logistik: (-inf,inf) -> (0,1), streng monoton, keine Kappung.
            # Randverteilung nahe uniform, weil z bereits standardisiert ist.
            signale[cell] = 1.0 / (1.0 + math.exp(-1.702 * z))

    for (art, schluessel), (n, mittel, m2) in zustand.items():
        conn.execute(
            "INSERT INTO f2_grid10_percept_calib "
            "(installation_id, art, schluessel, n, mittel, m2, aktualisiert, schema) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(installation_id, art, schluessel) DO UPDATE SET "
            "n=excluded.n, mittel=excluded.mittel, m2=excluded.m2, "
            "aktualisiert=excluded.aktualisiert",
            (installation_id, art, schluessel, n, mittel, m2, jetzt,
             SCHEMA_PERCEPT_CALIB_ZELLE if art == "zelle"
             else SCHEMA_PERCEPT_CALIB_MODELLACHSE
             if schluessel in PERCEPT_MODELL_ACHSEN
             else SCHEMA_PERCEPT_CALIB),
        )

    if not warm:
        grund = "hash_warmlauf" if not genug else "hash_alle_achsen_stumm"
        return None, grund, stumm
    return signale, "perzept", stumm


def fill_jspace(
    turn_event_id: str,
    seed_state: Mapping[str, float],
    *,
    kappa: float = p7mod.KAPPA,
    signal_overrides: Mapping[str, float] | None = None,
) -> JSpace:
    """J-Space befuellen: 10 GRID-Zellen erzeugen ihre Kandidaten
    (P7-Signal + P7-Proposal-Score), Competition = max, Selection = Winner,
    Broadcast = Winner-Score. Reine Funktion, kein I/O.

    ``kappa`` (F2WP1207 tune-passthrough, 2026-09-06): keyword-only override,
    default is p7mod's own module constant -- omitting it is byte-identical
    to before.

    ``signal_overrides`` (2026-09-07, percept passthrough): keyword-only,
    exactly the same shape and semantics as
    ``p7mod.run_coordination_cycle``'s parameter of the same name -- maps a
    subset of ``p7mod.CELLS`` to a signal in [0,1) that REPLACES
    ``derive_signal()``'s hash-noise for that cell, for this one call.
    ``None``/``{}`` is byte-identical to omitting it.

    WHY THIS EXISTS: the percept hook was added to
    ``p7mod.run_coordination_cycle`` on 2026-09-07, but the canonical turn
    loop does not call that function -- it re-implements the same
    competition here. Without this parameter the hook is unreachable from
    the only path that actually runs, so no real measurement could ever
    enter the competition. Measured before the fix: 208 frames, 100% of
    signals sha256 noise.

    NOTE the signal is now computed ONCE per cell and reused for both the
    ``signal`` field and ``proposal_score``. It used to be derived twice
    from the same inputs. That was harmless while it was a pure function of
    (turn_event_id, cell), and would have become a real defect the moment
    an override made the two call sites disagree -- the same
    one-value-computed-in-two-places shape as the opened_at ordering bug of
    2026-09-07."""
    signals = {cell: p7mod.derive_signal(turn_event_id, cell) for cell in p7mod.CELLS}
    if signal_overrides:
        for cell, value in signal_overrides.items():
            if cell in signals:
                signals[cell] = float(value)
    candidates = tuple(
        Candidate(
            cell_id=cell,
            signal=signals[cell],
            prior_state=float(seed_state.get(cell, 0.0)),
            proposal_score=p7mod.proposal_score(
                signals[cell],
                float(seed_state.get(cell, 0.0)),
                kappa=kappa,
            ),
        )
        for cell in p7mod.CELLS
    )
    winner = max(candidates, key=lambda c: c.proposal_score)
    return JSpace(
        turn_event_id=turn_event_id,
        candidates=candidates,
        winner_cell_id=winner.cell_id,
        broadcast_value=winner.proposal_score,
    )


def uptake_and_state(
    jspace: JSpace,
    *,
    lam: float = p7mod.LAMBDA_PRIMARY,
    alpha: float = p7mod.ALPHA,
    beta: float = p7mod.BETA,
    gamma: float = p7mod.GAMMA,
) -> tuple:
    """Uptake by all 10 Cells + new recurrent State (P7-Formulas,
    imported): state(t+1) = lambda*state + alpha*uptake + beta*broadcast
    - gamma*conflict. Winner uptake=1, Conflict by 0.05-Margin-Rule.
    Pure Function. Returns (transitions, new_state_map).

    ``lam``/``alpha``/``beta``/``gamma`` (F2WP1207 tune-passthrough,
    2026-09-06): keyword-only overrides, defaults are p7mod's own module
    constants -- omitting them is byte-identical to before."""
    transitions = []
    new_state = {}
    for cand in jspace.candidates:
        uptake = 1 if cand.cell_id == jspace.winner_cell_id else 0
        conflict = 1 if (
            cand.cell_id != jspace.winner_cell_id
            and abs(cand.proposal_score - jspace.broadcast_value) <= p7mod.CONFLICT_MARGIN
        ) else 0
        new = p7mod.state_update(
            cand.prior_state,
            uptake,
            jspace.broadcast_value if uptake else 0.0,
            conflict,
            lam=lam,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )
        new_state[cand.cell_id] = new
        transitions.append({
            "cell_id": cand.cell_id, "signal": cand.signal,
            "old_state": cand.prior_state, "proposal_score": cand.proposal_score,
            "uptake": uptake, "conflict": conflict, "new_state": new,
        })
    return tuple(transitions), new_state


# --------------------------------------------------------------------------
# Effect (P11-Gate-Schicht importiert, Journal-Row in DIESER Transaktion)
# --------------------------------------------------------------------------


def _submit_effect_in_transaction(
    conn: sqlite3.Connection,
    turn: p7mod.RealTurn,
    *,
    jspace: JSpace,
    policy: "p11mod.EffectGatePolicy",
) -> dict:
    """P11-Gate (evaluate_gate, imported, pure) + Journal-Row with P11's
    Columns/Schema-Tags -- here inside the atomic Turn-Transaction, because
    P11's own submit_effect_request commits itself. Structural Law
    unchanged: EXECUTED only with real ALLOW-Decision for the request_id,
    DENY is visibly journaled. Readback (re-SELECT) in the same Block."""
    request_id = uuid.uuid4().hex
    marker_text = (
        f"P11 journal marker (canonical turn loop): winner={jspace.winner_cell_id} "
        f"broadcast_value={jspace.broadcast_value:.6f} "
        f"condition_key={CONDITION_KEY} turn_event_id={turn.turn_event_id}"
    )
    request = p11mod.EffectRequest(
        schema=p11mod.SCHEMA_REQUEST,
        request_id=request_id,
        effect_type=p11mod.EffectType.JOURNAL_MARKER,
        turn=turn,
        condition_key=CONDITION_KEY,
        winner_cell_id=jspace.winner_cell_id,
        broadcast_value=jspace.broadcast_value,
        payload={"marker_text": marker_text},
        requested_at=_jetzt_iso(),
    )
    decision = p11mod.evaluate_gate(request, policy)
    journal_id = uuid.uuid4().hex
    now = _jetzt_iso()
    status = "EXECUTED" if decision.allowed else "DENIED"
    conn.execute(
        "INSERT INTO f2_grid10_effect_journal "
        "(journal_id, request_id, effect_type, schema, frame_id, turn_event_id, "
        " runtime_epoch_id, session_id, condition_key, winner_cell_id, broadcast_value, "
        " payload_json, gate_policy_id, gate_min_broadcast_value, gate_allowed, gate_reason, "
        " gate_decided_at, status, executed_marker_text, executed_at, readback_ok, "
        " readback_row_hash, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            journal_id, request_id, request.effect_type.value, p11mod.SCHEMA_JOURNAL_ROW,
            turn.frame_id, turn.turn_event_id, turn.runtime_epoch_id, turn.session_id,
            CONDITION_KEY, jspace.winner_cell_id, jspace.broadcast_value,
            _canonical_json(dict(request.payload)), decision.policy_id,
            decision.min_broadcast_value, 1 if decision.allowed else 0, decision.reason,
            decision.decided_at, status,
            marker_text if decision.allowed else None,
            now if decision.allowed else None, None, None, now,
        ),
    )
    row = conn.execute(
        "SELECT status, executed_marker_text, request_id FROM f2_grid10_effect_journal "
        "WHERE journal_id=?", (journal_id,),
    ).fetchone()
    readback_ok = (
        row is not None and row[0] == status
        and (status == "DENIED" or row[1] == marker_text)
        and row[2] == request_id
    )
    row_hash = p11mod._row_hash(journal_id, status, marker_text if decision.allowed else None)
    conn.execute(
        "UPDATE f2_grid10_effect_journal SET readback_ok=?, readback_row_hash=? "
        "WHERE journal_id=?",
        (1 if readback_ok else 0, row_hash, journal_id),
    )
    return {
        "journal_id": journal_id,
        "request_id": request_id,
        "policy_id": policy.policy_id,
        "allowed": bool(decision.allowed),
        "status": status,
        "readback_ok": bool(readback_ok),
        "gate_reason": decision.reason,
        "uptake_delta": p11mod.effect_uptake_delta(
            p11mod.EffectOutcome(
                request=request, decision=decision, executed=decision.allowed,
                journal_id=journal_id,
                readback_ok=(bool(readback_ok) if decision.allowed else None),
                readback_row=None,
            )
        ),
    }


# --------------------------------------------------------------------------
# Der kanonische Turn
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalTurnResult:
    schema: str
    frame_id: str
    turn_event_id: str
    runtime_epoch_id: str
    session_id: str
    reentry: ReentryPlan
    jspace: JSpace
    transitions: tuple
    new_state: Mapping[str, float]
    pointer_id: str
    effect: Optional[dict]
    self_observation: Optional[dict]
    grf_projection: Optional[Mapping[str, object]] = None


def run_canonical_turn(
    conn: sqlite3.Connection,
    typed_entry: TypedEntry | Mapping,
    *,
    declared_reentry: Optional[str] = None,
    effect_policy: Optional["p11mod.EffectGatePolicy"] = None,
    include_self_observation: bool = False,
    evidence_path: Optional[Path] = None,
    env: Mapping[str, str] | None = None,
    crash_hook: Optional[Callable[[str], None]] = None,
    tune: Optional[Mapping[str, float]] = None,
    signal_overrides: Optional[Mapping[str, float]] = None,
    grf_input: Optional[Mapping[str, object]] = None,
) -> Optional[CanonicalTurnResult]:
    """User's Chain, 1:1, everything in ONE Transaction.

    Gate OFF -> None, BEFORE any I/O happens (Zero-Behavior-Delta).
    crash_hook: ONLY for Tests -- called after Frame-INSERT, before COMMIT,
    with a Label (Proof of Kill-mid-turn).
    Errors of any Kind -> Rollback + Raise (Fail-Closed, no Swallowing).

    ``tune`` (F2WP1207 tune-passthrough, 2026-09-06): optional dict, keys
    ``kappa``/``lam``/``alpha``/``beta``/``gamma`` (p7mod's own parameter
    names), forwarded per-call into ``fill_jspace``/``uptake_and_state``.
    ``None``/``{}`` -> both calls use p7mod's own module-constant defaults,
    byte-identical to before this parameter existed. Purely a local dict
    read once per call -- no module constant is ever mutated, so there is
    no leakage into the next call in the same process.

    ``signal_overrides`` (2026-09-07, percept passthrough): optional mapping
    cell -> signal in [0,1), forwarded into ``fill_jspace``. ``None``/``{}``
    is byte-identical to before. Deliberately NOT a key inside ``tune``:
    ``tune`` carries competition *constants* and is written to
    f2_grid10_tune_audit as a tuning change; a percept is a measured *input*
    and would be mislabelled there. Tune says how the competition weighs;
    a percept says what it weighs.

    ``grf_input`` is a typed OMEGA GRF cognition input. It is mutually
    exclusive with opaque ``signal_overrides`` and requires an explicit
    TypedEntry.turn_event_id so capsule, projection and canonical turn cannot
    drift. Its capsule/projection are persisted atomically with the frame and
    pointer for forensic reconstruction. GRF grants no truth/effect authority."""
    if isinstance(typed_entry, Mapping):
        typed_entry = TypedEntry.from_mapping(typed_entry)
    if grf_input is not None and not typed_entry.turn_event_id:
        raise CanonicalTurnLoopError(
            "GRF-bound turn requires explicit turn_event_id for exact causal binding"
        )
    if grf_input is not None and signal_overrides is not None:
        raise CanonicalTurnLoopError(
            "grf_input and signal_overrides are mutually exclusive cognition inputs"
        )
    if declared_reentry is not None and declared_reentry not in _REENTRY_KINDS:
        raise CanonicalTurnLoopError(
            f"declared_reentry={declared_reentry!r} ungueltig, erlaubt: {_REENTRY_KINDS}"
        )

    # --- Gate VOR jedem I/O ---------------------------------------------
    environ = env if env is not None else os.environ
    override = environ.get(ENV_OVERRIDE)
    if override not in ("0", "1"):
        try:
            row = conn.execute(
                "SELECT wert FROM star_konfig WHERE schluessel=?", (KONFIG_KEY,)
            ).fetchone()
            if not row or row[0] != "1":
                return None
        except sqlite3.Error:
            return None
    elif override == "0":
        return None

    ensure_schema(conn)

    # Create percept schema only when the percept gate is ON -- gate OFF
    # still means: no table, no write operation, no delta.
    # Before BEGIN IMMEDIATE, so that no DDL lies in the turn transaction.
    _percept_an = percept_active(conn, env=environ)
    if _percept_an:
        ensure_percept_schema(conn)
        conn.commit()
    if grf_input is not None:
        ensure_grf_schema(conn)
        conn.commit()

    conn.execute("BEGIN IMMEDIATE")
    try:
        # --- Identity: the epoch of TypedEntry carries Installation/   -
        # StateRoot (f2_runtime_epoch) -- no cross product over the
        # Identity-Tabellen, damit mehrere Installationen je DB korrekt sind.
        runtime_epoch_id = typed_entry.runtime_epoch_id
        epoch = conn.execute(
            "SELECT installation_id, state_root_id FROM f2_runtime_epoch "
            "WHERE runtime_epoch_id=?",
            (runtime_epoch_id,),
        ).fetchone()
        if epoch is None:
            raise CanonicalTurnLoopError(
                f"runtime_epoch_id={runtime_epoch_id} existiert nicht in f2_runtime_epoch"
            )
        installation_id, state_root_id = epoch[0], epoch[1]
        entity_row = conn.execute(
            "SELECT entity_id FROM f2_installation_identity WHERE installation_id=?",
            (installation_id,),
        ).fetchone()
        if entity_row is None:
            raise CanonicalTurnLoopError(
                f"installation_id={installation_id} fehlt in f2_installation_identity"
            )
        entity_id = entity_row[0]

        turn_event_id = typed_entry.turn_event_id or _mint_turn_event_id(
            conn, typed_entry.session_id
        )
        frame_id = hashlib.sha256(
            f"{runtime_epoch_id}:{turn_event_id}".encode()
        ).hexdigest()
        turn = p7mod.RealTurn(
            frame_id=frame_id,
            turn_event_id=turn_event_id,
            runtime_epoch_id=runtime_epoch_id,
            session_id=typed_entry.session_id,
        )
        ts = typed_entry.ts or _jetzt_iso()

        # --- GRF cognition input: exact same-turn compile + projection ---
        _grf_capsule = None
        _grf_projection = None
        if grf_input is not None:
            try:
                import omega_grf_brain as grfmod
                _grf_capsule = grfmod.compile_capsule(
                    grf_input, expected_turn_id=turn_event_id
                )
                _grf_projection = grfmod.project_grid_signals(
                    _grf_capsule,
                    turn_event_id=turn_event_id,
                    cells=tuple(p7mod.CELLS),
                )
            except Exception as exc:
                raise CanonicalTurnLoopError(
                    f"GRF cognition input rejected: {exc}"
                ) from exc

        # --- zwingender Reentry -----------------------------------------
        reentry = resolve_reentry(
            conn, typed_entry, installation_id, state_root_id,
            declared=declared_reentry,
        )

        # --- optional P12 (kein Kettenglied, default AUS) ----------------
        self_observation = None
        seed_state = dict(reentry.seed_state)
        if include_self_observation:
            observations = _collect_observations(conn, turn)
            seed_state, delta, contributions = _apply_observations(
                seed_state, observations
            )
            self_observation = {
                "n_observations": len(observations),
                "delta": delta,
                "contributions": contributions,
            }

        # --- Perzepte: echte Messung statt sha256-Rauschen ---------------
        # Ein ausdruecklich uebergebenes signal_overrides gewinnt IMMER --
        # der Parameter behaelt seine Bedeutung, Perzepte draengen sich
        # no caller. During warmup,
        # derive_percept_signals() returns None: then exactly the previous
        # hash competition runs, and only the calibration learns.
        _percept_achsen = None
        _percept_signale = None
        _percept_quelle = None
        _percept_stumm = []
        if _percept_an and not signal_overrides and grf_input is None:
            _percept_achsen = percept_axes(
                typed_entry, ts,
                vorher_ts=(reentry.evidence or {}).get("pointer_created_at"),
            )
            _percept_signale, _percept_quelle, _percept_stumm = (
                derive_percept_signals(
                    conn, installation_id, _percept_achsen, jetzt=ts
                )
            )

        # --- J-Space befuellen -> 10 Kandidaten --------------------------
        _tune = tune or {}
        _jspace_kwargs = {k: _tune[k] for k in ("kappa",) if k in _tune}
        if signal_overrides:
            _jspace_kwargs["signal_overrides"] = signal_overrides
        elif _grf_projection is not None:
            _jspace_kwargs["signal_overrides"] = _grf_projection["signal_overrides"]
        elif _percept_signale:
            _jspace_kwargs["signal_overrides"] = _percept_signale
        jspace = fill_jspace(turn_event_id, seed_state, **_jspace_kwargs)

        # --- Uptake durch alle 10 + neuer rekurrenter State --------------
        _uptake_kwargs = {k: _tune[k] for k in ("lam", "alpha", "beta", "gamma") if k in _tune}
        transitions, new_state = uptake_and_state(jspace, **_uptake_kwargs)

        # --- Workspace/J-Space Update + atomarer Persist -----------------
        # Frame oeffnen (INNERHALB der Turn-Transaktion)
        conn.execute(
            "INSERT INTO f2_grid10_frame "
            "(frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id, "
            " session_id, turn_event_id, opened_at, closed_at, status, schema, cohort, "
            " experiment_condition, state_weight) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id,
                typed_entry.session_id, turn_event_id, ts, None, "OPEN", SCHEMA_FRAME,
                COHORT, CONDITION_KEY, 1.0,
            ),
        )
        # Perzept-Protokoll: WAS gemessen wurde und WELCHES Signal daraus
        # was done, per turn, in the same transaction as the frame. Without this
        # Zeile waere der Wettbewerb wieder unpruefbar -- f2_grid10_frame hat
        # no column for the measurement, and the pointer is overwritten every turn.
        # Exactly this caused the reconstruction of the
        # bisherigen 216 Frames.
        if _percept_achsen is not None:
            conn.execute(
                "INSERT INTO f2_grid10_percept "
                "(frame_id, installation_id, turn_event_id, ts, quelle, "
                " achsen_json, signale_json, stumme_achsen, schema) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    frame_id, installation_id, turn_event_id, ts, _percept_quelle,
                    _canonical_json({
                        PERCEPT_AXES[i]: _percept_achsen[i]
                        for i in range(len(_percept_achsen))
                    }),
                    _canonical_json(_percept_signale) if _percept_signale else None,
                    ",".join(_percept_stumm) if _percept_stumm else None,
                    SCHEMA_PERCEPT,
                ),
            )

        if _grf_projection is not None and _grf_capsule is not None:
            conn.execute(
                "INSERT INTO f2_grid10_grf_projection "
                "(frame_id, turn_event_id, runtime_epoch_id, capsule_digest, "
                " projection_digest, grf_definition_digest, capsule_json, "
                " projection_json, schema, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    frame_id, turn_event_id, runtime_epoch_id,
                    _grf_capsule["capsule_digest"],
                    _grf_projection["projection_digest"],
                    _grf_projection["grf_definition_digest"],
                    _canonical_json(_grf_capsule),
                    _canonical_json(_grf_projection),
                    SCHEMA_GRF_PROJECTION_ROW, ts,
                ),
            )

        if crash_hook is not None:
            crash_hook("after_frame_open")

        # 10 Zell-Beobachtungen (execution_position: Liveweg-Konvention,
        # deterministisch pseudozufaellig aus frame_id; timing_ms bewusst
        # NULL -- hier wird nichts gemessen/erfunden)
        zellen = list(p7mod.CELLS)
        random.Random(frame_id).shuffle(zellen)
        reentry_flag = 0 if reentry.kind == "genesis" else 1
        for pos, cell in enumerate(zellen, start=1):
            t = next(x for x in transitions if x["cell_id"] == cell)
            conn.execute(
                "INSERT INTO f2_grid10_cell_observation "
                "(observation_id, frame_id, logical_cell_id, input_digest_sha256, "
                " output_digest_sha256, uptake, reentry_flag, conflict_flag, timing_ms, "
                " cpu_ru_utime_delta_s, rss_delta_kb, predecessor_observation_id, schema, "
                " execution_position) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hashlib.sha256(f"{frame_id}:{cell}".encode()).hexdigest(),
                    frame_id, cell,
                    hashlib.sha256(f"{turn_event_id}:{cell}:in".encode()).hexdigest(),
                    hashlib.sha256(f"{turn_event_id}:{cell}:out".encode()).hexdigest(),
                    t["uptake"], reentry_flag, t["conflict"],
                    None, None, None, None, SCHEMA_CELL_OBS, pos,
                ),
            )

        # 10 rekurrente Zellzustaende (eigene Lane)
        for cell in p7mod.CELLS:
            conn.execute(
                "INSERT INTO f2_grid10_p6d_state "
                "(condition_key, logical_cell_id, state_value, updated_at, "
                " updated_by_frame_id, won_broadcast_count, schema) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(condition_key, logical_cell_id) DO UPDATE SET "
                "state_value=excluded.state_value, updated_at=excluded.updated_at, "
                "updated_by_frame_id=excluded.updated_by_frame_id, "
                "won_broadcast_count=won_broadcast_count + (CASE WHEN ?=? THEN 1 ELSE 0 END)",
                (
                    CONDITION_KEY, cell, new_state[cell], ts, frame_id,
                    1 if cell == jspace.winner_cell_id else 0, SCHEMA_STATE_ROW,
                    cell, jspace.winner_cell_id,
                ),
            )

        # Frame schliessen + Broadcast (Workspace-Update, P10-lesbar)
        conn.execute(
            "UPDATE f2_grid10_frame SET status='CLOSED', closed_at=?, "
            "broadcast_winner_cell=?, broadcast_value=? WHERE frame_id=?",
            (_jetzt_iso(), jspace.winner_cell_id, jspace.broadcast_value, frame_id),
        )

        # optionaler Effect (P11-Gate-Schicht, gleiche Transaktion)
        effect = None
        if effect_policy is not None:
            effect = _submit_effect_in_transaction(
                conn, turn, jspace=jspace, policy=effect_policy
            )
            # P11's uptake-Delta: belegte Ausfuehrung +epsilon auf Winner-State
            if effect["uptake_delta"]:
                conn.execute(
                    "UPDATE f2_grid10_p6d_state SET state_value=state_value+? "
                    "WHERE condition_key=? AND logical_cell_id=?",
                    (effect["uptake_delta"], CONDITION_KEY, jspace.winner_cell_id),
                )
                new_state = dict(new_state)
                new_state[jspace.winner_cell_id] = (
                    new_state[jspace.winner_cell_id] + effect["uptake_delta"]
                )

        # Reentry pointer = EXACTLY the entry point of the next turn
        pointer_id = uuid.uuid4().hex
        evidence = dict(reentry.evidence)
        evidence["resolved_kind"] = reentry.kind
        evidence["typed_entry"] = typed_entry.to_payload()
        if effect is not None:
            evidence["effect_journal_id"] = effect["journal_id"]
        if _grf_projection is not None and _grf_capsule is not None:
            evidence["grf"] = {
                "schema": SCHEMA_GRF_PROJECTION_ROW,
                "capsule_digest": _grf_capsule["capsule_digest"],
                "projection_digest": _grf_projection["projection_digest"],
                "grf_definition_digest": _grf_projection["grf_definition_digest"],
            }
        conn.execute(
            "INSERT INTO f2_grid10_turn_pointer (pointer_id, installation_id, state_root_id, "
            " runtime_epoch_id, session_id, frame_id, turn_event_id, reentry_kind_used, "
            " reentry_evidence_json, broadcast_winner_cell, broadcast_value, cell_states_json, "
            " persist_schema, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(installation_id, state_root_id) DO UPDATE SET "
            "pointer_id=excluded.pointer_id, runtime_epoch_id=excluded.runtime_epoch_id, "
            "session_id=excluded.session_id, frame_id=excluded.frame_id, "
            "turn_event_id=excluded.turn_event_id, reentry_kind_used=excluded.reentry_kind_used, "
            "reentry_evidence_json=excluded.reentry_evidence_json, "
            "broadcast_winner_cell=excluded.broadcast_winner_cell, "
            "broadcast_value=excluded.broadcast_value, "
            "cell_states_json=excluded.cell_states_json, "
            "persist_schema=excluded.persist_schema, created_at=excluded.created_at",
            (
                pointer_id, installation_id, state_root_id, runtime_epoch_id,
                typed_entry.session_id, frame_id, turn_event_id, reentry.kind,
                _canonical_json(evidence), jspace.winner_cell_id, jspace.broadcast_value,
                _canonical_json({c: new_state[c] for c in p7mod.CELLS}),
                SCHEMA_POINTER_ROW, _jetzt_iso(),
            ),
        )

        if crash_hook is not None:
            crash_hook("before_commit")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

    if evidence_path is not None:
        _append_log(evidence_path, {
            "schema": SCHEMA_LOG_LINE,
            "ts": _jetzt_iso(),
            "frame_id": frame_id,
            "turn_event_id": turn_event_id,
            "runtime_epoch_id": runtime_epoch_id,
            "session_id": typed_entry.session_id,
            "reentry_kind": reentry.kind,
            "reentry_evidence": dict(reentry.evidence),
            "winner_cell_id": jspace.winner_cell_id,
            "broadcast_value": jspace.broadcast_value,
            "transitions": [dict(t) for t in transitions],
            "effect": effect,
            "self_observation": self_observation,
            "grf": evidence.get("grf"),
            "pointer_id": pointer_id,
        })
    return CanonicalTurnResult(
        schema=SCHEMA,
        frame_id=frame_id,
        turn_event_id=turn_event_id,
        runtime_epoch_id=runtime_epoch_id,
        session_id=typed_entry.session_id,
        reentry=reentry,
        jspace=jspace,
        transitions=transitions,
        new_state=new_state,
        pointer_id=pointer_id,
        effect=effect,
        self_observation=self_observation,
        grf_projection=_grf_projection,
    )


def _mint_turn_event_id(conn: sqlite3.Connection, session_id: str) -> str:
    """Liveweg-Konvention: {session_id}:{n}, n = bestehende Frames der
    Session + 1 (innerhalb BEGIN IMMEDIATE konkurrenzfrei)."""
    n = conn.execute(
        "SELECT COUNT(*) FROM f2_grid10_frame WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    return f"{session_id}:{n + 1}"


def _collect_observations(conn: sqlite3.Connection, turn):
    try:
        import f2wp1207_p12_self_observation as p12mod  # vendored copy, same dir
        return p12mod.collect_self_observations(conn, turn)
    except Exception:
        return []


def _apply_observations(seed_state, observations):
    try:
        import f2wp1207_p12_self_observation as p12mod
        return p12mod.apply_self_observation(
            seed_state, observations, threshold_s=p12mod.DEFAULT_STALE_THRESHOLD_S
        )
    except Exception:
        return dict(seed_state), 0.0, []


def _append_log(evidence_path: Path, line: dict) -> None:
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "a", encoding="utf-8") as f:
        f.write(_canonical_json(line) + "\n")
