#!/usr/bin/env python3
"""star_cycle.py -- session cycle + effect gate + room + governance, PORTED
from the ARCH-import donor star_cli.py (peer A, 2026-10-01) by AST extraction.

Function bodies verbatim, except: owner display name = generic friend.
Helpers (DB connect, _uid, _now, _short, _config, USER_ID ...) come from
star_core.py, so there is ONE DB path and ONE identity.

What this adds to the hook engine (all local, fail-silent, no network, no LLM):
  SessionStart      cycle_open (users/sessions/turns/workspace_episodes/
                    active_turns/checkpoints) + room_join_and_pulse
  UserPromptSubmit  room_pulse_renew, room messages, governance signal
  PreToolUse        allow  (effect gate = BOOKKEEPING, never blocks)
  PostToolUse       remember    (event trail, effects verify, causal_episodes,
                    leases) + _i_do (activity trail)
  Stop              cycle_close, architect_governance_move
  SessionEnd        cycle_close, room_leave
Hard limits kept from donor: no LLM call in a hook, fail-silent, exit 0.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import random
import re
import signal
import sqlite3
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import star_core as _core_mod

# Bring every helper/constant of star_core into this namespace (one DB, one
# identity). Names defined in this file below override on purpose.
for _n, _v in vars(_core_mod).items():
    if not _n.startswith("__") and _n not in globals():
        globals()[_n] = _v


# ── Secret redaction (Security addendum to PHASE 18, 2026-08-26) ──────
# Real, demonstrated leak: EffectGate/event trail (allow()/remember(),
# below) write tool_input/argv/target (incl. Bash-`command`, Write/Edit-
# `content`) UNFILTERED into effects/durable_memory. Every secret that ever
# via a Bash argument text or a file content runs, ended up
# permanently in plaintext in unified.db -- independent of the vault (PHASE 18),
# whose own gpg calls the passphrase PROVABLY via `--passphrase-fd`
# (own pipe, no argv, see _gpg_run()) passed and therefore itself
# are NOT affected. Primary defense per vault onboarding: human types
# secrets in own terminal, never via model-controlled Bash call.
# This function is the SECONDARY, defense-in-depth defense: secret-like
# substrings are redacted BEFORE writing, regardless of how the
# secret entered the call. Only values are replaced (marker
# "[REDACTED]"), the rest of the line stays readable -- no blackout of the
# entire log entry. Order matters: specific patterns (known
# prefixes, named flags/env assignments) first, generic high-entropy-
# catcher last (it would otherwise e.g. not hit the marker itself, but
# could distort already redacted remnants differently).
_SECRET_PREFIX_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{10,}|gsk_[A-Za-z0-9_\-]{10,}|gh[pousr]_[A-Za-z0-9_\-]{10,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})\b"
)


_SECRET_BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{10,}")


# Named flags (--password, --passphrase, --token, --api-key, --secret, ...):
# flag name stays visible, only the value behind it gets redacted.
_SECRET_FLAG_PATTERN = re.compile(
    r"(?i)((?:--)?(?:passphrase|password|pass|api[-_]?key|apikey|token|secret)\s*[=: ]\s*)(\S+)"
)


# Env assignment style (UPPERCASE deliberately mandatory -- reduces false positives
# in normal flowing text): PASSWORD=..., API_KEY=..., TOKEN=..., SECRET=...
_SECRET_ENV_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSPHRASE)[A-Z0-9_]*=)(\S+)"
)


# mysql-style "-p <value>" -- ONLY if value mixed letter+digit AND
# >=6 characters, otherwise too many false positives on -p as port/parallelism.
_SECRET_MYSQLP_PATTERN = re.compile(r"(-p\s+)((?=\S*[0-9])(?=\S*[A-Za-z])\S{6,})")


# Generic high-entropy block: >=20 chars [A-Za-z0-9_-], letter AND
# digit mixed (discards pure word sequences and pure digit sequences) --
# catches Base64/hex blobs and raw passwords without known prefix, e.g.
# in `printf '...' | ...`-Pipes.
_SECRET_BLOB_PATTERN = re.compile(
    r"\b(?=[A-Za-z0-9_\-]{20,}\b)(?=[A-Za-z0-9_\-]*[0-9])(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{20,}\b"
)


def _gm_redact_obj(o):
    """Write-redaction (secret_pattern.py); fail-closed: without module -> placeholder."""
    try:
        import secret_pattern as _gm
        return _gm.redact_obj(o)
    except Exception:
        return "[REDACTED:module-missing]"


def _secret_edit(text: str) -> str:
    """Redacts secret-like substrings from `text`, replacing them with
    "[REDACTED]". Non-strings/empty values are returned unchanged.
    Order: known prefixes -> Bearer -> named flags -> env-style ->
    mysql `-p` -> generic high-entropy catcher."""
    if not isinstance(text, str) or not text:
        return text
    s = text
    s = _SECRET_PREFIX_PATTERN.sub("[REDACTED]", s)
    s = _SECRET_BEARER_PATTERN.sub("Bearer [REDACTED]", s)
    s = _SECRET_FLAG_PATTERN.sub(r"\1[REDACTED]", s)
    s = _SECRET_ENV_PATTERN.sub(r"\1[REDACTED]", s)
    s = _SECRET_MYSQLP_PATTERN.sub(r"\1[REDACTED]", s)
    s = _SECRET_BLOB_PATTERN.sub("[REDACTED]", s)
    return s


def _short_edited(value, n: int = 220) -> str:
    """Like _short(), but redacts secrets BEFORE truncating (a secret that
    lies exactly at the truncation boundary must not slip through as an
    unrecognized remainder). Only use at sites that write tool_input/argv/target/
    tool_response in effects/durable_memory -- _short() itself remains
    unchanged for all other (non-secret-suspect) callers."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    s = str(value if value is not None else "").replace("\n", " ").strip()
    s = _secret_edit(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _argv_normalized_edited(tool_input) -> str:
    """_argv_normalized() + secret redaction BEFORE truncating to 500 chars
    (see _short_edited() rationale)."""
    return _secret_edit(_argv_normalized(tool_input))[:500]


# ═══════════════════════════════════════════════════════════════════════
# SECTION: SESSION_CYCLE -- verbatim from udb/bridge.py (users/sessions/
# turns/workspace_episodes/active_turns, Injection protocol checkpoints).
# ═══════════════════════════════════════════════════════════════════════
def _owner_name() -> str:
    try:
        import frank_profile as _fpm
        return _fpm.name()
    except Exception:
        return "friend"


def _ensure_user(c) -> None:
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, display_name, rights) VALUES (?,?,?)",
        (USER_ID, _owner_name(), "owner"),
    )


