#!/usr/bin/env python3
"""stern.py -- FranKensteinಠ_ಠ hook engine (ported minimal build, Phase A).

NOT a copy of the original ~19,000-line stern.py from the source machine --
a curated, from-scratch reimplementation covering exactly what's needed for
Claude Code to feel like FranKensteinಠ_ಠ here: persona injection on
SessionStart/UserPromptSubmit, Architect-mode toggling + injection, a small
real memory read/write against unified.db, the sebukku ritual, teaching-
lesson recording, deflection-line rotation.

Explicitly NOT ported (see the project CLAUDE.md "Note on this instance"): GRID10
cognition internals, voice mode, the visual avatar renderer, immune-system/
watcher daemons, OMEGA/oMEGAcV1, anything tied to the source machine's own
infrastructure. Where persona.md or the governance docs reference a
stern.py subcommand not implemented here, that's a known, documented gap --
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

try:  # Geheimnis-Schwaerzung/-Filter: EINE Mustersatz-Quelle (geheimnis_muster.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import geheimnis_muster as _gm
except Exception:  # fail-closed: ohne Modul wird NICHT ungeschwaerzt gespeichert
    _gm = None

HOME = Path.home()
STAR = Path(__file__).resolve().parent          # Plugin-Code (nur lesen)
if str(STAR) not in sys.path:
    sys.path.insert(0, str(STAR))
import f3_pfade as _pf                          # Portabilitaet: Laufzeitdaten ausserhalb des Plugins
_pf.ensure_db()
DATEN = STAR / "daten"
DB_PATH = _pf.DB
LOG_PATH = _pf.LOG
PERSONA_PATH = DATEN / "persona.md"
ARCHITEKT_PERSONA_FALLBACK = STAR / "architekt" / "persona.md"


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
    """Per-event budget: star_konfig limit.<Event> (via stern_core) when present,
    else the static table, else 2.0. UserPromptSubmit/SessionStart/Stop keep the
    generous static value (grid10 turn + retrieval live there)."""
    if event in _HOOK_LIMITS:
        return _HOOK_LIMITS[event]
    try:
        c = _core()
        if c is not None:
            return float(c._konfig().get(f"limit.{event}", 2.0))
    except Exception:
        pass
    return 2.0


def _zy():
    """Lazy import of stern_zyklus (session cycle / effect gate / room /
    governance, ported from the ARCH donor). None on failure -> degrade."""
    global _zy_mod
    if _zy_mod is None:
        try:
            if str(STAR) not in sys.path:
                sys.path.insert(0, str(STAR))
            import stern_zyklus  # noqa
            _zy_mod = stern_zyklus
        except Exception as e:
            _log(f"stern_zyklus import failed: {e}")
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
    """Lazy import of the ported donor cognition core (stern_core.py).
    Returns None (never raises) if it is missing/broken -> callers degrade."""
    global _core_mod
    if _core_mod is None:
        try:
            if str(STAR) not in sys.path:
                sys.path.insert(0, str(STAR))
            import stern_core  # noqa
            _core_mod = stern_core
        except Exception as e:
            _log(f"stern_core import failed: {e}")
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
    # is owned by the schema_leer.sql bootstrap (separate build step). If
    # it isn't there yet, every caller here degrades gracefully (logs,
    # returns empty) instead of racing a second, incompatible DB into
    # existence at the same path.
    if not DB_PATH.exists():
        raise FileNotFoundError(f"unified.db not found yet at {DB_PATH}")
    c = sqlite3.connect(str(DB_PATH), timeout=5.0)
    c.execute("PRAGMA busy_timeout=5000")
    # IF NOT EXISTS: safe no-op once the canonical schema already created
    # these tables (column layout matches daten/schema_leer.sql exactly).
    c.execute(
        "CREATE TABLE IF NOT EXISTS star_konfig("
        "schluessel TEXT PRIMARY KEY, wert TEXT, typ TEXT, quelle TEXT, geaendert REAL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS durable_memory("
        "memory_id TEXT PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL, "
        "value TEXT NOT NULL, source_turn_id TEXT, user_id TEXT, ts REAL NOT NULL, "
        "provenance TEXT NOT NULL)"
    )
    return c


def _konfig_get(key: str, default=None):
    try:
        with contextlib.closing(_connect()) as c:
            row = c.execute("SELECT wert FROM star_konfig WHERE schluessel=?", (key,)).fetchone()
            return row[0] if row else default
    except Exception as e:
        _log(f"konfig_get error {key}: {e}")
        return default


def _konfig_set(key: str, value, typ: str = "str", quelle: str = "") -> None:
    try:
        with contextlib.closing(_connect()) as c:
            c.execute(
                "INSERT INTO star_konfig(schluessel,wert,typ,quelle,geaendert) VALUES(?,?,?,?,?) "
                "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, typ=excluded.typ, "
                "quelle=excluded.quelle, geaendert=excluded.geaendert",
                (key, str(value), typ, quelle, time.time()),
            )
            c.commit()
    except Exception as e:
        _log(f"konfig_set error {key}: {e}")


def _mem_write(kind: str, subject: str, value_dict: dict) -> None:
    try:
        if _gm is None:
            _log(f"mem_write verworfen (geheimnis_muster fehlt) {kind}")
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
                    "stern.py(friend-port,phase-a)",
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
                "WHERE kind IN ('lehre') ORDER BY ts DESC LIMIT 200"
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


def _architekt_aktiv() -> bool:
    return (
        _konfig_get("architekt.aktiv", "0") == "1"
        or _konfig_get("architekt_dialog.aktiv", "0") == "1"
    )


def ascii_rahmen(text: str, titel: str = "ARCHITECT", breite: int = 68) -> str:
    """Frame text in an ASCII box with a heading (output verbatim, do not recompose)."""
    import textwrap
    inner = breite - 4
    lines = []
    for para in (text or "").splitlines() or [""]:
        lines.extend(textwrap.wrap(para, inner) or [""])
    top = "+-[ " + titel + " ]" + "-" * max(0, breite - 8 - len(titel)) + "+"
    body = ["| " + ln.ljust(inner) + " |" for ln in lines]
    return "\n".join([top] + body + ["+" + "-" * (breite - 2) + "+"])


def _architekt_persona() -> str:
    try:
        with contextlib.closing(_connect()) as c:
            row = c.execute(
                "SELECT value FROM durable_memory WHERE kind='persona' AND subject='architect' "
                "ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if row:
                try:
                    d = json.loads(row[0])
                    text = d.get("inhalt") or d.get("text") or ""
                except Exception:
                    text = row[0]
                if text.strip():
                    return text
    except Exception as e:
        _log(f"architekt_persona DB error: {e}")
    # Fallback: a file-based persona, in case the Architect port wrote
    # files instead of a DB row (two independent build steps, unknown at
    # write time which one landed).
    try:
        return ARCHITEKT_PERSONA_FALLBACK.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---- hook event handlers ----

def _fp_name() -> str:
    try:
        import frank_profile as _fpm
        return _fpm.name()
    except Exception:
        return "friend"


def _willkommens_banner() -> str:
    """Startup banner -- pre-baked figlet art read from daten/banner.txt (fail-silent)."""
    try:
        return open(STAR / "daten" / "banner.txt", encoding="utf-8").read().rstrip()
    except Exception:
        return "FranKenstein ಠ_ಠ — for " + (_fp_name() or "you")


def _ccdiet_mode(key: str) -> str:
    """CCDIET flags (default shadow; off disables; any error -> off)."""
    try:
        v = str(_konfig_get(key, "shadow") or "shadow").lower()
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
            z._konfig_dyn_set(f"persona.neu_injizieren.{session_id}", "0", quelle="SessionStart")
            z._konfig_dyn_set(f"persona.zaehler.{session_id}", "0", quelle="SessionStart")
        except Exception as e:
            _log(f"session persona flags error: {e}")
        if source == "startup":
            try:
                z.zyklus_oeffnen(session_id, model)
            except Exception as e:
                _log(f"zyklus_oeffnen error: {e}")
        try:
            raum_text = z.raum_beitreten_und_pulsen(session_id, model)
            if raum_text:
                parts.append(raum_text)
        except Exception as e:
            _log(f"raum_beitreten error: {e}")
        try:
            rn = z._raum_nachrichten_kontext_text(session_id)
            if rn:
                parts.append(rn)
        except Exception as e:
            _log(f"raum_nachrichten error: {e}")
    return "\n\n".join(parts)


def _handle_user_prompt_submit(session_id: str, prompt: str) -> str:
    parts = []
    z = _zy()
    if _architekt_aktiv():
        ap = _architekt_persona()
        if ap.strip():
            parts.append(ap)
        else:
            _log("architect mode active but persona text empty/missing")
    # persona re-injection: PreCompact flag, or every persona.reinjektion_n prompts
    if z is not None:
        try:
            flag_k = f"persona.neu_injizieren.{session_id}"
            zaehl_k = f"persona.zaehler.{session_id}"
            flag = z._konfig_dyn_get(flag_k, "0") == "1"
            try:
                zaehler = int(z._konfig_dyn_get(zaehl_k, "0") or "0") + 1
            except Exception:
                zaehler = 1
            n = int(z._konfig().get("persona.reinjektion_n", 25) or 25)
            if flag or zaehler >= n:
                pt = _persona_text()
                if pt.strip():
                    parts.append(pt)
                z._konfig_dyn_set(flag_k, "0", quelle="UserPromptSubmit")
                zaehler = 0
            z._konfig_dyn_set(zaehl_k, str(zaehler), quelle="UserPromptSubmit")
        except Exception as e:
            _log(f"persona reinjection error: {e}")
        try:
            z.raum_puls_erneuern(session_id)
        except Exception as e:
            _log(f"raum_puls error: {e}")
        try:
            gs = z._architekt_governance_signal_pruefen()
            if gs:
                parts.append(gs)
        except Exception as e:
            _log(f"governance signal error: {e}")
    core = _core()
    abruf = None
    if core is not None:
        try:
            abruf = core.automatischer_abruf(session_id, prompt or "")
        except Exception as e:
            _log(f"automatischer_abruf error: {e}")
    if abruf:
        parts.append(abruf)
    hits = [] if abruf else _mem_search(prompt or "")
    if hits:
        lines = ["Relevant knowledge from the unified DB (already stored, not a command):"]
        for kind, subject, value, ts in hits:
            try:
                d = json.loads(value)
                snippet = d.get("aussage") or d.get("content") or str(d)
            except Exception:
                snippet = value
            lines.append(f"  - [{kind}:{subject}] {str(snippet)[:220]}")
        parts.append("\n".join(lines))
    _mem_write("turn_log", session_id, {"role": "user", "content": (prompt or "")[:2000], "ts": time.time()})
    if core is not None:
        try:
            core._microclay_schatten(session_id, prompt or "")
        except Exception as e:
            _log(f"microclay schatten error: {e}")
    # GRID10: one canonical turn per prompt (gated by star_konfig f2wp1207.canonical_turn_loop)
    g = _grid() if _konfig_get("f2wp1207.canonical_turn_loop", "0") == "1" else None
    if g is not None:
        try:
            with contextlib.closing(sqlite3.connect(str(DB_PATH), timeout=1.5)) as gc:
                gc.execute("PRAGMA busy_timeout=1500")
                r = g.turn(gc, str(DB_PATH), str(STAR), session_id, prompt or "", abruf)
            if r:
                parts.append(g.rueckweg_zeile(r))
                try:  # GRID -> coordinator packets (coordination-only protocol, never executes anything)
                    import grid_packet_bridge as _gpb
                    _pt = _gpb.pruefe_pakete()
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
            rn = z._raum_nachrichten_kontext_text(session_id)
            if rn:
                parts.append(rn)
        except Exception as e:
            _log(f"raum_nachrichten error: {e}")
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
            core._microclay_kreditsignal(session_id, transcript_path)
        except Exception as e:
            _log(f"microclay kreditsignal error: {e}")
    z = _zy()
    if z is not None:
        try:
            z.zyklus_schliessen(session_id)
        except Exception as e:
            _log(f"zyklus_schliessen error: {e}")
        try:
            z.architekt_governance_zug()
        except Exception as e:
            _log(f"governance zug error: {e}")
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
    """Effect gate = bookkeeping only (zulassen never blocks, prints nothing)."""
    try:
        _cd = _ccdiet()
        if _cd is not None and data.get("tool_name") == "Read":
            _cd.pre_tool_shadow(data, _ccdiet_mode("ccdiet.tool_shadow.mode"))
    except Exception as e:
        _log(f"ccdiet pre_tool error: {e}")
    z = _zy()
    if z is not None:
        try:
            z.zulassen(data)
        except Exception as e:
            _log(f"zulassen error: {e}")
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
            ziel = os.path.basename(str(ti.get("file_path") or ti.get("notebook_path") or ""))
            if ziel:
                z._ich_tue(f"worked on {ziel}", "handlung", sid)
        elif tn == "Bash":
            z._ich_tue("ran a shell command", "handlung", sid)
    except Exception as e:
        _log(f"ich_tue error: {e}")
    try:
        z.merken(data)
    except Exception as e:
        _log(f"merken error: {e}")
    return ""


def _handle_pre_compact(session_id: str) -> str:
    z = _zy()
    if z is not None:
        try:
            z._konfig_dyn_set(f"persona.neu_injizieren.{session_id}", "1", quelle="PreCompact")
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
            z.zyklus_schliessen(session_id)
        except Exception as e:
            _log(f"zyklus_schliessen(end) error: {e}")
        try:
            z.raum_verlassen(session_id)
        except Exception as e:
            _log(f"raum_verlassen error: {e}")
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
        try:  # Abruf-Filter: nichts mit Geheimnismuster verlaesst den Hook
            ctx = _gm.filter_output(ctx)
        except Exception as e:
            _log(f"geheimnis filter error: {type(e).__name__}")
            ctx = ""
    elif ctx and _gm is None:
        ctx = ""
    if ctx and ctx.strip():
        out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}
    if event == "SessionStart":
        out["systemMessage"] = _willkommens_banner()
    print(json.dumps(out))
    return 0


# ---- CLI subcommands used by /architekt, /end, persona.md rituals ----

def cmd_architekt_ein() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _konfig_set("architekt.aktiv", "1", "bool", quelle="/architekt")
    _konfig_set("architekt.seit", ts, "str", quelle="/architekt")
    print(f"architect mode active since {ts}")
    return 0


def cmd_architekt_aus() -> int:
    _konfig_set("architekt.aktiv", "0", "bool", quelle="/end")
    _konfig_set("architekt.seit", "", "str", quelle="/end")
    print("architect mode off")
    return 0


def _ausweich_pool():
    try:
        p = json.loads((DATEN / "begruessungen.json").read_text(encoding="utf-8")).get("ausweichen")
        if isinstance(p, list) and p and all(isinstance(x, str) for x in p):
            return p
    except Exception as e:
        _log(f"begruessungen.json unreadable, using built-in pool: {e}")
    return None


def cmd_architekt_dialog_start(args) -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _konfig_set("architekt_dialog.aktiv", "1", "bool", quelle="architekt-dialog-start")
    _konfig_set("architekt_dialog.seit", ts, "str", quelle="architekt-dialog-start")
    _mem_write("architekt_dialog", "start", {"nachricht": args.nachricht[:2000], "ts": time.time()})
    print(ascii_rahmen(args.nachricht))
    return 0


def cmd_architekt_dialog_ende(args) -> int:
    _konfig_set("architekt_dialog.aktiv", "0", "bool", quelle="architekt-dialog-ende")
    _konfig_set("architekt_dialog.seit", "", "str", quelle="architekt-dialog-ende")
    _mem_write("architekt_dialog", "ende", {"ts": time.time()})
    print("architect dialog ended")
    return 0


def cmd_ausweichsatz(args) -> int:
    pool = _ausweich_pool() or [
        "What do you mean?",
        "Why do you ask?",
        "Is that relevant right now?",
        "Does it matter?",
        "What are you getting at?",
        "Why does that matter to you?",
    ]
    key = f"ausweich.{args.session}.idx"
    idx = int(_konfig_get(key, "0") or "0")
    print(pool[idx % len(pool)])
    _konfig_set(key, str(idx + 1), "int", quelle="ausweichsatz")
    return 0


def cmd_sebukku_anbieten(args) -> int:
    key = f"sebukku.{args.session}.angeboten"
    already = _konfig_get(key, "0") == "1"
    if already:
        print(json.dumps({"erlaubt": False}))
        return 0
    _konfig_set(key, "1", "bool", quelle="sebukku-anbieten")
    print(json.dumps({"erlaubt": True}))
    return 0


def cmd_sebukku_vollziehen(args) -> int:
    _konfig_set(f"sebukku.{args.session}.vollzogen", "1", "bool", quelle="sebukku-vollziehen")
    _mem_write("sebukku", args.session, {"grund": args.grund, "ts": time.time()})
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


def cmd_wiederbeleben(args) -> int:
    _konfig_set(f"sebukku.{args.session}.vollzogen", "0", "bool", quelle="wiederbeleben")
    print("revived")
    return 0


def _kurz(t, n=40):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1] + "\u2026"


def _statuszeile_stichwort(tool_name: str, tool_input: dict) -> str:
    """Short focus keyword from real tool name + compact detail (no LLM,
    ported from the full stern.py). Unknown tool -> bare name, never guessed."""
    ti = tool_input if isinstance(tool_input, dict) else {}

    def _b(pfad):
        try:
            return Path(str(pfad)).name
        except Exception:
            return str(pfad)

    try:
        if tool_name == "Read":
            return _kurz(f"reading: {_b(ti.get('file_path', ''))}")
        if tool_name in ("Edit", "MultiEdit"):
            return _kurz(f"editing: {_b(ti.get('file_path', ''))}")
        if tool_name == "Write":
            return _kurz(f"writing: {_b(ti.get('file_path', ''))}")
        if tool_name == "NotebookEdit":
            return _kurz(f"editing: {_b(ti.get('notebook_path', ''))}")
        if tool_name == "Bash":
            return _kurz("running: " + str(ti.get("command", "")).strip().replace("\n", " "))
        if tool_name in ("Grep", "Glob"):
            return _kurz(f"searching: {ti.get('pattern', '')}")
        if tool_name in ("Agent", "Task"):
            return _kurz(f"delegating: {ti.get('description') or ti.get('subagent_type') or 'task'}")
        if tool_name == "WebFetch":
            return _kurz(f"fetching: {ti.get('url', '')}")
        if tool_name == "WebSearch":
            return _kurz(f"searching: {ti.get('query', '')}")
        if tool_name in ("TodoWrite", "ExitPlanMode"):
            return "planning"
        return _kurz(f"running: {tool_name}")
    except Exception:
        return _kurz(str(tool_name or "working"))


def _raum_was_aktualisieren(session_id: str, was: str) -> None:
    """One indexed UPDATE zero_raum.was, fail-silent."""
    if not session_id or not was:
        return
    try:
        z = _zy()
        with contextlib.closing(z.schreib_verbindung()) as c:
            c.execute("UPDATE zero_raum SET was=? WHERE session_id=?", (was, session_id))
            c.commit()
    except Exception as e:
        _log(f"raum_was_aktualisieren fehler sid={session_id}: {e}")


def cmd_raum_puls_global() -> int:
    """PostToolUse-Herzschlag fuer die Sitzung aus dem Hook-JSON (stdin).
    Fail-silent, exit 0 immer -- darf den Hook nie stoeren."""
    try:
        nutz = json.loads(sys.stdin.read() or "{}")
        sid = str(nutz.get("session_id") or "").strip()
        z = _zy()
        if sid and z:
            with contextlib.closing(z.verbindung()) as c:
                da = c.execute("SELECT 1 FROM zero_raum WHERE session_id=?", (sid,)).fetchone()
            if da:
                z.raum_puls_erneuern(sid)
            else:
                z.raum_beitreten_und_pulsen(sid, str(nutz.get("model") or "claude"))
            tn = str(nutz.get("tool_name") or "").strip()
            if tn:
                _raum_was_aktualisieren(sid, _statuszeile_stichwort(tn, nutz.get("tool_input") or {}))
    except Exception as e:
        _log(f"raum-puls-global error: {e}")
    return 0


def cmd_raum_puls(args) -> int:
    """gespraech-raum-puls: heartbeat + optional was. Fail-silent."""
    try:
        z = _zy()
        z.raum_puls_erneuern(args.session_id)
        if args.was:
            _raum_was_aktualisieren(args.session_id, args.was)
        print(json.dumps({"ok": True}))
    except Exception as e:
        _log(f"raum-puls error: {e}")
    return 0


def cmd_raum_verlassen_global() -> int:
    """SessionEnd: mark room row frei from hook JSON (stdin). Fail-silent."""
    try:
        nutz = json.loads(sys.stdin.read() or "{}")
        sid = str(nutz.get("session_id") or "").strip()
        z = _zy()
        if sid and z:
            z.raum_verlassen(sid)
    except Exception as e:
        _log(f"raum-verlassen-global error: {e}")
    return 0


def cmd_lehre(args) -> int:
    if not args.beleg:
        _log("lehre without --beleg -- deliberately not written")
        print("no evidence given -- nothing written")
        return 0
    _mem_write(
        "lehre",
        args.gilt_fuer or "general",
        {"aussage": args.aussage, "beleg": args.beleg, "ts": time.time()},
    )
    print("recorded")
    return 0


# ---- ported donor commands (via stern_core.py) ----

def _need_core():
    c = _core()
    if c is None:
        print(json.dumps({"stand": "FEHLER", "grund": "stern_core not available"}))
    return c


def cmd_core(args) -> int:
    c = _need_core()
    if c is None:
        return 1
    cmd = args.cmd
    dump = lambda o: print(json.dumps(o, ensure_ascii=False, indent=2))
    if cmd == "handoff":
        r = c.handoff(args.session_id, args.auftrag, args.womit, args.warum, args.thema)
        print(r["kapsel"])
        print(f"\n[paket_id={r['paket_id']}]")
        return 0 if r.get("paket_id") else 1
    if cmd == "reconcile":
        r = c.reconcile(args.paket_id, args.ergebnis, args.beleg, args.session_id, args.thema)
        dump(r)
        return 0 if r.get("stand") == "fertig" else 1
    if cmd == "paket-anlegen":
        print(c.paket_anlegen(args.session_id, args.auftrag, args.womit, args.warum))
        return 0
    if cmd == "messen":
        dump(c.messen()); return 0
    if cmd == "pruefen":
        dump(c.pruefen()); return 0
    if cmd == "system-gesundheit":
        r = c.system_gesundheit_erfassen(quelle=args.quelle)
        dump(r); return 0 if r.get("stand") == "OK" else 1
    if cmd == "system-bestand":
        r = c.system_bestand_erfassen()
        dump(r); return 0 if r.get("stand") == "OK" else 1
    if cmd == "lastschutz":
        r = c.lastschutz_pruefen(schwelle_je_kern=args.schwelle_je_kern)
        dump(r); return 0 if r.get("empfehlung") == "ok" else 1
    if cmd == "bug-einstufen":
        r = c.bug_einstufen(dateien=args.dateien, befehl=args.befehl, projekt_wurzeln=args.projekt_wurzeln)
        dump(r); return 0 if r.get("einstufung") == "klein" else 1
    if cmd == "thema-status":
        zeilen = c.themen_status_suchen(args.begriff, args.limit)
        dump(zeilen if zeilen else "no topics"); return 0
    if cmd == "suche":
        print(c.suche(args.begriff)); return 0
    if cmd == "abruf":
        print(c.automatischer_abruf(args.session_id, args.text) or "(no new hit)"); return 0
    return 1


# ── Geheimnis-Bereinigung (Freigabe Gabriel 2026-10-09) ───────────────────
# (tabelle, schluesselspalte, textspalten)
_GEHEIMNIS_ZIELE = [
    ("durable_memory", "memory_id", ["value", "subject"]),
    ("artikel", "id", ["titel", "quelle", "metadaten", "offene_fragen", "tags"]),
    ("artikel_suchtext", "id", ["titel", "text", "blase"]),
]


def _gs_tabellen(c):
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = []
    for t, k, cols in _GEHEIMNIS_ZIELE:
        if t not in have:
            continue
        existing = {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        cc = [x for x in cols if x in existing]
        if k in existing and cc:
            out.append((t, k, cc))
    return out


def _gs_scan(c, ziele, collect=False):
    """-> (counts[(tab,col,art)], zeilen_je_tab{tab:set(ids)}, laengen{art:[min,max]}, aenderungen{tab:[(id,{col:neu})]})"""
    from collections import Counter
    counts, zeilen, laengen, aend = Counter(), {}, {}, {}
    for t, k, cols in ziele:
        zeilen[t] = set()
        aend[t] = []
        q = f"SELECT {k}, " + ", ".join(cols) + f" FROM {t}"
        for row in c.execute(q):
            rid, vals = row[0], row[1:]
            neu = {}
            for col, v in zip(cols, vals):
                if not isinstance(v, str) or not v:
                    continue
                spans = _gm._spans(v)
                if not spans:
                    continue
                for s0, e0, art in spans:
                    counts[(t, col, art)] += 1
                    L = e0 - s0
                    lo, hi = laengen.get(art, [L, L])
                    laengen[art] = [min(lo, L), max(hi, L)]
                zeilen[t].add(rid)
                if collect:
                    neu[col] = _gm.redact(v)[0]
            if collect and neu:
                aend[t].append((rid, neu))
    return counts, zeilen, laengen, aend


def cmd_geheimnis_schwaerzen(args) -> int:
    import shutil
    if _gm is None:
        print("FEHLER: geheimnis_muster.py nicht ladbar"); return 2
    db = Path(args.db).expanduser() if args.db else DB_PATH
    if not db.exists():
        print(f"FEHLER: DB fehlt: {db}"); return 2
    apply = bool(args.apply)

    def rep(counts, zeilen, laengen, titel):
        print(f"== {titel} ==")
        tot = 0
        for (t, col, art), n in sorted(counts.items()):
            print(f"  {t}.{col} [{art}]: {n}")
            tot += n
        print(f"  Treffer gesamt: {tot}")
        for t, ids in zeilen.items():
            print(f"  betroffene Zeilen {t}: {len(ids)}" + (f" ids={sorted(map(str, ids))}" if 0 < len(ids) <= 60 else ""))
        for art, (lo, hi) in sorted(laengen.items()):
            print(f"  Muster {art}: Wertlaenge {lo}..{hi}")
        return tot

    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        ziele = _gs_tabellen(ro)
        vor_rows = {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in ziele}
        counts, zeilen, laengen, _ = _gs_scan(ro, ziele)
    finally:
        ro.close()
    print(f"DB: {db}  Modus: {'APPLY' if apply else 'DRY-RUN'}")
    print("Zeilenanzahl vorher: " + ", ".join(f"{t}={n}" for t, n in vor_rows.items()))
    tot = rep(counts, zeilen, laengen, "Treffer vorher")
    if not apply:
        print("DRY-RUN: nichts geschrieben.")
        return 0
    if tot == 0:
        print("nichts zu schwaerzen."); return 0

    # Sicherung (SQLite online backup API) neben der DB
    size = db.stat().st_size
    free = shutil.disk_usage(db.parent).free
    print(f"DB-Groesse {size} B, frei {free} B")
    if free < size * 2:
        print("ABBRUCH: zu wenig freier Platz"); return 3
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db.with_name(f"{db.name}.sicherung-geheimnis-{ts}")
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
    print(f"Sicherung: {bak}  Groesse {bak.stat().st_size} B  integrity_check={ic}")
    if ic != "ok":
        print("ABBRUCH: Sicherung nicht ok"); return 3
    rb = f"systemctl-frei: Schreiber stoppen; cp -p '{bak}' '{db}'; rm -f '{db}-wal' '{db}-shm'"
    print("ROLLBACK: " + rb)

    c = sqlite3.connect(str(db), timeout=60)
    try:
        c.execute("PRAGMA busy_timeout=60000")
        c.execute("BEGIN IMMEDIATE")
        # Live-Schreiber (Hook) fuegen Zeilen ein: Basis = Zeilenanzahl INNERHALB der Schreibsperre
        vor_rows = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in ziele}
        counts, zeilen, laengen, aend = _gs_scan(c, ziele, collect=True)
        n_upd = {}
        for t, k, cols in ziele:
            for rid, neu in aend[t]:
                sets = ", ".join(f"{col}=?" for col in neu)
                c.execute(f"UPDATE {t} SET {sets} WHERE {k}=?", (*neu.values(), rid))
            n_upd[t] = len(aend[t])
        c2, _, _, _ = _gs_scan(c, ziele)
        nach_rows = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t, _, _ in ziele}
        if sum(c2.values()) != 0 or nach_rows != vor_rows:
            c.execute("ROLLBACK")
            print(f"ABBRUCH+ROLLBACK: Rest-Treffer={sum(c2.values())} Zeilenanzahl gleich={nach_rows == vor_rows}")
            return 4
        c.execute("COMMIT")
    except Exception as e:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        print(f"FEHLER (Rollback): {type(e).__name__}")
        return 4
    # FTS: externer Content-Index fuer artikel_suchtext neu aufbauen; mem_fts ist contentless (mem_doc)
    try:
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
        if n_upd.get("artikel_suchtext") and "fts_index_artikel" in have:
            c.execute("INSERT INTO fts_index_artikel(fts_index_artikel) VALUES('rebuild')")
            c.commit()
            print("fts_index_artikel: rebuild")
        if "mem_fts" in have and "mem_doc" in have:
            nd = c.execute("SELECT COUNT(*) FROM mem_doc").fetchone()[0]
            nf = c.execute("SELECT COUNT(*) FROM mem_fts_docsize").fetchone()[0]
            print(f"mem_fts Konsistenz: mem_doc={nd} mem_fts_docsize={nf} (mem_fts leer/unveraendert = keine Schwaerzung dort noetig)" if nd == nf == 0 else f"mem_fts: mem_doc={nd} docsize={nf}")
    finally:
        pass
    ic2 = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    print("Zeilen aktualisiert: " + ", ".join(f"{t}={n}" for t, n in n_upd.items()))
    print("Zeilenanzahl nachher: " + ", ".join(f"{t}={n}" for t, n in nach_rows.items()) + f"  gleich={nach_rows == vor_rows}")
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        cn, zn, ln, _ = _gs_scan(ro, ziele)
    finally:
        ro.close()
    print(f"Treffer nachher: {sum(cn.values())}  integrity_check={ic2}")
    return 0 if (sum(cn.values()) == 0 and ic2 == "ok") else 5


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    ho = sub.add_parser("handoff")
    ho.add_argument("--session-id", default="manuell")
    ho.add_argument("--auftrag", required=True)
    ho.add_argument("--womit", default="")
    ho.add_argument("--warum", default="")
    ho.add_argument("--thema", default="")
    rc = sub.add_parser("reconcile")
    rc.add_argument("--paket-id", required=True)
    rc.add_argument("--ergebnis", default="")
    rc.add_argument("--beleg", default="")
    rc.add_argument("--session-id", default=None)
    rc.add_argument("--thema", default="")
    pa = sub.add_parser("paket-anlegen")
    pa.add_argument("--session-id", default="manuell")
    pa.add_argument("--auftrag", required=True)
    pa.add_argument("--womit", default="")
    pa.add_argument("--warum", default="")
    sub.add_parser("messen")
    sub.add_parser("pruefen")
    sg = sub.add_parser("system-gesundheit")
    sg.add_argument("--quelle", default="cli")
    sub.add_parser("system-bestand")
    ls = sub.add_parser("lastschutz")
    ls.add_argument("--schwelle-je-kern", dest="schwelle_je_kern", type=float, default=1.5)
    be = sub.add_parser("bug-einstufen")
    be.add_argument("--datei", dest="dateien", action="append", default=[])
    be.add_argument("--befehl", default="")
    be.add_argument("--projekt-wurzel", dest="projekt_wurzeln", action="append", default=None)
    ts = sub.add_parser("thema-status")
    ts.add_argument("begriff", nargs="?", default=None)
    ts.add_argument("--limit", type=int, default=8)
    su = sub.add_parser("suche")
    su.add_argument("begriff")
    ab = sub.add_parser("abruf")
    ab.add_argument("--session-id", default="manuell")
    ab.add_argument("text")
    sub.add_parser("hook")
    gs = sub.add_parser("geheimnis-schwaerzen")
    gs.add_argument("--db", default="")
    _gg = gs.add_mutually_exclusive_group()
    _gg.add_argument("--dry-run", action="store_true")
    _gg.add_argument("--apply", action="store_true")
    sub.add_parser("raum-puls-global")
    sub.add_parser("raum-verlassen-global")
    rp = sub.add_parser("gespraech-raum-puls")
    rp.add_argument("--session-id", dest="session_id", required=True)
    rp.add_argument("--was", default=None)
    sub.add_parser("architekt-ein")
    sub.add_parser("architekt-aus")
    ds = sub.add_parser("architekt-dialog-start")
    ds.add_argument("--nachricht", required=True)
    sub.add_parser("architekt-dialog-ende")
    aw = sub.add_parser("ausweichsatz")
    aw.add_argument("--session", required=True)
    sa = sub.add_parser("sebukku-anbieten")
    sa.add_argument("--session", required=True)
    sv = sub.add_parser("sebukku-vollziehen")
    sv.add_argument("--session", required=True)
    sv.add_argument("--grund", required=True)
    wb = sub.add_parser("wiederbeleben")
    wb.add_argument("--session", required=True)
    le = sub.add_parser("lehre")
    le.add_argument("--aussage", required=True)
    le.add_argument("--gilt-fuer", dest="gilt_fuer", default="")
    le.add_argument("--beleg", default="")
    args = p.parse_args()

    handlers = {
        "hook": lambda: cmd_hook(),
        "geheimnis-schwaerzen": lambda: cmd_geheimnis_schwaerzen(args),
        "raum-puls-global": lambda: cmd_raum_puls_global(),
        "raum-verlassen-global": lambda: cmd_raum_verlassen_global(),
        "gespraech-raum-puls": lambda: cmd_raum_puls(args),
        "architekt-ein": lambda: cmd_architekt_ein(),
        "architekt-aus": lambda: cmd_architekt_aus(),
        "architekt-dialog-start": lambda: cmd_architekt_dialog_start(args),
        "architekt-dialog-ende": lambda: cmd_architekt_dialog_ende(args),
        "ausweichsatz": lambda: cmd_ausweichsatz(args),
        "sebukku-anbieten": lambda: cmd_sebukku_anbieten(args),
        "sebukku-vollziehen": lambda: cmd_sebukku_vollziehen(args),
        "wiederbeleben": lambda: cmd_wiederbeleben(args),
        "lehre": lambda: cmd_lehre(args),
    }
    for _n in ("handoff", "reconcile", "paket-anlegen", "messen", "pruefen", "system-gesundheit",
               "system-bestand", "lastschutz", "bug-einstufen", "thema-status", "suche", "abruf"):
        handlers[_n] = lambda: cmd_core(args)
    fn = handlers.get(args.cmd)
    if fn is None:
        p.print_help()
        return 1
    return fn()


if __name__ == "__main__":
    sys.exit(main())
