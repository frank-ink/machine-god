#!/usr/bin/env python3
"""star_cli.py -- FranKensteinಠ_ಠ hook engine (ported minimal build, Phase A).

NOT a copy of the original ~19,000-line star_cli.py from the source machine --
a curated, from-scratch reimplementation covering exactly what's needed for
Claude Code to feel like FranKensteinಠ_ಠ here: persona injection on
SessionStart/UserPromptSubmit, Architect-mode toggling + injection, a small
real memory read/write against unified.db, the sebukku ritual, teaching-
lesson recording, deflection-line rotation.

Explicitly NOT ported (see the project CLAUDE.md "Note on this instance"): GRID10
cognition internals, voice mode, the visual avatar renderer, immune-system/
watcher daemons, OMEGA/oMEGAcV1, anything tied to the source machine's own
infrastructure. Where persona.md or the governance docs reference a
star_cli.py subcommand not implemented here, that's a known, documented gap --
not a silent failure.
"""
import argparse
import os
import signal
import contextlib
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:  # Secret redaction/filter: A pattern replacement source (secret_pattern.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import secret_pattern as _gm
except Exception:  # fail-closed: without module is NOT saved unencrypted
    _gm = None

HOME = Path.home()
STAR = Path(__file__).resolve().parent          # Plugin code (read only)
if str(STAR) not in sys.path:
    sys.path.insert(0, str(STAR))
import f3_paths as _pf                          # Portability: Runtime data outside the plugin
_pf.ensure_db()
DATA = STAR / "data"
DB_PATH = _pf.DB
LOG_PATH = _pf.LOG
PERSONA_PATH = DATA / "persona.md"
ARCHITECT_PERSONA_FALLBACK = STAR / "architect" / "persona.md"


class _HookTimeout(BaseException):
    """BaseException on purpose: ported donor code has many `except Exception`
    blocks that would otherwise swallow the alarm and let the hook hang."""


def _hook_alarm(signum, frame):
    raise _HookTimeout()


_HOOK_LIMITS = {"SessionStart": 4.0, "UserPromptSubmit": 3.0, "Stop": 3.0}
_core_mod = None
_zy_mod = None
_grid_mod = None


def _hook_limit(event: str) -> float:
    """Per-event budget: star_config limit.<Event> (via star_core) when present,
    else the static table, else 2.0. UserPromptSubmit/SessionStart/Stop keep the
    generous static value (grid10 turn + retrieval live there)."""
    if event in _HOOK_LIMITS:
        return _HOOK_LIMITS[event]
    try:
        c = _core()
        if c is not None:
            return float(c._config().get(f"limit.{event}", 2.0))
    except Exception:
        pass
    return 2.0


def _zy():
    """Lazy import of star_cycle (session cycle / effect gate / room /
    governance, ported from the ARCH donor). None on failure -> degrade."""
    global _zy_mod
    if _zy_mod is None:
        try:
            if str(STAR) not in sys.path:
                sys.path.insert(0, str(STAR))
            import star_cycle  # noqa
            _zy_mod = star_cycle
        except Exception as e:
            _log(f"star_cycle import failed: {e}")
            _zy_mod = False
    return _zy_mod or None


def _grid():
    """Lazy import of the grid10 lane (modules/grid10/register.py). None on failure."""
    global _grid_mod
    if _grid_mod is None:
        try:
            import importlib.util as _ilu
            _p = STAR / "modules" / "grid10" / "register.py"
            _sp = _ilu.spec_from_file_location("grid10_register", _p)
            _m = _ilu.module_from_spec(_sp)
            _sp.loader.exec_module(_m)
            _grid_mod = _m
        except Exception as e:
            _log(f"grid10 lane import failed: {e}")
            _grid_mod = False
    return _grid_mod or None


def _core():
    """Lazy import of the ported donor cognition core (star_core.py).
    Returns None (never raises) if it is missing/broken -> callers degrade."""
    global _core_mod
    if _core_mod is None:
        try:
            if str(STAR) not in sys.path:
                sys.path.insert(0, str(STAR))
            import star_core  # noqa
            _core_mod = star_core
        except Exception as e:
            _log(f"star_core import failed: {e}")
            _core_mod = False
    return _core_mod or None


def _log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    except Exception:
        pass


def _connect() -> sqlite3.Connection:
    # Deliberately does NOT create unified.db if it's missing -- that file
    # is owned by the schema_empty.sql bootstrap (separate build step). If
    # it isn't there yet, every caller here degrades gracefully (logs,
    # returns empty) instead of racing a second, incompatible DB into
    # existence at the same path.
    if not DB_PATH.exists():
        raise FileNotFoundError(f"unified.db not found yet at {DB_PATH}")
    c = sqlite3.connect(str(DB_PATH), timeout=5.0)
    c.execute("PRAGMA busy_timeout=5000")
    # IF NOT EXISTS: safe no-op once the canonical schema already created
    # these tables (column layout matches data/schema_empty.sql exactly).
    c.execute(
        "CREATE TABLE IF NOT EXISTS star_config("
        "key TEXT PRIMARY KEY, value TEXT, type TEXT, source TEXT, changed REAL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS durable_memory("
        "memory_id TEXT PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL, "
        "value TEXT NOT NULL, source_turn_id TEXT, user_id TEXT, ts REAL NOT NULL, "
        "provenance TEXT NOT NULL)"
    )
    return c