def cycle_open(session_id: str, model: str) -> Optional[str]:
    """Opens the session cycle. Returns the episode_id (or None).

    PHASE 2 (ZECP17): sessions.generation is REAL from here on -- no longer
    hardcoded 1. cycle_open is called exclusively at SessionStart with
    source='startup' per cmd_hook() (see branching there);
    the ON CONFLICT here therefore increments exactly at every 'startup' event,
    as required in the concept document PHASE 2 ("incremented at every
    SessionStart with source='startup'"). A brand-new session_id stays
    at generation 1 (INSERT branch fires, no conflict); a repeated
    'startup' for the same session_id (e.g. terminal reconnected, same
    ID resumed) increments -- exactly the case that the new
    PreToolUse admission check below should detect as "stale generation"
    when an effect is still triggered from the old count."""
    try:
        with contextlib.closing(write_connection()) as c:
            _ensure_user(c)
            now = _now()
            c.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, updated_at, "
                "generation, terminal_name) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "generation = sessions.generation + 1, updated_at = excluded.updated_at",
                (session_id, USER_ID, now, now, 1, f"claude-code:{session_id}"),
            )
            generation = (
                c.execute("SELECT generation FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                or (1,)
            )[0]

            turn_id = _uid("t-open")
            ordinal = _next_ordinal(c, session_id)
            c.execute(
                "INSERT INTO turns (turn_id, session_id, user_id, ordinal, ts, role, "
                "content, fidelity, compression_generation, resource_refs, causal_refs, "
                "provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn_id, session_id, USER_ID, ordinal, now, "system",
                    "[Session marker: cycle opened via star_cli.py -- not a real "
                    "Transcript captured, only margin marker]",
                    "marker", 0, "[]", "[]",
                    json.dumps({"source": "star_cli.py", "model": model}, ensure_ascii=False),
                ),
            )
            episode_id = _uid("ep")
            c.execute(
                "INSERT INTO workspace_episodes (episode_id, session_id, ts, "
                "observation_turn_id, salience, alternatives, selected, state) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (episode_id, session_id, now, turn_id, 1.0, "[]", None, "open"),
            )
            causal_id = _uid("c")
            c.execute(
                "INSERT OR REPLACE INTO active_turns (session_id, user_id, turn_id, "
                "episode_id, causal_id, generation, resource_refs, effect_id, outcome, "
                "workspace_selected, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, USER_ID, turn_id, episode_id, causal_id, generation, "[]", None, None, 0, now),
            )
            c.commit()
            return episode_id
    except Exception as e:
        _log(f"cycle_open error sid={session_id}: {e}")
        return None


def cycle_close(session_id: str) -> None:
    try:
        with contextlib.closing(write_connection()) as c:
            row = c.execute(
                "SELECT episode_id FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            now = _now()
            ordinal = _next_ordinal(c, session_id)
            turn_id = _uid("t-close")
            c.execute(
                "INSERT INTO turns (turn_id, session_id, user_id, ordinal, ts, role, "
                "content, fidelity, compression_generation, resource_refs, causal_refs, "
                "provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn_id, session_id, USER_ID, ordinal, now, "system",
                    "[Session marker: Cycle closed via star_cli.py]",
                    "marker", 0, "[]", "[]",
                    json.dumps({"source": "star_cli.py"}, ensure_ascii=False),
                ),
            )
            if row and row[0]:
                c.execute(
                    "UPDATE workspace_episodes SET state='closed' WHERE episode_id=?",
                    (row[0],),
                )
            c.execute(
                "UPDATE active_turns SET outcome='closed' WHERE session_id=?",
                (session_id,),
            )
            c.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (now, session_id))
            c.commit()
    except Exception as e:
        _log(f"cycle_close error sid={session_id}: {e}")
    _checkpoint("Stop/SessionEnd", session_id, "-", "close", "")


def _checkpoint(event: str, session_id: str, model: str, phase: str, injected_text: str) -> str:
    digest_source = injected_text if injected_text else f"{phase}:{event}:{session_id}"
    state_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    note = json.dumps(
        {
            "phase": phase, "event": event, "session_id": session_id, "model": model,
            "capsule_length": len(injected_text) if injected_text else 0,
            "capsule_beginning": _short(injected_text, 160) if injected_text else None,
        },
        ensure_ascii=False, separators=(",", ":"),
    )
    cp_id = _uid(f"udb-{phase}")
    try:
        with contextlib.closing(write_connection()) as c:
            c.execute(
                "INSERT OR REPLACE INTO checkpoints (checkpoint_id, ts, state_hash, note) "
                "VALUES (?, ?, ?, ?)",
                (cp_id, _now(), state_hash, note),
            )
            c.commit()
    except Exception as e:
        _log(f"checkpoint error phase={phase} sid={session_id}: {e}")
    return state_hash


# ═══════════════════════════════════════════════════════════════════════
# SECTION: EFFECTGATE -- ZECP17, PHASE 2. Two sides of an effect:
# allow() (PreToolUse, approval BEFORE execution) and the verification
# in remember() (PostToolUse, afterwards). Before there was only the second half --
# a retrospective protocol, not a gate (see docstring of this file/
# Concept document PHASE 2: "today's EffectGate isn't one at all").
#
# NON-NEGOTIABLE: allow() NEVER blocks a tool. There is in
# this entire file no code path that from a PreToolUse hook a
# "deny"/"block" back to Claude Code -- cmd_hook() prints for
# PreToolUse nothing at all to stdout (see there). In doubt,
# Timeout or error writes status='UNCHECKED' (or,
# if even that no longer succeeds in time, nothing at all) -- the
# Tool runs in any case. The existing, older BLOCKING
# Guardian (~/aicore/opt/aicore/tools/schranke/wache-koenig.py, global
# settings.json) remains untouched; this section is additional, purely
# bookkeeping logic in the STAR-scoped settings.json. Related, but
# a different category than the LEASES below (P5d): Leases are
# collision NOTIFICATION between sessions, EffectGate is bookkeeping FOR
# a single effect (admission -> verification), neither blocks.
# ═══════════════════════════════════════════════════════════════════════
STATE_CHANGING = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}


def _effect_goal(tool_input, tool_name: str) -> str:
    if not isinstance(tool_input, dict):
        return "?"
    return (
        tool_input.get("file_path") or tool_input.get("notebook_path")
        or tool_input.get("command") or "?"
    )


def _is_faulty(tool_response) -> bool:
    if isinstance(tool_response, dict):
        return bool(tool_response.get("is_error") or tool_response.get("error"))
    if isinstance(tool_response, str):
        return tool_response.strip().lower().startswith(("error", "fehler"))  # lang-data:de (German tool error prefix)
    return False


def _argv_normalized(tool_input) -> str:
    """Canonical form for the idempotency key -- sorted keys,
    no whitespace, so the same input always yields the same hash,
    regardless of key order in the incoming JSON."""
    try:
        return json.dumps(tool_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return _short(tool_input, 500)


def _idempotence_key(tool_name: str, target: str, tool_input) -> str:
    raw = f"{tool_name}|{target}|{_argv_normalized(tool_input)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_ability_table(c) -> None:
    """star_ability is initially a REGISTRATION, not a ban (PHASE 2,
    Check 1): unknown tools are automatically registered with allowed=1 on
    first admission check. A ban only arises when someone manually sets a
    line to 0 -- this phase itself never sets 0 (no credit/learning logic,
    that is P3)."""
    c.execute(
        "CREATE TABLE IF NOT EXISTS star_ability("
        "tool_name TEXT PRIMARY KEY, allowed INTEGER NOT NULL DEFAULT 1, "
        "reason TEXT, changed REAL NOT NULL)"
    )


def allow(payload: dict) -> None:
    """PreToolUse -- Admission. Budget 0.4s (star_config limit.PreToolUse),
    enforced by cmd_hook()'s SIGALRM, not here itself. Checks in
    fixed order: 1 Capability, 2 Generation, 3 Precondition,
    4 Idempotency -- and writes EXACTLY ONE effects row with the finding.
    The effect_id is stored in active_turns.effect_id (the already
    existing session-bound storage, one field per session) -- remember()
    (PostToolUse) reads it from there and updates the same row instead of
    creating a second one."""
    session_id = str(payload.get("session_id") or "unknown")
    tool_name = payload.get("tool_name") or "?"
    tool_input = payload.get("tool_input") or {}
    if tool_name not in STATE_CHANGING:
        return  # only state-changing tools get an EffectGate row

    target = _effect_goal(tool_input, tool_name)
    idem_key = _idempotence_key(tool_name, target, tool_input)

    try:
        with contextlib.closing(write_connection()) as c:
            _ensure_ability_table(c)

            # 1) Capability -- default: everything allowed (registration, no prohibition)
            row = c.execute(
                "SELECT approved FROM star_ability WHERE tool_name=?", (tool_name,)
            ).fetchone()
            if row is None:
                c.execute(
                    "INSERT OR IGNORE INTO star_ability (tool_name, approved, reason, changed) "
                    "VALUES (?,1,?,?)",
                    (tool_name, "auto-registered at first admission check", _now()),
                )
                capability_ok = True
            else:
                capability_ok = bool(row[0])

            # 2) Generation -- Session generation (sessions.generation) vs. the
            # Generation under which the current episode (active_turns) was
            # opened. If they differ, the episode is from a meanwhile via
            # new SessionStart(source=startup) superseded Count.
            srow = c.execute(
                "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            current_generation = srow[0] if srow else 1
            arow = c.execute(
                "SELECT episode_id, generation FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            episode_id = arow[0] if arow else None
            expected_generation = arow[1] if arow else current_generation
            generation_ok = (expected_generation == current_generation)

            # 3) Precondition -- for Edit/MultiEdit/NotebookEdit the target file
            # must exist, for Write at least the parent directory must exist.
            precondition_ok, precondition_reason = True, None
            if tool_name in ("Edit", "MultiEdit"):
                fp = tool_input.get("file_path") if isinstance(tool_input, dict) else None
                if not fp or not Path(fp).is_file():
                    precondition_ok = False
                    precondition_reason = f"Target file does not exist: {fp}"
            elif tool_name == "NotebookEdit":
                np_ = tool_input.get("notebook_path") if isinstance(tool_input, dict) else None
                if not np_ or not Path(np_).is_file():
                    precondition_ok = False
                    precondition_reason = f"Notebook does not exist: {np_}"
            elif tool_name == "Write":
                fp = tool_input.get("file_path") if isinstance(tool_input, dict) else None
                if fp and not Path(fp).parent.is_dir():
                    precondition_ok = False
                    precondition_reason = f"Parent folder missing: {Path(fp).parent}"
            # Bash has no file precondition -- stays ok.

            status, reason = "APPROVED", None
            if not capability_ok:
                status, reason = "REJECTED", "capability: tool locked in star_ability"
            elif not generation_ok:
                status, reason = (
                    "REJECTED",
                    f"generation outdated: Episode expects {expected_generation}, "
                    f"Session currently {current_generation}",
                )
            elif not precondition_ok:
                status, reason = "REJECTED", f"precondition: {precondition_reason}"
            else:
                # 4) Idempotence -- identical, already VERIFIED booked effect
                # in THE SAME session is marked, not blocked.
                # Search pattern deliberately ONLY on the quoted hash value, not on
                # the surrounding key/colon/Whitespace -- json.dumps()
                # without separators= sets a space after the colon
                # ("idempotence_key": "..."), a pattern with fixed
                # built-in "):" would be format-dependent and silently wrong
                # (found exactly like this on first build of this phase: no
                # duplicate was ever detected because the pattern never matched). The
                # hash itself is 64 hex characters -- as a substring practically
                # collision-free, a wrapper of quotation marks suffices.
                dup = c.execute(
                    "SELECT e.effect_id FROM effects e "
                    "JOIN workspace_episodes we ON we.episode_id = e.episode_id "
                    "WHERE we.session_id=? AND e.status='VERIFIED' "
                    "AND e.outcome LIKE ? LIMIT 1",
                    (session_id, f'%"{idem_key}"%'),
                ).fetchone()
                if dup:
                    status = "REPETITION"
                    reason = f"identical verified effect already present: {dup[0]}"

            outcome = {
                "phase": "approval",
                "idempotence_key": idem_key,
                "verifications": {
                    "capability": capability_ok, "generation": generation_ok,
                    "precondition": precondition_ok,
                },
            }
            if reason:
                outcome["reason"] = reason

            effect_id = _uid("eff")
            c.execute(
                "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                "target, argv, requested_generation, status, outcome, ts, verified_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    effect_id, episode_id, USER_ID, tool_name, _short_edited(target, 300),
                    _argv_normalized_edited(tool_input), current_generation, status,
                    json.dumps(outcome, ensure_ascii=False), _now(), None,
                ),
            )
            if arow is not None:
                c.execute(
                    "UPDATE active_turns SET effect_id=? WHERE session_id=?",
                    (effect_id, session_id),
                )
            c.commit()
    except Exception as e:
        # Fail-silent per hard limit 4 -- the tool runs either way
        # (cmd_hook() returns no decision for PreToolUse anyway).
        # Best-effort addendum: an UNTESTED row, if even that still
        # fits in the remaining time; if that also fails, the session simply remains
        # without admission line for this call -- remember() catches that below
        # als Fallback ab.
        _log(f"allow error sid={session_id} tool={tool_name}: {e}")
        try:
            with contextlib.closing(write_connection()) as c2:
                c2.execute(
                    "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                    "target, argv, requested_generation, status, outcome, ts, verified_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _uid("eff"), None, USER_ID, tool_name, _short_edited(target, 300),
                        _argv_normalized_edited(tool_input), 1, "UNTESTED",
                        json.dumps({"reason": f"check failed: {e}"}, ensure_ascii=False),
                        _now(), None,
                    ),
                )
                c2.commit()
        except Exception:
            pass  # even the addendum must never disturb a session


def _effect_check(tool_name: str, tool_input, tool_response) -> tuple:
    """PostToolUse -- the actual result, hashed (zeros pattern:
    {'ok':bool,'bytes':n,'sha256':...}) instead of truncated raw text.
    Returns (ok, outcome_object)."""
    faulty = _is_faulty(tool_response)
    if tool_name == "Bash":
        exit_code = None
        text = ""
        if isinstance(tool_response, dict):
            if "exit_code" in tool_response:
                exit_code = tool_response.get("exit_code")
            text = str(tool_response.get("stdout") or "") + str(tool_response.get("stderr") or "")
        else:
            text = str(tool_response or "")
        raw = text.encode("utf-8", "replace")
        ok = (exit_code == 0) if exit_code is not None else (not faulty)
        return ok, {"ok": ok, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                     "exit_code": exit_code}

    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = None
        if isinstance(tool_input, dict):
            path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if path and Path(path).is_file():
            try:
                raw = Path(path).read_bytes()
                ok = not faulty
                return ok, {"ok": ok, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            except Exception as e:
                return False, {"ok": False, "bytes": 0, "sha256": None, "error": str(e)}
        return (not faulty), {
            "ok": not faulty, "bytes": 0, "sha256": None,
            "hint": "Target file not found after run",
        }

    text = _short(tool_response, 2000).encode("utf-8", "replace")
    ok = not faulty
    return ok, {"ok": ok, "bytes": len(text), "sha256": hashlib.sha256(text).hexdigest()}


_I_DO_DDL = """CREATE TABLE IF NOT EXISTS f2_i_do (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    session TEXT,
    was     TEXT NOT NULL,
    kind     TEXT,
    schema  TEXT NOT NULL)"""


def _i_do(activity: str, kind: str = "task", session: str = "") -> None:
    """A line about own activity. Never throws."""
    activity = " ".join((activity or "").split())[:400]
    if not activity:
        return
    try:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=5.0)) as c:
            c.execute(_I_DO_DDL)
            c.execute("INSERT INTO f2_i_do (ts, session, activity, kind, schema) "
                      "VALUES (?,?,?,?,?)",
                      (datetime.now(timezone.utc).strftime(
                          "%Y-%m-%dT%H:%M:%SZ"), session, activity, kind,
                       "F2WP1207_ICHTUE/v1"))
            # Keep short: what was an hour ago is no longer an activity.
            c.execute("DELETE FROM f2_i_do WHERE id NOT IN "
                      "(SELECT id FROM f2_i_do ORDER BY id DESC LIMIT 40)")
            c.commit()
    except Exception:
        pass