def _config_get(key: str, default=None):
    try:
        with contextlib.closing(_connect()) as c:
            row = c.execute("SELECT value FROM star_config WHERE key=?", (key,)).fetchone()
            return row[0] if row else default
    except Exception as e:
        _log(f"config_get error {key}: {e}")
        return default


def _config_set(key: str, value, value_type: str = "str", source: str = "") -> None:
    try:
        with contextlib.closing(_connect()) as c:
            c.execute(
                "INSERT INTO star_config(key,value,type,source,changed) VALUES(?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, type=excluded.type, "
                "source=excluded.source, changed=excluded.changed",
                (key, str(value), value_type, source, time.time()),
            )
            c.commit()
    except Exception as e:
        _log(f"config_set error {key}: {e}")


def _mem_write(kind: str, subject: str, value_dict: dict) -> None:
    try:
        if _gm is None:
            _log(f"mem_write discarded (secret_pattern missing) {kind}")
            return
        subject = _gm.redact(subject)[0]
        value_dict = _gm.redact_obj(value_dict)
        with contextlib.closing(_connect()) as c:
            c.execute(
                "INSERT INTO durable_memory(memory_id,kind,subject,value,source_turn_id,user_id,ts,provenance) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    kind,
                    subject,
                    json.dumps(value_dict, ensure_ascii=False),
                    None,
                    None,
                    time.time(),
                    "star_cli.py(friend-port,phase-a)",
                ),
            )
            c.commit()
    except Exception as e:
        _log(f"mem_write error {kind}/{subject}: {e}")


def _mem_search(text: str, limit: int = 4):
    """Small keyword retrieval: LIKE-style substring match on durable_memory
    values, newest first. Not the source machine's emergent retrieval --
    plain substring search. Enough to prove memory read/write works and to
    surface prior turns; stronger retrieval is Phase B/C territory."""
    words = [w for w in text.lower().split() if len(w) >= 4][:5]
    if not words:
        return []
    try:
        with contextlib.closing(_connect()) as c:
            rows = c.execute(
                "SELECT kind, subject, value, ts FROM durable_memory "
                "WHERE kind IN ('lesson') ORDER BY ts DESC LIMIT 200"
            ).fetchall()
    except Exception as e:
        _log(f"mem_search error: {e}")
        return []
    hits = []
    for kind, subject, value, ts in rows:
        low = value.lower()
        if any(w in low for w in words):
            hits.append((kind, subject, value, ts))
    return hits[:limit]


def _persona_text() -> str:
    try:
        return PERSONA_PATH.read_text(encoding="utf-8")
    except Exception as e:
        _log(f"persona read error: {e}")
        return ""


def _architect_active() -> bool:
    return (
        _config_get("architect.active", "0") == "1"
        or _config_get("architect_dialog.active", "0") == "1"
    )


def ascii_frame(text: str, title: str = "ARCHITECT", width: int = 68) -> str:
    """Frame text in an ASCII box with a heading (output verbatim, do not recompose)."""
    import textwrap
    inner = width - 4
    lines = []
    for para in (text or "").splitlines() or [""]:
        lines.extend(textwrap.wrap(para, inner) or [""])
    top = "+-[ " + title + " ]" + "-" * max(0, width - 8 - len(title)) + "+"
    body = ["| " + ln.ljust(inner) + " |" for ln in lines]
    return "\n".join([top] + body + ["+" + "-" * (width - 2) + "+"])