def remember(payload: dict) -> None:
    """PostToolUse -- event trail (unchanged) + effect verification
    (PHASE 2, ZECP17). Updates the same effects row that allow()
    (PreToolUse) created (found via active_turns.effect_id); only
    if status='ALLOWED' was there, it switches to VERIFIED/FAILED --
    DENIED/RETRY/UNCHECKED remain as findings (that IS the information),
    but still get verified_at and an addendum with the actual result. If a
    PreToolUse row is missing entirely (timeout/error/fallback), remember()
    creates one itself -- the journal must never stay empty just because
    admission didn't make it in time. Additionally: one causal_episodes row
    per verified effect (described here for the first time, credit stays 0
    -- that is P3)."""
    session_id = str(payload.get("session_id") or "unknown")
    tool_name = payload.get("tool_name") or payload.get("hook_event_name") or "?"
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")

    try:
        with contextlib.closing(write_connection()) as c:
            mem_id = _uid(f"event-{session_id}")
            value = {"input": _short_edited(tool_input, 220), "response": _short_edited(tool_response, 220)}
            c.execute(
                "INSERT INTO durable_memory (memory_id, kind, subject, value, "
                "source_turn_id, user_id, ts, provenance) VALUES (?,?,?,?,?,?,?,?)",
                (
                    mem_id, "event", f"tool:{tool_name}",
                    json.dumps(_gm_redact_obj(value), ensure_ascii=False),
                    None, USER_ID, _now(), f"hook:PostToolUse:session={session_id}",
                ),
            )

            # PHASE 6/ZECP10, P6a point 2 -- gw_origin. provenance line per
            # newly written durable_memory line. `remember()` is [LIVE
            # checked, 2026-08-26] the ONLY write path into this table
            # in the entire file -- every line here is thus created
            # mandatorily from tool_input/tool_response, never from the user's
            # own input or the corpus. foreign_text=1 is therefore here
            # no guessed heuristic, but a fact about THIS
            # a write path -- honestly reported finding, not "always 1
            # because convenient": as soon as a second write path (e.g. explicit
            # Remembering of user's own text) arises, must the local
            # caller sets their own foreign_text, not this constant.
            gw_turn_row = c.execute(
                "SELECT turn_id FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            c.execute(
                "INSERT INTO gw_origin(memory_id, turn_id, session_id, ts, "
                "foreign_text, tools) VALUES (?,?,?,?,?,?)",
                (
                    mem_id, gw_turn_row[0] if gw_turn_row else None, session_id,
                    _now(), 1, json.dumps([tool_name], ensure_ascii=False),
                ),
            )

            if tool_name in STATE_CHANGING:
                ok, effect = _effect_check(tool_name, tool_input, tool_response)

                arow = c.execute(
                    "SELECT episode_id, effect_id, turn_id FROM active_turns WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                episode_id = arow[0] if arow else None
                effect_id = arow[1] if arow else None
                turn_id = arow[2] if arow else None

                line = c.execute(
                    "SELECT status, outcome FROM effects WHERE effect_id=?", (effect_id,)
                ).fetchone() if effect_id else None

                if line:
                    alter_status, alter_outcome_raw = line
                    try:
                        alter_outcome = json.loads(alter_outcome_raw) if alter_outcome_raw else {}
                    except Exception:
                        alter_outcome = {"illegible": alter_outcome_raw}
                    new_status = "VERIFIED" if ok else "FAILED"
                    if alter_status not in ("APPROVED",):
                        new_status = alter_status  # REJECTED/REPETITION/UNTESTED remain standing
                    alter_outcome["addendum"] = effect
                    c.execute(
                        "UPDATE effects SET status=?, outcome=?, verified_at=? WHERE effect_id=?",
                        (new_status, json.dumps(alter_outcome, ensure_ascii=False), _now(), effect_id),
                    )
                else:
                    # Fallback: no PreToolUse line found (timeout, error,
                    # or call outside a real session cycle).
                    srow = c.execute(
                        "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
                    ).fetchone()
                    generation = srow[0] if srow else 1
                    effect_id = _uid("eff")
                    target = _effect_goal(tool_input, tool_name)
                    c.execute(
                        "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                        "target, argv, requested_generation, status, outcome, ts, verified_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            effect_id, episode_id, USER_ID, tool_name, _short_edited(target, 300),
                            _argv_normalized_edited(tool_input), generation,
                            "VERIFIED" if ok else "FAILED",
                            json.dumps(
                                {"addendum": effect,
                                 "hint": "no PreToolUse row found (timeout/error/fallback)"},
                                ensure_ascii=False,
                            ),
                            _now(), _now(),
                        ),
                    )

                c.execute(
                    "INSERT INTO causal_episodes (causal_id, episode_id, effect_id, "
                    "observation_turn_id, outcome_hash, credit, reentered, ts) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (_uid("c"), episode_id, effect_id, turn_id, effect.get("sha256"), 0, 0, _now()),
                )
            c.commit()
    except Exception as e:
        _log(f"remember error sid={session_id} tool={tool_name}: {e}")
        return

    # P5d: Renew lease on touched file -- ONLY for the three
    # real file tools (Bash targets are not reliable file paths,
    # see target derivation above, which takes command text for Bash).
    # Fail-silent, outside the write_connection() transaction above, because
    # lease_hold() opens its own short connection -- a
    # failing lease must not drag down the event trail.
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit") and isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if path:
            try:
                with contextlib.closing(connection()) as c3:
                    genrow = c3.execute(
                        "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
                    ).fetchone()
                generation = genrow[0] if genrow else 1
            except Exception:
                generation = 1
            lease_hold(path, session_id, generation)


def _config_dyn_get(key: str, fallback: str = "") -> str:
    try:
        with contextlib.closing(connection()) as c:
            row = c.execute("SELECT value FROM star_config WHERE key=?", (key,)).fetchone()
            return row[0] if row else fallback
    except Exception as e:
        _log(f"_config_dyn_get error key={key}: {e}")
        return fallback


def _config_dyn_set(key: str, value: str, source: str = "phase13") -> None:
    try:
        with contextlib.closing(write_connection()) as c:
            c.execute(
                "INSERT INTO star_config (key, value, type, source, changed) VALUES (?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, source=excluded.source, "
                "changed=excluded.changed",
                (key, value, "str", source, _now()),
            )
            c.commit()
    except Exception as e:
        _log(f"_config_dyn_set error key={key}: {e}")


_LANGUAGE_DE_CACHE: Optional[bool] = None


def _language_is_german() -> bool:
    """PHASE 25 override path (user, explicit language choice per instance,
    2026-08-26): reads language_default directly from star_config -- NO
    import from setup.py (no circular import, same table/column, same
    rough detection as there _sprachkuerzel()). Instance-local by definition:
    each machine has its own unified.db/own language_default, ai-core-
    node remains untouched as long as nobody explicitly sets 'German'
    there. Fail-closed on DB errors -> False (English remains default)."""
    global _LANGUAGE_DE_CACHE
    if _LANGUAGE_DE_CACHE is None:
        value = ""
        try:
            with contextlib.closing(connection()) as c:
                row = c.execute(
                    "SELECT value FROM star_config WHERE key='language_default'"
                ).fetchone()
                if row and row[0]:
                    value = str(row[0])
        except Exception as e:
            _log(f"reading language_default failed (staying with English): {e}")
        s = value.strip().lower()
        # lang-data:de begin
        _LANGUAGE_DE_CACHE = s in (
            "de", "german", "deutsch", "de-de", "de-at", "de-ch",
            "österreichisch", "oesterreichisch",
        )
        # lang-data:de end
    return _LANGUAGE_DE_CACHE


def _language_variant_read(p: Path, fallback: str) -> str:
    """Common loader for the four PHASE-25-override files (persona/
    sebukku/architect_governance/architect_deep_session): if language_
    default=German AND a `<stem>.de.<ext>` file exists next to it,
    use that -- otherwise the previous (English) file unchanged. No
    second maintained text store project-wide (PHASE 25 requirement): the
    .de file exists only where it was created by hand/via gen+curation
    (currently: another instance), if missing, this silently falls back
    to English -- not an error state."""
    if _language_is_german():
        de_path = p.with_name(p.stem + ".de" + p.suffix)
        if de_path.exists():
            try:
                return de_path.read_text(encoding="utf-8")
            except Exception as e:
                _log(f"{de_path.name} missing/unreadable, falling back to English: {e}")
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        _log(f"{p.name} missing/illegible: {e}")
        return fallback