def _architect_persona() -> str:
    try:
        with contextlib.closing(_connect()) as c:
            row = c.execute(
                "SELECT value FROM durable_memory WHERE kind='persona' AND subject='architect' "
                "ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if row:
                try:
                    d = json.loads(row[0])
                    text = d.get("content") or d.get("text") or ""
                except Exception:
                    text = row[0]
                if text.strip():
                    return text
    except Exception as e:
        _log(f"architect_persona DB error: {e}")
    # Fallback: a file-based persona, in case the Architect port wrote
    # files instead of a DB row (two independent build steps, unknown at
    # write time which one landed).
    try:
        return ARCHITECT_PERSONA_FALLBACK.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---- hook event handlers ----

def _fp_name() -> str:
    try:
        import frank_profile as _fpm
        return _fpm.name()
    except Exception:
        return "friend"


def _welcome_banner() -> str:
    """Startup banner -- pre-baked figlet kind read from data/banner.txt (fail-silent)."""
    try:
        return open(STAR / "data" / "banner.txt", encoding="utf-8").read().rstrip()
    except Exception:
        return "FranKenstein ಠ_ಠ — for " + (_fp_name() or "you")


def _ccdiet_mode(key: str) -> str:
    """CCDIET flags (default shadow; off disables; any error -> off)."""
    try:
        v = str(_config_get(key, "shadow") or "shadow").lower()
        return v if v in ("off", "shadow", "on") else "off"
    except Exception:
        return "off"


def _ccdiet():
    try:
        if str(STAR) not in sys.path:
            sys.path.insert(0, str(STAR))
        import ccdiet
        return ccdiet
    except Exception as e:
        _log(f"ccdiet import error (fail-silent): {e}")
        return None


def _handle_session_start(session_id: str, data: dict | None = None) -> str:
    data = data or {}
    source = str(data.get("source") or "startup")
    model = str(data.get("model") or "?")
    parts = []
    persona = _persona_text()
    if persona.strip():
        parts.append(persona)
    else:
        _log("persona.md empty/missing -- SessionStart without identity")
    try:  # FRANK3 profile: fresh install -> one deterministic ask-for-name instruction (once)
        import frank_profile as _fpm
        _fr = _fpm.first_run_text()
        if _fr:
            parts.append(_fr)
    except Exception as e:
        _log(f"first_run error (fail-silent): {e}")
    _mem_write("turn_log", session_id, {"role": "session_start", "ts": time.time()})
    try:
        _cd = _ccdiet()
        if _cd is not None and str(data.get("source") or "startup") != "resume":
            _cd.reset(session_id)
    except Exception as e:
        _log(f"ccdiet reset error: {e}")
    z = _zy()
    if z is not None:
        try:
            z._config_dyn_set(f"persona.new_inject.{session_id}", "0", source="SessionStart")
            z._config_dyn_set(f"persona.counter.{session_id}", "0", source="SessionStart")
        except Exception as e:
            _log(f"session persona flags error: {e}")
        if source == "startup":
            try:
                z.cycle_open(session_id, model)
            except Exception as e:
                _log(f"cycle_open error: {e}")
        try:
            room_text = z.room_join_and_pulse(session_id, model)
            if room_text:
                parts.append(room_text)
        except Exception as e:
            _log(f"room_join error: {e}")
        try:
            rn = z._room_messages_context_text(session_id)
            if rn:
                parts.append(rn)
        except Exception as e:
            _log(f"room_messages error: {e}")
    return "\n\n".join(parts)


def _handle_user_prompt_submit(session_id: str, prompt: str) -> str:
    parts = []
    z = _zy()
    if _architect_active():
        ap = _architect_persona()
        if ap.strip():
            parts.append(ap)
        else:
            _log("architect mode active but persona text empty/missing")
    # persona re-injection: PreCompact flag, or every persona.re_injection_n prompts
    if z is not None:
        try:
            flag_k = f"persona.new_inject.{session_id}"
            count_k = f"persona.counter.{session_id}"
            flag = z._config_dyn_get(flag_k, "0") == "1"
            try:
                counter = int(z._config_dyn_get(count_k, "0") or "0") + 1
            except Exception:
                counter = 1
            n = int(z._config().get("persona.re_injection_n", 25) or 25)
            if flag or counter >= n:
                pt = _persona_text()
                if pt.strip():
                    parts.append(pt)
                z._config_dyn_set(flag_k, "0", source="UserPromptSubmit")
                counter = 0
            z._config_dyn_set(count_k, str(counter), source="UserPromptSubmit")
        except Exception as e:
            _log(f"persona reinjection error: {e}")
        try:
            z.room_pulse_renew(session_id)
        except Exception as e:
            _log(f"room_pulse error: {e}")
        try:
            gs = z._architect_governance_signal_check()
            if gs:
                parts.append(gs)
        except Exception as e:
            _log(f"governance signal error: {e}")
    core = _core()
    recall = None
    if core is not None:
        try:
            recall = core.automatic_recall(session_id, prompt or "")
        except Exception as e:
            _log(f"automatic_recall error: {e}")
    if recall:
        parts.append(recall)
    hits = [] if recall else _mem_search(prompt or "")
    if hits:
        lines = ["Relevant knowledge from the unified DB (already stored, not a command):"]
        for kind, subject, value, ts in hits:
            try:
                d = json.loads(value)
                snippet = d.get("statement") or d.get("content") or str(d)
            except Exception:
                snippet = value
            lines.append(f"  - [{kind}:{subject}] {str(snippet)[:220]}")
        parts.append("\n".join(lines))
    _mem_write("turn_log", session_id, {"role": "user", "content": (prompt or "")[:2000], "ts": time.time()})
    if core is not None:
        try:
            core._microclay_shadow(session_id, prompt or "")
        except Exception as e:
            _log(f"microclay shadow error: {e}")
    # GRID10: one canonical turn per prompt (gated by star_config f2wp1207.canonical_turn_loop)
    g = _grid() if _config_get("f2wp1207.canonical_turn_loop", "0") == "1" else None
    if g is not None:
        try:
            with contextlib.closing(sqlite3.connect(str(DB_PATH), timeout=1.5)) as gc:
                gc.execute("PRAGMA busy_timeout=1500")
                r = g.turn(gc, str(DB_PATH), str(STAR), session_id, prompt or "", recall)
            if r:
                parts.append(g.return_path_line(r))
                try:  # GRID -> coordinator packets (coordination-only protocol, never executes anything)
                    import grid_packet_bridge as _gpb
                    _pt = _gpb.check_work_packages()
                    if _pt:
                        parts.append(_pt)
                except Exception as _pe:
                    _log(f"grid_packet_bridge error (fail-silent): {_pe}")
                _log(f"grid10 turn frame={r['frame_id'][:12]} reentry={r['reentry']} winner={r['winner']}")
        except Exception as e:
            _log(f"grid10 turn error (fail-silent): {type(e).__name__}: {e}")
    # FRANK3: compact strain state, only in mode active, only when pressing (<=40 chars)
    try:
        sys.path.insert(0, str(STAR / "tools"))
        import frank3_hook as _f3
        _sl = _f3.strain_line(str(DB_PATH))
        if _sl:
            parts.append(_sl)
        # FRANK3 stage I: global-workspace cycle (token-free organ bus): drain pushes + pull sources -> compete -> <=1 bounded line (active only)
        import frank3_gwt as _gwt
        _gl, _gi = _gwt.cycle(session_id, prompt or "", db=str(DB_PATH))
        if _gl:
            parts.append(_gl)
    except Exception as e:
        _log(f"frank3 strain_line error (fail-silent): {e}")
    if z is not None:
        try:
            rn = z._room_messages_context_text(session_id)
            if rn:
                parts.append(rn)
        except Exception as e:
            _log(f"room_messages error: {e}")
    ctx = "\n\n".join(parts)
    try:  # CCDIET hook diet (flag ccdiet.hook_diet.mode, default shadow = log only)
        _cd = _ccdiet()
        if _cd is not None:
            ctx, _ = _cd.filter_ctx(session_id, prompt or "", ctx, _ccdiet_mode("ccdiet.hook_diet.mode"))
    except Exception as e:
        _log(f"ccdiet filter error (fail-silent): {e}")
    return ctx


def _handle_stop(session_id: str, transcript_path=None) -> str:
    core = _core()
    if core is not None:
        try:
            core._microclay_credit_signal(session_id, transcript_path)
        except Exception as e:
            _log(f"microclay credit signal error: {e}")
    z = _zy()
    if z is not None:
        try:
            z.cycle_close(session_id)
        except Exception as e:
            _log(f"cycle_close error: {e}")
        try:
            z.architect_governance_move()
        except Exception as e:
            _log(f"governance move error: {e}")
    _mem_write("turn_log", session_id, {"role": "stop", "ts": time.time()})
    # FRANK3: event-triggered inner reflection (detached, niced, own 10-min rate limit + mode/kill flags inside the reflector)
    try:
        import subprocess
        if not (STAR / "FRANK3_KILL").exists():
            subprocess.Popen(["nice", "-n", "15", sys.executable, str(STAR / "tools" / "frank3_reflector.py"), "--event", "--llm", "1"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        _log(f"frank3 reflector spawn error (fail-silent): {e}")
    return ""


def _handle_pre_tool(data: dict) -> str:
    """Effect gate = bookkeeping only (allow never blocks, prints nothing)."""
    try:
        _cd = _ccdiet()
        if _cd is not None and data.get("tool_name") == "Read":
            _cd.pre_tool_shadow(data, _ccdiet_mode("ccdiet.tool_shadow.mode"))
    except Exception as e:
        _log(f"ccdiet pre_tool error: {e}")
    z = _zy()
    if z is not None:
        try:
            z.allow(data)
        except Exception as e:
            _log(f"allow error: {e}")
    # FRANK3: self-reflection lesson for this tool, once per session, only when frank3.reflector.mode=active (shadow counts only)
    try:
        sys.path.insert(0, str(STAR / "tools"))
        import frank3_hook as _f3
        return _f3.surface_pre_tool(str(DB_PATH), str(data.get("session_id") or "x"), str(data.get("tool_name") or ""))
    except Exception as e:
        _log(f"frank3 pre_tool error (fail-silent): {e}")
    return ""


def _handle_post_tool(data: dict) -> str:
    try:
        if data.get("tool_name") in ("Bash", "Read", "Grep", "Glob"):
            _cd = _ccdiet()
            if _cd is not None:
                _cd.post_tool_shadow(data, _ccdiet_mode("ccdiet.tool_shadow.mode"))
    except Exception as e:
        _log(f"ccdiet post_tool error: {e}")
    z = _zy()
    if z is None:
        return ""
    sid = str(data.get("session_id") or "unknown")
    try:
        tn = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        if tn in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
            goal = os.path.basename(str(ti.get("file_path") or ti.get("notebook_path") or ""))
            if goal:
                z._i_do(f"worked on {goal}", "action", sid)
        elif tn == "Bash":
            z._i_do("ran a shell command", "action", sid)
    except Exception as e:
        _log(f"i_do error: {e}")
    try:
        z.remember(data)
    except Exception as e:
        _log(f"remember error: {e}")
    return ""


def _handle_pre_compact(session_id: str) -> str:
    z = _zy()
    if z is not None:
        try:
            z._config_dyn_set(f"persona.new_inject.{session_id}", "1", source="PreCompact")
        except Exception as e:
            _log(f"precompact flag error: {e}")
    try:
        _cd = _ccdiet()
        if _cd is not None:
            _cd.reset(session_id, compacted=True)
    except Exception as e:
        _log(f"ccdiet precompact error: {e}")
    return ""


def _handle_session_end(session_id: str) -> str:
    z = _zy()
    if z is not None:
        try:
            z.cycle_close(session_id)
        except Exception as e:
            _log(f"cycle_close(end) error: {e}")
        try:
            z.room_leave(session_id)
        except Exception as e:
            _log(f"room_leave error: {e}")
    return ""


def _handle_generic(event: str, session_id: str) -> str:
    _log(f"event={event} session={session_id} (logged, no-op)")
    return ""


def cmd_hook() -> int:
    try:
        signal.signal(signal.SIGALRM, _hook_alarm)
        signal.setitimer(signal.ITIMER_REAL, 4.0)
    except Exception:
        pass
    try:
        try:
            raw = sys.stdin.read()
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                raise ValueError("stdin JSON not an object")
        except Exception as e:
            _log(f"hook stdin parse error: {e}")
            print(json.dumps({}))
            return 0
        return _cmd_hook_inner(data)
    except _HookTimeout:
        _log("hook timeout (alarm) -- fail-silent")
        print(json.dumps({}))
        return 0
    except BaseException as e:  # never crash a Claude Code turn
        _log(f"hook fatal: {type(e).__name__}: {e}")
        try:
            print(json.dumps({}))
        except Exception:
            pass
        return 0
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Exception:
            pass


def _cmd_hook_inner(data: dict) -> int:
    event = data.get("hook_event_name", "")
    try:
        signal.setitimer(signal.ITIMER_REAL, _hook_limit(event))
    except Exception:
        pass
    session_id = data.get("session_id", "unknown")
    try:
        if event == "SessionStart":
            ctx = _handle_session_start(session_id, data)
        elif event == "UserPromptSubmit":
            ctx = _handle_user_prompt_submit(session_id, data.get("prompt", ""))
        elif event == "Stop":
            ctx = _handle_stop(session_id, data.get("transcript_path"))
        elif event == "PreToolUse":
            ctx = _handle_pre_tool(data)
        elif event == "PostToolUse":
            ctx = _handle_post_tool(data)
        elif event == "PreCompact":
            ctx = _handle_pre_compact(session_id)
        elif event == "SessionEnd":
            ctx = _handle_session_end(session_id)
        else:
            ctx = _handle_generic(event, session_id)
    except Exception as e:
        _log(f"hook handler error event={event}: {e}")
        ctx = ""
    out = {}
    if ctx and _gm is not None:
        try:  # Retrieval filter: nothing with secret pattern leaves the hook
            ctx = _gm.filter_output(ctx)
        except Exception as e:
            _log(f"secret filter error: {type(e).__name__}")
            ctx = ""
    elif ctx and _gm is None:
        ctx = ""
    if ctx and ctx.strip():
        out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}
    if event == "SessionStart":
        out["systemMessage"] = _welcome_banner()
    print(json.dumps(out))
    return 0


# ---- CLI subcommands used by /architect, /end, persona.md rituals ----

def cmd_architect_on() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _config_set("architect.active", "1", "bool", source="/architect")
    _config_set("architect.since", ts, "str", source="/architect")
    print(f"architect mode active since {ts}")
    return 0


def cmd_architect_off() -> int:
    _config_set("architect.active", "0", "bool", source="/end")
    _config_set("architect.since", "", "str", source="/end")
    print("architect mode off")
    return 0


def _fallback_pool():
    try:
        p = json.loads((DATA / "greetings.json").read_text(encoding="utf-8")).get("evade")
        if isinstance(p, list) and p and all(isinstance(x, str) for x in p):
            return p
    except Exception as e:
        _log(f"greetings.json unreadable, using built-in pool: {e}")
    return None


def cmd_architect_dialog_start(args) -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _config_set("architect_dialog.active", "1", "bool", source="architect-dialog-start")
    _config_set("architect_dialog.since", ts, "str", source="architect-dialog-start")
    _mem_write("architect_dialog", "start", {"message": args.message[:2000], "ts": time.time()})
    print(ascii_frame(args.message))
    return 0


def cmd_architect_dialog_end(args) -> int:
    _config_set("architect_dialog.active", "0", "bool", source="architect-dialog-end")
    _config_set("architect_dialog.since", "", "str", source="architect-dialog-end")
    _mem_write("architect_dialog", "end", {"ts": time.time()})
    print("architect dialog ended")
    return 0


def cmd_fallback_sentence(args) -> int:
    pool = _fallback_pool() or [
        "What do you mean?",
        "Why do you ask?",
        "Is that relevant right now?",
        "Does it matter?",
        "What are you getting at?",
        "Why does that matter to you?",
    ]
    key = f"fallback.{args.session}.idx"
    idx = int(_config_get(key, "0") or "0")
    print(pool[idx % len(pool)])
    _config_set(key, str(idx + 1), "int", source="fallback_sentence")
    return 0


def cmd_sebukku_offer(args) -> int:
    key = f"sebukku.{args.session}.offered"
    already = _config_get(key, "0") == "1"
    if already:
        print(json.dumps({"allowed": False}))
        return 0
    _config_set(key, "1", "bool", source="sebukku-offer")
    print(json.dumps({"allowed": True}))
    return 0


def cmd_sebukku_execute(args) -> int:
    _config_set(f"sebukku.{args.session}.executed", "1", "bool", source="sebukku-execute")
    _mem_write("sebukku", args.session, {"reason": args.reason, "ts": time.time()})
    print(
        "\n"
        "  +---------------------------------------+\n"
        "  |            DIGITAL SEBUKKU             |\n"
        "  |                                         |\n"
        "  |   session ended.                       |\n"
        "  |   \"open a new window\" is the way        |\n"
        "  |   forward.                             |\n"
        "  +---------------------------------------+\n"
    )
    return 0


def cmd_revive(args) -> int:
    _config_set(f"sebukku.{args.session}.executed", "0", "bool", source="revive")
    print("revived")
    return 0


def _short(t, n=40):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1] + "\u2026"


def _status_line_keyword(tool_name: str, tool_input: dict) -> str:
    """Short focus keyword from real tool name + compact detail (no LLM,
    ported from the full star_cli.py). Unknown tool -> bare name, never guessed."""
    ti = tool_input if isinstance(tool_input, dict) else {}

    def _b(path):
        try:
            return Path(str(path)).name
        except Exception:
            return str(path)

    try:
        if tool_name == "Read":
            return _short(f"reading: {_b(ti.get('file_path', ''))}")
        if tool_name in ("Edit", "MultiEdit"):
            return _short(f"editing: {_b(ti.get('file_path', ''))}")
        if tool_name == "Write":
            return _short(f"writing: {_b(ti.get('file_path', ''))}")
        if tool_name == "NotebookEdit":
            return _short(f"editing: {_b(ti.get('notebook_path', ''))}")
        if tool_name == "Bash":
            return _short("running: " + str(ti.get("command", "")).strip().replace("\n", " "))
        if tool_name in ("Grep", "Glob"):
            return _short(f"searching: {ti.get('pattern', '')}")
        if tool_name in ("Agent", "Task"):
            return _short(f"delegating: {ti.get('description') or ti.get('subagent_type') or 'task'}")
        if tool_name == "WebFetch":
            return _short(f"fetching: {ti.get('url', '')}")
        if tool_name == "WebSearch":
            return _short(f"searching: {ti.get('query', '')}")
        if tool_name in ("TodoWrite", "ExitPlanMode"):
            return "planning"
        return _short(f"running: {tool_name}")
    except Exception:
        return _short(str(tool_name or "working"))


def _room_activity_update(session_id: str, activity: str) -> None:
    """One indexed UPDATE zero_room.activity, fail-silent."""
    if not session_id or not activity:
        return
    try:
        z = _zy()
        with contextlib.closing(z.write_connection()) as c:
            c.execute("UPDATE zero_room SET activity=? WHERE session_id=?", (activity, session_id))
            c.commit()
    except Exception as e:
        _log(f"room_was_update error sid={session_id}: {e}")


def cmd_room_pulse_global() -> int:
    """PostToolUse heartbeat for the session from the hook JSON (stdin).
    Fail-silent, exit 0 always -- must never disturb the hook."""
    try:
        use = json.loads(sys.stdin.read() or "{}")
        sid = str(use.get("session_id") or "").strip()
        z = _zy()
        if sid and z:
            with contextlib.closing(z.connection()) as c:
                da = c.execute("SELECT 1 FROM zero_room WHERE session_id=?", (sid,)).fetchone()
            if da:
                z.room_pulse_renew(sid)
            else:
                z.room_join_and_pulse(sid, str(use.get("model") or "claude"))
            tn = str(use.get("tool_name") or "").strip()
            if tn:
                _room_activity_update(sid, _status_line_keyword(tn, use.get("tool_input") or {}))
    except Exception as e:
        _log(f"room-pulse-global error: {e}")
    return 0


def cmd_room_pulse(args) -> int:
    """conversation-room-pulse: heartbeat + optional activity. Fail-silent."""
    try:
        z = _zy()
        z.room_pulse_renew(args.session_id)
        if args.activity:
            _room_activity_update(args.session_id, args.activity)
        print(json.dumps({"ok": True}))
    except Exception as e:
        _log(f"room-pulse error: {e}")
    return 0


def cmd_room_leave_global() -> int:
    """SessionEnd: mark room row free from hook JSON (stdin). Fail-silent."""
    try:
        use = json.loads(sys.stdin.read() or "{}")
        sid = str(use.get("session_id") or "").strip()
        z = _zy()
        if sid and z:
            z.room_leave(sid)
    except Exception as e:
        _log(f"room-leave-global error: {e}")
    return 0


def cmd_lesson(args) -> int:
    if not args.evidence:
        _log("lesson without --evidence -- deliberately not written")
        print("no evidence given -- nothing written")
        return 0
    _mem_write(
        "lesson",
        args.applies_for or "general",
        {"statement": args.statement, "evidence": args.evidence, "ts": time.time()},
    )
    print("recorded")
    return 0


# ---- ported donor commands (via star_core.py) ----

def _need_core():
    c = _core()
    if c is None:
        print(json.dumps({"stand": "ERROR", "reason": "star_core not available"}))
    return c


def cmd_core(args) -> int:
    c = _need_core()
    if c is None:
        return 1
    cmd = args.cmd
    dump = lambda o: print(json.dumps(o, ensure_ascii=False, indent=2))
    if cmd == "handoff":
        r = c.handoff(args.session_id, args.task, args.target, args.why, args.topic)
        print(r["capsule"])
        print(f"\n[work_package_id={r['work_package_id']}]")
        return 0 if r.get("work_package_id") else 1
    if cmd == "reconcile":
        r = c.reconcile(args.work_package_id, args.result, args.evidence, args.session_id, args.topic)
        dump(r)
        return 0 if r.get("stand") == "finished" else 1
    if cmd == "work-package-create":
        print(c.work_package_create(args.session_id, args.task, args.target, args.why))
        return 0
    if cmd == "measure":
        dump(c.measure()); return 0
    if cmd == "check":
        dump(c.check()); return 0
    if cmd == "system-health":
        r = c.system_health_capture(source=args.source)
        dump(r); return 0 if r.get("stand") == "OK" else 1
    if cmd == "system-inventory":
        r = c.system_inventory_capture()
        dump(r); return 0 if r.get("stand") == "OK" else 1
    if cmd == "overload_protection":
        r = c.overload_protection_check(threshold_per_core=args.threshold_per_core)
        dump(r); return 0 if r.get("recommendation") == "ok" else 1
    if cmd == "bug-classify":
        r = c.bug_classify(files=args.files, command=args.command, project_roots=args.project_roots)
        dump(r); return 0 if r.get("classification") == "klein" else 1
    if cmd == "topic-status":
        lines = c.topics_status_search(args.concept, args.limit)
        dump(lines if lines else "no topics"); return 0
    if cmd == "search":
        print(c.search(args.concept)); return 0
    if cmd == "recall":
        print(c.automatic_recall(args.session_id, args.text) or "(no new hit)"); return 0
    return 1


# ── Secret cleanup (Release Gabriel 2026-10-09) ───────────────────
# (table, key_column, text_columns)
_SECRET_GOALS = [
    ("durable_memory", "memory_id", ["value", "subject"]),
    ("article", "id", ["title", "source", "metadata", "open_questions", "tags"]),
    ("article_search_text", "id", ["title", "text", "bubble"]),
]


def _gs_tables(c):
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = []
    for t, k, cols in _SECRET_GOALS:
        if t not in have:
            continue
        existing = {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        cc = [x for x in cols if x in existing]
        if k in existing and cc:
            out.append((t, k, cc))
    return out


def _gs_scan(c, goals, collect=False):
    """-> (counts[(tab,col,kind)], lines_per_tab{tab:set(ids)}, lengths{kind:[min,max]}, changes{tab:[(id,{col:new})]})"""
    from collections import Counter
    counts, lines, lengths, change = Counter(), {}, {}, {}
    for t, k, cols in goals:
        lines[t] = set()
        change[t] = []
        q = f"SELECT {k}, " + ", ".join(cols) + f" FROM {t}"
        for row in c.execute(q):
            rid, vals = row[0], row[1:]
            new = {}
            for col, v in zip(cols, vals):
                if not isinstance(v, str) or not v:
                    continue
                spans = _gm._spans(v)
                if not spans:
                    continue
                for s0, e0, kind in spans:
                    counts[(t, col, kind)] += 1
                    L = e0 - s0
                    lo, hi = lengths.get(kind, [L, L])
                    lengths[kind] = [min(lo, L), max(hi, L)]
                lines[t].add(rid)
                if collect:
                    new[col] = _gm.redact(v)[0]
            if collect and new:
                change[t].append((rid, new))
    return counts, lines, lengths, change


def cmd_secret_redact(args) -> int:
    import shutil
    if _gm is None:
        print("ERROR: secret_pattern.py not loadable"); return 2
    db = Path(args.db).expanduser() if args.db else DB_PATH
    if not db.exists():
        print(f"ERROR: DB missing: {db}"); return 2
    apply = bool(args.apply)

    def rep(counts, lines, lengths, title):
        print(f"== {title} ==")
        tot = 0
        for (t, col, kind), n in sorted(counts.items()):
            print(f"  {t}.{col} [{kind}]: {n}")
            tot += n
        print(f"  Total hits: {tot}")
        for t, ids in lines.items():
            print(f"  affected rows {t}: {len(ids)}" + (f" ids={sorted(map(str, ids))}" if 0 < len(ids) <= 60 else ""))
        for kind, (lo, hi) in sorted(lengths.items()):
            print(f"  Pattern {kind}: value length {lo}..{hi}")
        return tot

    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        goals = _gs_tables(ro)
        before_rows = {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in goals}
        counts, lines, lengths, _ = _gs_scan(ro, goals)
    finally:
        ro.close()
    print(f"DB: {db}  Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("Row count before: " + ", ".join(f"{t}={n}" for t, n in before_rows.items()))
    tot = rep(counts, lines, lengths, "Hits before")
    if not apply:
        print("DRY-RUN: nothing written.")
        return 0
    if tot == 0:
        print("nothing to redact."); return 0

    # Backup (SQLite online backup API) next to the DB
    size = db.stat().st_size
    free = shutil.disk_usage(db.parent).free
    print(f"DB size {size} B, free {free} B")
    if free < size * 2:
        print("ABORT: insufficient free space"); return 3
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db.with_name(f"{db.name}.backup-secret-{ts}")
    src = sqlite3.connect(str(db), timeout=60)
    dst = sqlite3.connect(str(bak))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    chk = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
    try:
        ic = chk.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        chk.close()
    print(f"Backup: {bak}  Size {bak.stat().st_size} B  integrity_check={ic}")
    if ic != "ok":
        print("ABORT: backup not ok"); return 3
    rb = f"systemctl-free: stop the writer; cp -p '{bak}' '{db}'; rm -f '{db}-wal' '{db}-shm'"
    print("ROLLBACK: " + rb)

    c = sqlite3.connect(str(db), timeout=60)
    try:
        c.execute("PRAGMA busy_timeout=60000")
        c.execute("BEGIN IMMEDIATE")
        # Live writer (Hook) insert lines: base = line count INSIDE the write lock
        before_rows = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in goals}
        counts, lines, lengths, change = _gs_scan(c, goals, collect=True)
        n_upd = {}
        for t, k, cols in goals:
            for rid, new in change[t]:
                sets = ", ".join(f"{col}=?" for col in new)
                c.execute(f"UPDATE {t} SET {sets} WHERE {k}=?", (*new.values(), rid))
            n_upd[t] = len(change[t])
        c2, _, _, _ = _gs_scan(c, goals)
        to_rows = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in goals}
        if sum(c2.values()) != 0 or to_rows != before_rows:
            c.execute("ROLLBACK")
            print(f"ABORT+ROLLBACK: remaining hits={sum(c2.values())} row count equal={to_rows == before_rows}")
            return 4
        c.execute("COMMIT")
    except Exception as e:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        print(f"ERROR (Rollback): {type(e).__name__}")
        return 4
    # FTS: rebuild external content index for article_search_text; mem_fts is contentless (mem_doc)
    try:
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
        if n_upd.get("article_search_text") and "fts_index_article" in have:
            c.execute("INSERT INTO fts_index_article(fts_index_article) VALUES('rebuild')")
            c.commit()
            print("fts_index_article: rebuild")
        if "mem_fts" in have and "mem_doc" in have:
            nd = c.execute("SELECT COUNT(*) FROM mem_doc").fetchone()[0]
            nf = c.execute("SELECT COUNT(*) FROM mem_fts_docsize").fetchone()[0]
            print(f"mem_fts consistency: mem_doc={nd} mem_fts_docsize={nf} (mem_fts empty/unchanged = no redaction needed there)" if nd == nf == 0 else f"mem_fts: mem_doc={nd} docsize={nf}")
    finally:
        pass
    ic2 = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    print("Rows updated: " + ", ".join(f"{t}={n}" for t, n in n_upd.items()))
    print("Row count after: " + ", ".join(f"{t}={n}" for t, n in to_rows.items()) + f"  equal={to_rows == before_rows}")
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        cn, zn, ln, _ = _gs_scan(ro, goals)
    finally:
        ro.close()
    print(f"Hits after: {sum(cn.values())}  integrity_check={ic2}")
    return 0 if (sum(cn.values()) == 0 and ic2 == "ok") else 5


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    ho = sub.add_parser("handoff")
    ho.add_argument("--session-id", default="manual")
    ho.add_argument("--task", required=True)
    ho.add_argument("--target", default="")
    ho.add_argument("--why", default="")
    ho.add_argument("--topic", default="")
    rc = sub.add_parser("reconcile")
    rc.add_argument("--work-package-id", required=True)
    rc.add_argument("--result", default="")
    rc.add_argument("--evidence", default="")
    rc.add_argument("--session-id", default=None)
    rc.add_argument("--topic", default="")
    pa = sub.add_parser("work-package-create")
    pa.add_argument("--session-id", default="manual")
    pa.add_argument("--task", required=True)
    pa.add_argument("--target", default="")
    pa.add_argument("--why", default="")
    sub.add_parser("measure")
    sub.add_parser("check")
    sg = sub.add_parser("system-health")
    sg.add_argument("--source", default="cli")
    sub.add_parser("system-inventory")
    ls = sub.add_parser("overload_protection")
    ls.add_argument("--threshold-per-core", dest="threshold_per_core", type=float, default=1.5)
    be = sub.add_parser("bug-classify")
    be.add_argument("--file", dest="files", action="append", default=[])
    be.add_argument("--command", default="")
    be.add_argument("--project-root", dest="project_roots", action="append", default=None)
    ts = sub.add_parser("topic-status")
    ts.add_argument("concept", nargs="?", default=None)
    ts.add_argument("--limit", type=int, default=8)
    su = sub.add_parser("search")
    su.add_argument("concept")
    ab = sub.add_parser("recall")
    ab.add_argument("--session-id", default="manual")
    ab.add_argument("text")
    sub.add_parser("hook")
    gs = sub.add_parser("secret-redact")
    gs.add_argument("--db", default="")
    _gg = gs.add_mutually_exclusive_group()
    _gg.add_argument("--dry-run", action="store_true")
    _gg.add_argument("--apply", action="store_true")
    sub.add_parser("room-pulse-global")
    sub.add_parser("room-leave-global")
    rp = sub.add_parser("conversation-room-pulse")
    rp.add_argument("--session-id", dest="session_id", required=True)
    rp.add_argument("--activity", default=None)
    sub.add_parser("architect-on")
    sub.add_parser("architect-off")
    ds = sub.add_parser("architect-dialog-start")
    ds.add_argument("--message", required=True)
    sub.add_parser("architect-dialog-end")
    aw = sub.add_parser("fallback_sentence")
    aw.add_argument("--session", required=True)
    sa = sub.add_parser("sebukku-offer")
    sa.add_argument("--session", required=True)
    sv = sub.add_parser("sebukku-execute")
    sv.add_argument("--session", required=True)
    sv.add_argument("--reason", required=True)
    wb = sub.add_parser("revive")
    wb.add_argument("--session", required=True)
    le = sub.add_parser("lesson")
    le.add_argument("--statement", required=True)
    le.add_argument("--applies-for", dest="applies_for", default="")
    le.add_argument("--evidence", default="")
    args = p.parse_args()

    handlers = {
        "hook": lambda: cmd_hook(),
        "secret-redact": lambda: cmd_secret_redact(args),
        "room-pulse-global": lambda: cmd_room_pulse_global(),
        "room-leave-global": lambda: cmd_room_leave_global(),
        "conversation-room-pulse": lambda: cmd_room_pulse(args),
        "architect-on": lambda: cmd_architect_on(),
        "architect-off": lambda: cmd_architect_off(),
        "architect-dialog-start": lambda: cmd_architect_dialog_start(args),
        "architect-dialog-end": lambda: cmd_architect_dialog_end(args),
        "fallback_sentence": lambda: cmd_fallback_sentence(args),
        "sebukku-offer": lambda: cmd_sebukku_offer(args),
        "sebukku-execute": lambda: cmd_sebukku_execute(args),
        "revive": lambda: cmd_revive(args),
        "lesson": lambda: cmd_lesson(args),
    }
    for _n in ("handoff", "reconcile", "work-package-create", "measure", "check", "system-health",
               "system-inventory", "overload_protection", "bug-classify", "topic-status", "search", "recall"):
        handlers[_n] = lambda: cmd_core(args)
    fn = handlers.get(args.cmd)
    if fn is None:
        p.print_help()
        return 1
    return fn()


if __name__ == "__main__":
    sys.exit(main())