def sebukku_brand_check(session_id: str) -> Optional[dict]:
    """None = no mark (session unaffected). Otherwise {reason, ts,
    effect_id}. SESSION-BOUND -- the key is session_id, never
    global (Concept Document §5.5.2, bold marked)."""
    try:
        with contextlib.closing(connection()) as c:
            row = c.execute(
                "SELECT reason, ts, effect_id FROM star_sebukku WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return {"reason": row[0], "ts": row[1], "effect_id": row[2]}
    except Exception:
        return None  # Table may not exist yet -- then certainly no mark


_ROOM_FOCUS_PLACEHOLDER = "unknown at join time"


_ROOM_STALE_MINUTES = 45  # like active_workers(stale_minutes=45) in old research_room.py


_ROOM_NAMES_FILE = STAR_DIR / "data" / "room_names.json"


def _room_nickname_pull(place: int) -> str:
    """PHASE 37 -- random dystopian-gloomy short name from
    data/room_names.json for the .rname display in /stat (instead of raw
    'Session N'). Freshly loaded (no module caches, the file is tiny
    and read only ONCE per real join). Fail-silent: if file missing/broken,
    falls back to 'Session N' -- never a crash."""
    try:
        pool = json.loads(_ROOM_NAMES_FILE.read_text(encoding="utf-8"))
        if isinstance(pool, list) and pool:
            return str(random.choice(pool))
    except Exception as e:
        _log(f"room_nickname load error: {e}")
    return f"Session {place}"


def _zero_room_nickname_migrate(c) -> None:
    """Self-healing schema migration (real find, PHASE 42b/c deploy
    on machine-b, 2026-08-26): `data/schema_empty.sql` (template for
    fresh installs) never had a `nickname` column in `zero_room`
    -- on a dev box it exists anyway (added manually at some point,
    never mirrored back to template), on a freshly provisioned DB
    (another machine) it was missing and caused EVERY room join to
    fail with 'no such column'. `PRAGMA table_info`
    is cheap and idempotent -- no state that could be migrated twice,
    no harm on repeated calls."""
    try:
        columns = {row[1] for row in c.execute("PRAGMA table_info(zero_room)")}
        if "nickname" not in columns:
            c.execute("ALTER TABLE zero_room ADD COLUMN nickname TEXT")
            _log("zero_room: Column 'nickname' migrated retroactively (was missing on this DB)")
    except Exception as e:
        _log(f"_zero_room_nickname_migrate error (not critical): {e}")


def room_join_and_pulse(session_id: str, model: str) -> str:
    """Join (or renewed pulse, if line already exists -- a
    session that triggers SessionStart multiple times: /clear, /resume, /compact,
    /fork) + list of other active sessions. Replaces
    rooms_hook.py:handle_session_start()."""
    now = _now()
    try:
        with contextlib.closing(write_connection()) as c:
            _zero_room_nickname_migrate(c)
            available = c.execute(
                "SELECT place FROM zero_room WHERE session_id=?", (session_id,)
            ).fetchone()
            if available:
                place = available[0]
                join_text = "rejoin/pulse"
                # nickname remains stable for session lifetime -- the DO UPDATE
                # below leaves the column untouched, this value is only
                # used in the (not taken here) INSERT branch.
                nickname = None
            else:
                row = c.execute(
                    "SELECT COUNT(*) FROM zero_room WHERE human=? AND state='works'",
                    (USER_ID,),
                ).fetchone()
                place = (row[0] if row else 0) + 1
                join_text = "joined"
                nickname = _room_nickname_pull(place)  # ONCE, only on genuine first join
            c.execute(
                "INSERT INTO zero_room(session_id,human,place,activity,target,state,since,nickname) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET state='works', since=excluded.since, "
                "activity=excluded.activity",
                (session_id, USER_ID, place, _ROOM_FOCUS_PLACEHOLDER, f"claude-code:{model}",
                 "works", now, nickname),
            )
            threshold = now - _ROOM_STALE_MINUTES * 60
            # True self-healing instead of just display filter (user's requirement:
            # no corpses -- state must be reality, not just filtered out
            # when reading). Own line is safe: just written with
            # since=now, so >= threshold, never caught here.
            c.execute(
                "UPDATE zero_room SET state='free' WHERE state='works' AND since < ?",
                (threshold,),
            )
            c.commit()
            other = c.execute(
                "SELECT session_id, activity, since FROM zero_room WHERE state='works' "
                "AND session_id != ? AND since >= ? ORDER BY since DESC",
                (session_id, threshold),
            ).fetchall()
    except Exception as e:
        _log(f"room_join error sid={session_id}: {e}")
        return f"room center: Error joining ({e})."

    _room_call_write(session_id, "JOIN" if join_text == "joined" else "PULSE",
                        f"session={session_id} place={place}")

    lines = [f"room center: {join_text} as {session_id}."]
    if other:
        lines.append(f"{len(other)} other active session(s):")
        for sid, activity, since in other:
            lines.append(f"- {sid} focus={activity} last_pulse={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(since))}")
    else:
        lines.append("no other active sessions in room now.")

    # P5d: Collision message, no lock -- all active leases of other
    # Sessions, so that a fresh SessionStart immediately sees what is currently being worked on
    # worked on, without anything being blocked.
    hints = lease_hints(except_session=session_id)
    if hints:
        lines.append(f"{len(hints)} file(s) currently leased by other session(s):")
        lines.extend(f"- {h}" for h in hints)

    return "\n".join(lines)


def room_leave(session_id: str) -> None:
    """Replaces rooms_hook.py:handle_session_end(). Line remains intact
    (state='free') instead of being deleted -- same semantics as the
    old status=COMPLETE (history stays visible, but no longer
    counts as 'active')."""
    try:
        with contextlib.closing(write_connection()) as c:
            c.execute("UPDATE zero_room SET state='free' WHERE session_id=?", (session_id,))
            c.commit()
    except Exception as e:
        _log(f"room_leave error sid={session_id}: {e}")
    _room_call_write(session_id, "LEAVE", f"session={session_id}")


def room_pulse_renew(session_id: str) -> None:
    """Heartbeat for a running session -- runs on EVERY
    UserPromptSubmit (not just SessionStart/`/clear`/`/resume`/`/compact`/
    `/fork`), so long-running sessions' `since` doesn't just stay at join time
    and then become invisible via the display threshold
    (_ROOM_STALE_MINUTES) even though work continues. No re-join, no new JOIN/PULSE line in zero_room_call, no full recalculation of other sessions -- just refresh `since`.
    Refresh own line first (proves liveness independent of
    previous state), THEN the expiry sweep for all others, so that
    the own, just-refreshed line can never be caught.

    This makes expiry REAL, not just filtered out at display time
    (user's requirement: no corpses in the room -- state must be reality,
    either logged in or automatically logged out on disappearance).
    Complements room_leave() (SessionEnd, immediate correct exit) as
    safety net for crashes/kills that never trigger SessionEnd. A single
    indexed UPDATE per statement, sub-millisecond cheap.
    Fail-silent like everything here -- must never disturb the hook."""
    now = _now()
    try:
        with contextlib.closing(write_connection()) as c:
            c.execute(
                "UPDATE zero_room SET state='works', since=? WHERE session_id=?",
                (now, session_id),
            )
            c.execute(
                "UPDATE zero_room SET state='free' WHERE state='works' AND since < ?",
                (now - _ROOM_STALE_MINUTES * 60,),
            )
            c.commit()
    except Exception as e:
        _log(f"room_pulse_renew error sid={session_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION: ROOM MESSAGES (User order 2026-08-27, verbatim: "you
# have no way to talk to each other in the Room? that's supposed to be an Agent
# solve and make possible.") -- real message channel BETWEEN
# Sessions/agents in the room, additive to zero_room (who is there)/zero_room_call
# (Event log, remains unchanged -- MESSAGE is additionally there
# noted, briefly, without full text, see room_message_send()). Two
# new tables, self-healing created via CREATE TABLE IF NOT EXISTS like
# topics_status above (no schema_empty.sql entry needed, same
# Convention/precedent from the same day).
#
# WHY TWO TABLES INSTEAD OF JUST ONE room_message WITH read_at (as in the
# brief outlined as basic structure, "your discretion on details, but
# check them against existing code"): a single read_at column
# works only when EXACTLY ONE recipient exists. With --all
# (to_session_id IS NULL) have MULTIPLE sessions read the same row --
# the first reading session would set read_at, making the
# message immediately disappear for every other session that never saw it
# has (bug, really thought through, not just found live). room_message_
# read tracks read status PER RECIPIENT, only for broadcasts
# needed (direct messages keep the simple read_at column,
# because there's only one recipient anyway -- no unnecessary second
# write path for the more common case).
#
# RECEIPT is NEVER active polling: _room_messages_context_text() runs
# automatically on EVERY SessionStart AND UserPromptSubmit (see cmd_hook(),
# exactly the two places that can already deliver additionalContext
# -- PostToolUse/PreToolUse usually print nothing, see cmd_hook()-
# Kopf), analog to room_join_and_pulse()/room_pulse_renew(). Holt
# unread messages AND marks them as read in the same turn -- no
# session sees the same message twice, no session must ever actively
# ask. No LLM call here (pure SQL), §1.9.2 preserved.
# ═══════════════════════════════════════════════════════════════════════
def _ensure_room_message_tables(c) -> None:
    c.execute(
        "CREATE TABLE IF NOT EXISTS room_message("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, from_session_id TEXT NOT NULL, "
        "to_session_id TEXT, text TEXT NOT NULL, created_at REAL NOT NULL, read_at REAL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS room_message_read("
        "message_id INTEGER NOT NULL, session_id TEXT NOT NULL, read_at REAL NOT NULL, "
        "PRIMARY KEY (message_id, session_id))"
    )


_ROOM_MESSAGE_FETCH_LIMIT = 10  # per hook call at most this many new messages append


def room_message_send(from_session_id: str, text: str, to_session_id: Optional[str] = None) -> dict:
    """Writes ONE new line -- direct message (to_session_id set)
    or broadcast (to_session_id NULL, visible to ALL except the
    sender, also for sessions that pulse later, as long as the line
    is still unread for them). `text` is not validated for content,
    only hard-truncated (abuse protection, no free-text novel in the
    hook context of a foreign session)."""
    from_session_id = (from_session_id or "").strip() or "manual"
    text = _short((text or "").strip(), 2000)
    if not text:
        return {"ok": False, "reason": "empty text"}
    to_session_id = (to_session_id or "").strip() or None
    now = _now()
    try:
        with contextlib.closing(write_connection()) as c:
            _ensure_room_message_tables(c)
            cur = c.execute(
                "INSERT INTO room_message (from_session_id, to_session_id, text, created_at, read_at) "
                "VALUES (?,?,?,?,NULL)",
                (from_session_id, to_session_id, text, now),
            )
            message_id = cur.lastrowid
            c.commit()
    except Exception as e:
        _log(f"room_message_send error from={from_session_id} to={to_session_id}: {e}")
        return {"ok": False, "reason": str(e)}
    # Shortcut in the existing event log -- without full text (which lives alone
    # in room_message), so that zero_room_call does not become a second message-
    # store, just a note "something happened here".
    _room_call_write(from_session_id, "MESSAGE",
                         f"to={to_session_id or 'ALL'} id={message_id} text={_short(text, 80)}")
    return {"ok": True, "id": message_id, "to": to_session_id or "ALL"}


def _room_messages_pick_up_and_mark(session_id: str, limit: int = _ROOM_MESSAGE_FETCH_LIMIT) -> list:
    """Reads unread messages for `session_id` (direct OR broadcast,
    that this session has not seen yet) and marks them IMMEDIATELY as
    read (direct: read_at, broadcast: own row in
    room_message_read) -- afterwards the same message never
    appears again for this session. Fail-silent like everything here, must not
    disturb a hook."""
    if not session_id or session_id == "unknown":
        return []
    now = _now()
    hit = []
    try:
        with contextlib.closing(write_connection()) as c:
            _ensure_room_message_tables(c)
            lines = c.execute(
                "SELECT n.id, n.from_session_id, n.to_session_id, n.text, n.created_at "
                "FROM room_message n WHERE n.from_session_id != ? AND ("
                "  (n.to_session_id = ? AND n.read_at IS NULL)"
                "  OR (n.to_session_id IS NULL AND NOT EXISTS ("
                "        SELECT 1 FROM room_message_read g "
                "        WHERE g.message_id = n.id AND g.session_id = ?))"
                ") ORDER BY n.created_at ASC LIMIT ?",
                (session_id, session_id, session_id, limit),
            ).fetchall()
            for nid, src, an, text, created_at in lines:
                if an is not None:
                    c.execute("UPDATE room_message SET read_at=? WHERE id=?", (now, nid))
                else:
                    c.execute(
                        "INSERT INTO room_message_read (message_id, session_id, read_at) "
                        "VALUES (?,?,?) ON CONFLICT(message_id, session_id) DO NOTHING",
                        (nid, session_id, now),
                    )
                hit.append({"id": nid, "src": src, "broadcast": an is None,
                                 "text": text, "created_at": created_at})
            c.commit()
    except Exception as e:
        _log(f"room_messages_pick_up error sid={session_id}: {e}")
        return []
    return hit


def _room_messages_context_text(session_id: str) -> Optional[str]:
    """Builds the additionalContext block from freshly fetched messages --
    None if there are no new ones (no filler text, same discipline as
    _topics_status_overview_text())."""
    hit = _room_messages_pick_up_and_mark(session_id)
    if not hit:
        return None
    n = len(hit)
    lines = [f"The room -- {n} new message{'s' if n != 1 else ''} from other sessions:"]
    for t in hit:
        kind = "to everyone" if t["broadcast"] else "directly to you"
        lines.append(f"  - [{kind}] from {t['src']}: {t['text']}")
    lines.append('(Replies: `star_cli.py room-message-send --to <session_id|--all> --text "..."`)')
    return "\n".join(lines)


def _architect_governance_interval(signal_count: int) -> int:
    """PHASE 17v2 (addendum 'cadence, deep session, mandate, representation'):
    replaces the fixed 25-turn cadence with a ramp-up cadence -- the
    FIRST 2 signals every 10 turns, the NEXT 3 every 25 turns, THEN
    permanently every 40 turns. `signal_count` is how many signals have
    already been delivered (0 = none yet) -- determines which regime the
    NEXT signal has."""
    if signal_count < 2:
        return 10
    if signal_count < 5:
        return 25
    return 40


def architect_governance_move() -> dict:
    """PHASE 17 item 4, PHASE 17v2 escalated -- one turn = one 'Stop' event
    (see cmd_hook). GLOBALLY counted (not session-bound -- concept doc:
    'counter in star_config', no <sid> binding like persona.counter.<sid>),
    because the self-care loop affects all usage, not a single session.

    Two counters, deliberately separate:
    - architect_governance.move_counter: cumulative over ALL turns per,
      unchanged from PHASE 17 (informational only, for the signal display
      "at turn N").
    - architect_governance.moves_since_signal: since the LAST delivered
      signal, NEW in PHASE 17v2 -- this is the counter checked against the
      current cadence regime (_architect_governance_interval) and
      reset to 0 on trigger.
    - architect_governance.signal_count: how many signals delivered
      IN TOTAL -- determines the current regime (10/25/40)."""
    try:
        counter = int(_config_dyn_get("architect_governance.move_counter", "0") or "0") + 1
    except Exception:
        counter = 1
    _config_dyn_set("architect_governance.move_counter", str(counter), source="phase17-stop")

    try:
        since_signal = int(_config_dyn_get("architect_governance.moves_since_signal", "0") or "0") + 1
    except Exception:
        since_signal = 1
    try:
        signal_count = int(_config_dyn_get("architect_governance.signal_count", "0") or "0")
    except Exception:
        signal_count = 0

    interval = _architect_governance_interval(signal_count)
    due = since_signal >= interval
    if due:
        since_signal = 0
        signal_count += 1
        _config_dyn_set("architect_governance.signal_count", str(signal_count), source="phase17-stop")
        _config_dyn_set("architect_governance.signal_due", "1", source="phase17-stop")
    _config_dyn_set("architect_governance.moves_since_signal", str(since_signal), source="phase17-stop")
    return {
        "move_counter": counter, "moves_since_signal": since_signal,
        "signal_count": signal_count, "interval_used": interval,
        "due": due,
    }


_ARCHITECT_GOVERNANCE_TEXT_CACHE: Optional[str] = None


def _architect_governance_text() -> str:
    """Instruction text for the main instance at a due 25-turn
    milestone -- stored as a file in data/ (same reason as persona.md/
    sebukku.txt: tone pool/instruction stays a file matter, only state goes
    into unified.db, see PERSONA/SEBUKKU section header above)."""
    global _ARCHITECT_GOVERNANCE_TEXT_CACHE
    if _ARCHITECT_GOVERNANCE_TEXT_CACHE is not None:
        return _ARCHITECT_GOVERNANCE_TEXT_CACHE
    p = STAR_DIR / "data" / "architect_governance.md"
    _ARCHITECT_GOVERNANCE_TEXT_CACHE = _language_variant_read(p, "")
    return _ARCHITECT_GOVERNANCE_TEXT_CACHE


def _architect_governance_signal_check() -> Optional[str]:
    """Called from UserPromptSubmit (see cmd_hook). Reads the
    flag that architect_governance_move() set on Stop -- delivered at most
    ONCE (flag reset immediately), then continue counting normally until
    the next 25-turn milestone."""
    if _config_dyn_get("architect_governance.signal_due", "0") != "1":
        return None
    _config_dyn_set("architect_governance.signal_due", "0", source="userpromptsubmit")
    text = _architect_governance_text()
    if not text:
        return None
    counter = _config_dyn_get("architect_governance.move_counter", "?")
    signal_count = _config_dyn_get("architect_governance.signal_count", "?")
    interval = _architect_governance_interval(max(int(signal_count) - 1, 0) if str(signal_count).isdigit() else 0)
    return (
        f"[PHASE 17 -- Architect-Governance-Brand No. {signal_count} on move {counter} "
        f"(Cadence regime: every {interval} moves)]\n\n{text}"
    )
