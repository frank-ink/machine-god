#!/usr/bin/env python3
"""stern_zyklus.py -- session cycle + effect gate + room + governance, PORTED
from the ARCH-import donor stern.py (peer A, 2026-10-01) by AST extraction.

Function bodies verbatim, except: owner display name = generic friend.
Helpers (DB connect, _uid, _jetzt, _kurz, _konfig, USER_ID ...) come from
stern_core.py, so there is ONE DB path and ONE identity.

What this adds to the hook engine (all local, fail-silent, no network, no LLM):
  SessionStart      zyklus_oeffnen (users/sessions/turns/workspace_episodes/
                    active_turns/checkpoints) + raum_beitreten_und_pulsen
  UserPromptSubmit  raum_puls_erneuern, room messages, governance signal
  PreToolUse        zulassen  (effect gate = BOOKKEEPING, never blocks)
  PostToolUse       merken    (event trail, effects verify, causal_episodes,
                    leases) + _ich_tue (taetigkeit trail)
  Stop              zyklus_schliessen, architekt_governance_zug
  SessionEnd        zyklus_schliessen, raum_verlassen
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

import stern_core as _core_mod

# Bring every helper/constant of stern_core into this namespace (one DB, one
# identity). Names defined in this file below override on purpose.
for _n, _v in vars(_core_mod).items():
    if not _n.startswith("__") and _n not in globals():
        globals()[_n] = _v


# ── Geheimnis-Redaktion (Sicherheits-Nachtrag zu PHASE 18, 2026-08-26) ──────
# Realer, demonstrierter Leak: EffectGate/Ereignisspur (zulassen()/merken(),
# unten) schreiben tool_input/argv/target (u.a. Bash-`command`, Write/Edit-
# `content`) UNGEFILTERT in effects/durable_memory. Jedes Geheimnis, das je
# ueber einen Bash-Argumenttext oder einen Datei-Inhalt laeuft, landete
# dauerhaft im Klartext in unified.db -- unabhaengig vom Tresor (PHASE 18),
# dessen eigene gpg-Aufrufe die Passphrase NACHWEISLICH per `--passphrase-fd`
# (eigener Pipe, kein argv, siehe _gpg_lauf()) uebergeben und daher selbst
# NICHT betroffen sind. Primaere Abwehr laut Tresor-Onboarding: Mensch tippt
# Geheimnisse im eigenen Terminal, nie per modellgesteuerten Bash-Aufruf.
# Diese Funktion ist die SEKUNDAERE, defense-in-depth Abwehr: geheimnisartige
# Teilstrings werden VOR dem Schreiben getilgt, unabhaengig davon, wie das
# Geheimnis in den Aufruf gelangt ist. Nur die Werte werden ersetzt (Marker
# "[REDACTED]"), der Rest der Zeile bleibt lesbar -- kein Blackout des
# gesamten Log-Eintrags. Reihenfolge wichtig: spezifische Muster (bekannte
# Praefixe, benannte Flags/Env-Zuweisungen) zuerst, generischer Hochentropie-
# Faenger zuletzt (er wuerde sonst z.B. den Marker selbst nicht treffen, aber
# koennte bereits redigierte Reste anders verzerren).
_GEHEIM_PRAEFIX_MUSTER = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{10,}|gsk_[A-Za-z0-9_\-]{10,}|gh[pousr]_[A-Za-z0-9_\-]{10,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})\b"
)


_GEHEIM_BEARER_MUSTER = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{10,}")


# Benannte Flags (--password, --passphrase, --token, --api-key, --secret, ...):
# Flag-Name bleibt sichtbar, nur der Wert dahinter wird getilgt.
_GEHEIM_FLAG_MUSTER = re.compile(
    r"(?i)((?:--)?(?:passphrase|password|pass|api[-_]?key|apikey|token|secret)\s*[=: ]\s*)(\S+)"
)


# Env-Zuweisungsstil (GROSSSCHREIBUNG bewusst Pflicht -- reduziert Fehltreffer
# auf normalen Fliesstext): PASSWORD=..., API_KEY=..., TOKEN=..., SECRET=...
_GEHEIM_ENV_MUSTER = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSPHRASE)[A-Z0-9_]*=)(\S+)"
)


# mysql-artiges "-p <wert>" -- NUR wenn Wert gemischt Buchstabe+Ziffer UND
# >=6 Zeichen ist, sonst zu viele Fehltreffer auf -p als Port/Parallelitaet.
_GEHEIM_MYSQLP_MUSTER = re.compile(r"(-p\s+)((?=\S*[0-9])(?=\S*[A-Za-z])\S{6,})")


# Generischer Hochentropie-Block: >=20 Zeichen [A-Za-z0-9_-], Buchstabe UND
# Ziffer gemischt (verwirft reine Wortfolgen und reine Zifferfolgen) --
# faengt Base64/Hex-Blobs und rohe Passwoerter ohne bekanntes Praefix, z.B.
# in `printf '...' | ...`-Pipes.
_GEHEIM_BLOB_MUSTER = re.compile(
    r"\b(?=[A-Za-z0-9_\-]{20,}\b)(?=[A-Za-z0-9_\-]*[0-9])(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{20,}\b"
)


def _gm_redact_obj(o):
    """Schreib-Schwaerzung (geheimnis_muster.py); fail-closed: ohne Modul -> Platzhalter."""
    try:
        import geheimnis_muster as _gm
        return _gm.redact_obj(o)
    except Exception:
        return "[REDACTED:modul-fehlt]"


def _geheimnis_redigieren(text: str) -> str:
    """Tilgt geheimnisartige Teilstrings aus `text`, ersetzt sie durch
    "[REDACTED]". Nicht-Strings/leere Werte werden unveraendert zurueckgegeben.
    Reihenfolge: bekannte Praefixe -> Bearer -> benannte Flags -> Env-Stil ->
    mysql-`-p` -> generischer Hochentropie-Faenger."""
    if not isinstance(text, str) or not text:
        return text
    s = text
    s = _GEHEIM_PRAEFIX_MUSTER.sub("[REDACTED]", s)
    s = _GEHEIM_BEARER_MUSTER.sub("Bearer [REDACTED]", s)
    s = _GEHEIM_FLAG_MUSTER.sub(r"\1[REDACTED]", s)
    s = _GEHEIM_ENV_MUSTER.sub(r"\1[REDACTED]", s)
    s = _GEHEIM_MYSQLP_MUSTER.sub(r"\1[REDACTED]", s)
    s = _GEHEIM_BLOB_MUSTER.sub("[REDACTED]", s)
    return s


def _kurz_redigiert(wert, n: int = 220) -> str:
    """Wie _kurz(), aber tilgt Geheimnisse VOR dem Kappen (ein Geheimnis, das
    genau an der Kappungsgrenze liegt, darf nicht als unerkannter Rest
    durchrutschen). Nur an den Stellen verwenden, die tool_input/argv/target/
    tool_response in effects/durable_memory schreiben -- _kurz() selbst bleibt
    unveraendert fuer alle anderen (nicht geheimnisverdaechtigen) Aufrufer."""
    if isinstance(wert, (dict, list)):
        wert = json.dumps(wert, ensure_ascii=False, separators=(",", ":"))
    s = str(wert if wert is not None else "").replace("\n", " ").strip()
    s = _geheimnis_redigieren(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _argv_normalisiert_redigiert(tool_input) -> str:
    """_argv_normalisiert() + Geheimnis-Tilgung VOR dem Kappen auf 500 Zeichen
    (siehe _kurz_redigiert()-Begruendung)."""
    return _geheimnis_redigieren(_argv_normalisiert(tool_input))[:500]


# ═══════════════════════════════════════════════════════════════════════
# ABSCHNITT: SITZUNGSZYKLUS -- verbatim aus udb/bruecke.py (users/sessions/
# turns/workspace_episodes/active_turns, Injektionsprotokoll checkpoints).
# ═══════════════════════════════════════════════════════════════════════
def _owner_name() -> str:
    try:
        import frank_profile as _fpm
        return _fpm.name()
    except Exception:
        return "friend"


def _sicherstellen_nutzer(c) -> None:
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, display_name, rights) VALUES (?,?,?)",
        (USER_ID, _owner_name(), "eigner"),
    )


def zyklus_oeffnen(session_id: str, model: str) -> Optional[str]:
    """Eroeffnet den Sitzungszyklus. Gibt die episode_id zurueck (oder None).

    PHASE 2 (ZECP17): sessions.generation ist ab hier ECHT -- nicht mehr
    hartkodiert 1. zyklus_oeffnen wird laut cmd_hook() ausschliesslich bei
    SessionStart mit source='startup' aufgerufen (siehe dortige Verzweigung);
    das ON CONFLICT hier zaehlt daher genau bei jedem 'startup'-Ereignis
    hoch, wie im Konzeptdokument PHASE 2 gefordert ("hochgezaehlt bei jedem
    SessionStart mit source='startup'"). Eine brandneue session_id bleibt
    bei Generation 1 (INSERT-Zweig greift, kein Konflikt); ein wiederholter
    'startup' fuer dieselbe session_id (z.B. Terminal neu verbunden, gleiche
    ID wiederaufgenommen) zaehlt hoch -- exakt der Fall, den die neue
    PreToolUse-Zulassungspruefung unten als "veraltete Generation" erkennen
    soll, wenn eine Wirkung noch aus der alten Zaehlung angestossen wird."""
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            _sicherstellen_nutzer(c)
            jetzt = _jetzt()
            c.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, updated_at, "
                "generation, terminal_name) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "generation = sessions.generation + 1, updated_at = excluded.updated_at",
                (session_id, USER_ID, jetzt, jetzt, 1, f"claude-code:{session_id}"),
            )
            generation = (
                c.execute("SELECT generation FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                or (1,)
            )[0]

            turn_id = _uid("t-open")
            ordinal = _naechste_ordinal(c, session_id)
            c.execute(
                "INSERT INTO turns (turn_id, session_id, user_id, ordinal, ts, role, "
                "content, fidelity, compression_generation, resource_refs, causal_refs, "
                "provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn_id, session_id, USER_ID, ordinal, jetzt, "system",
                    "[Sitzungsmarke: Zyklus eroeffnet ueber stern.py -- kein echtes "
                    "Transkript erfasst, nur Randmarke]",
                    "marker", 0, "[]", "[]",
                    json.dumps({"quelle": "stern.py", "model": model}, ensure_ascii=False),
                ),
            )
            episode_id = _uid("ep")
            c.execute(
                "INSERT INTO workspace_episodes (episode_id, session_id, ts, "
                "observation_turn_id, salience, alternatives, selected, state) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (episode_id, session_id, jetzt, turn_id, 1.0, "[]", None, "offen"),
            )
            causal_id = _uid("c")
            c.execute(
                "INSERT OR REPLACE INTO active_turns (session_id, user_id, turn_id, "
                "episode_id, causal_id, generation, resource_refs, effect_id, outcome, "
                "workspace_selected, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, USER_ID, turn_id, episode_id, causal_id, generation, "[]", None, None, 0, jetzt),
            )
            c.commit()
            return episode_id
    except Exception as e:
        _log(f"zyklus_oeffnen fehler sid={session_id}: {e}")
        return None


def zyklus_schliessen(session_id: str) -> None:
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            row = c.execute(
                "SELECT episode_id FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            jetzt = _jetzt()
            ordinal = _naechste_ordinal(c, session_id)
            turn_id = _uid("t-close")
            c.execute(
                "INSERT INTO turns (turn_id, session_id, user_id, ordinal, ts, role, "
                "content, fidelity, compression_generation, resource_refs, causal_refs, "
                "provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn_id, session_id, USER_ID, ordinal, jetzt, "system",
                    "[Sitzungsmarke: Zyklus geschlossen ueber stern.py]",
                    "marker", 0, "[]", "[]",
                    json.dumps({"quelle": "stern.py"}, ensure_ascii=False),
                ),
            )
            if row and row[0]:
                c.execute(
                    "UPDATE workspace_episodes SET state='geschlossen' WHERE episode_id=?",
                    (row[0],),
                )
            c.execute(
                "UPDATE active_turns SET outcome='geschlossen' WHERE session_id=?",
                (session_id,),
            )
            c.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (jetzt, session_id))
            c.commit()
    except Exception as e:
        _log(f"zyklus_schliessen fehler sid={session_id}: {e}")
    _checkpoint("Stop/SessionEnd", session_id, "-", "schliessen", "")


def _checkpoint(event: str, session_id: str, model: str, phase: str, injiziert_text: str) -> str:
    digest_quelle = injiziert_text if injiziert_text else f"{phase}:{event}:{session_id}"
    state_hash = hashlib.sha256(digest_quelle.encode("utf-8")).hexdigest()[:16]
    note = json.dumps(
        {
            "phase": phase, "event": event, "session_id": session_id, "model": model,
            "kapsel_laenge": len(injiziert_text) if injiziert_text else 0,
            "kapsel_anfang": _kurz(injiziert_text, 160) if injiziert_text else None,
        },
        ensure_ascii=False, separators=(",", ":"),
    )
    cp_id = _uid(f"udb-{phase}")
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            c.execute(
                "INSERT OR REPLACE INTO checkpoints (checkpoint_id, ts, state_hash, note) "
                "VALUES (?, ?, ?, ?)",
                (cp_id, _jetzt(), state_hash, note),
            )
            c.commit()
    except Exception as e:
        _log(f"checkpoint fehler phase={phase} sid={session_id}: {e}")
    return state_hash


# ═══════════════════════════════════════════════════════════════════════
# ABSCHNITT: EFFECTGATE -- ZECP17, PHASE 2. Zwei Seiten einer Wirkung:
# zulassen() (PreToolUse, Zulassung VOR der Ausfuehrung) und die Verifikation
# in merken() (PostToolUse, danach). Vorher gab es nur die zweite Haelfte --
# ein Protokoll im Nachhinein, kein Gate (siehe Docstring dieser Datei/
# Konzeptdokument PHASE 2: "der heutige EffectGate ist gar keiner").
#
# NICHT VERHANDELBAR: zulassen() blockiert NIE ein Werkzeug. Es gibt in
# dieser gesamten Datei keinen Codepfad, der aus einem PreToolUse-Hook ein
# "deny"/"block" an Claude Code zurueckgibt -- cmd_hook() druckt fuer
# PreToolUse ueberhaupt nichts nach stdout (siehe dort). Bei Zweifel,
# Zeitueberschreitung oder Fehler wird status='UNGEPRUEFT' geschrieben (oder,
# wenn selbst das nicht mehr rechtzeitig gelingt, gar nichts) -- das
# Werkzeug laeuft in jedem Fall. Der bestehende, aeltere BLOCKIERENDE
# Waechter (~/aicore/opt/aicore/tools/schranke/wache-koenig.py, globales
# settings.json) bleibt unberuehrt; dieser Abschnitt ist zusaetzliche, rein
# buchhalterische Logik in der STAR-scoped settings.json. Verwandt, aber
# eine andere Kategorie als die LEASES weiter unten (P5d): Leases sind
# Kollisions-MELDUNG zwischen Sitzungen, EffectGate ist Buchfuehrung UEBER
# eine einzelne Wirkung (Zulassung -> Verifikation), beide blockieren nie.
# ═══════════════════════════════════════════════════════════════════════
ZUSTANDSAENDERND = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}


def _effect_ziel(tool_input, tool_name: str) -> str:
    if not isinstance(tool_input, dict):
        return "?"
    return (
        tool_input.get("file_path") or tool_input.get("notebook_path")
        or tool_input.get("command") or "?"
    )


def _ist_fehlerhaft(tool_response) -> bool:
    if isinstance(tool_response, dict):
        return bool(tool_response.get("is_error") or tool_response.get("error"))
    if isinstance(tool_response, str):
        return tool_response.strip().lower().startswith(("error", "fehler"))
    return False


def _argv_normalisiert(tool_input) -> str:
    """Kanonische Form fuer den Idempotenz-Schluessel -- sortierte Schluessel,
    kein Leerraum, damit dieselbe Eingabe immer denselben Hash ergibt,
    unabhaengig von Schluesselreihenfolge im eingehenden JSON."""
    try:
        return json.dumps(tool_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return _kurz(tool_input, 500)


def _idempotenz_schluessel(tool_name: str, target: str, tool_input) -> str:
    roh = f"{tool_name}|{target}|{_argv_normalisiert(tool_input)}"
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


def _sicherstellen_faehigkeit_tabelle(c) -> None:
    """star_faehigkeit ist zunaechst eine REGISTRIERUNG, kein Verbot (PHASE 2,
    Pruefung 1): unbekannte Werkzeuge werden bei der ersten Zulassungspruefung
    automatisch mit zugelassen=1 eingetragen. Ein Verbot entsteht erst, wenn
    jemand von Hand eine Zeile auf 0 setzt -- diese Phase selbst setzt nie 0
    (kein Kredit-/Lernlogik, das ist P3)."""
    c.execute(
        "CREATE TABLE IF NOT EXISTS star_faehigkeit("
        "tool_name TEXT PRIMARY KEY, zugelassen INTEGER NOT NULL DEFAULT 1, "
        "grund TEXT, geaendert REAL NOT NULL)"
    )


def zulassen(payload: dict) -> None:
    """PreToolUse -- Zulassung. Budget 0.4s (star_konfig limit.PreToolUse),
    durchgesetzt von cmd_hook()'s SIGALRM, nicht hier selbst. Prueft in
    fester Reihenfolge: 1 Capability, 2 Generation, 3 Vorbedingung,
    4 Idempotenz -- und schreibt GENAU EINE effects-Zeile mit dem Befund.
    Die effect_id wird in active_turns.effect_id abgelegt (die bereits
    bestehende sitzungsgebundene Ablage, ein Feld je Sitzung) -- merken()
    (PostToolUse) liest sie von dort und aktualisiert dieselbe Zeile, statt
    eine zweite anzulegen."""
    session_id = str(payload.get("session_id") or "unknown")
    tool_name = payload.get("tool_name") or "?"
    tool_input = payload.get("tool_input") or {}
    if tool_name not in ZUSTANDSAENDERND:
        return  # nur zustandsaendernde Werkzeuge bekommen eine EffectGate-Zeile

    target = _effect_ziel(tool_input, tool_name)
    idem_schluessel = _idempotenz_schluessel(tool_name, target, tool_input)

    try:
        with contextlib.closing(schreib_verbindung()) as c:
            _sicherstellen_faehigkeit_tabelle(c)

            # 1) Capability -- Voreinstellung: alles zugelassen (Registrierung, kein Verbot)
            row = c.execute(
                "SELECT zugelassen FROM star_faehigkeit WHERE tool_name=?", (tool_name,)
            ).fetchone()
            if row is None:
                c.execute(
                    "INSERT OR IGNORE INTO star_faehigkeit (tool_name, zugelassen, grund, geaendert) "
                    "VALUES (?,1,?,?)",
                    (tool_name, "auto-registriert bei erster Zulassungspruefung", _jetzt()),
                )
                capability_ok = True
            else:
                capability_ok = bool(row[0])

            # 2) Generation -- Sitzungsgeneration (sessions.generation) vs. die
            # Generation, unter der die aktuelle Episode (active_turns) eroeffnet
            # wurde. Weichen sie ab, ist die Episode aus einer inzwischen per
            # neuem SessionStart(source=startup) ueberholten Zaehlung.
            srow = c.execute(
                "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            aktuelle_generation = srow[0] if srow else 1
            arow = c.execute(
                "SELECT episode_id, generation FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            episode_id = arow[0] if arow else None
            erwartete_generation = arow[1] if arow else aktuelle_generation
            generation_ok = (erwartete_generation == aktuelle_generation)

            # 3) Vorbedingung -- bei Edit/MultiEdit/NotebookEdit muss die Zieldatei
            # existieren, bei Write muss zumindest der Elternordner existieren.
            vorbedingung_ok, vorbedingung_grund = True, None
            if tool_name in ("Edit", "MultiEdit"):
                fp = tool_input.get("file_path") if isinstance(tool_input, dict) else None
                if not fp or not Path(fp).is_file():
                    vorbedingung_ok = False
                    vorbedingung_grund = f"Zieldatei existiert nicht: {fp}"
            elif tool_name == "NotebookEdit":
                np_ = tool_input.get("notebook_path") if isinstance(tool_input, dict) else None
                if not np_ or not Path(np_).is_file():
                    vorbedingung_ok = False
                    vorbedingung_grund = f"Notebook existiert nicht: {np_}"
            elif tool_name == "Write":
                fp = tool_input.get("file_path") if isinstance(tool_input, dict) else None
                if fp and not Path(fp).parent.is_dir():
                    vorbedingung_ok = False
                    vorbedingung_grund = f"Elternordner fehlt: {Path(fp).parent}"
            # Bash hat keine Datei-Vorbedingung -- bleibt ok.

            status, grund = "ZUGELASSEN", None
            if not capability_ok:
                status, grund = "ABGELEHNT", "capability: Werkzeug in star_faehigkeit gesperrt"
            elif not generation_ok:
                status, grund = (
                    "ABGELEHNT",
                    f"generation veraltet: Episode erwartet {erwartete_generation}, "
                    f"Sitzung aktuell {aktuelle_generation}",
                )
            elif not vorbedingung_ok:
                status, grund = "ABGELEHNT", f"vorbedingung: {vorbedingung_grund}"
            else:
                # 4) Idempotenz -- identischer, bereits VERIFIED verbuchter Effekt
                # in DERSELBEN Sitzung wird markiert, nicht blockiert.
                # Suchmuster bewusst NUR auf den gequoteten Hash-Wert, nicht auf
                # den umgebenden Schluessel/Doppelpunkt/Leerraum -- json.dumps()
                # ohne separators= setzt ein Leerzeichen nach dem Doppelpunkt
                # ("idempotenz_schluessel": "..."), ein Muster mit fest
                # eingebautem "):"  waere formatabhaengig und still falsch
                # (beim ersten Bau dieser Phase genau so gefunden: kein
                # Duplikat wurde je erkannt, weil das Muster nie traf). Der
                # Hash selbst ist 64 Hex-Zeichen -- als Teilstring praktisch
                # kollisionsfrei, ein Wrapper aus Anfuehrungszeichen genuegt.
                dup = c.execute(
                    "SELECT e.effect_id FROM effects e "
                    "JOIN workspace_episodes we ON we.episode_id = e.episode_id "
                    "WHERE we.session_id=? AND e.status='VERIFIED' "
                    "AND e.outcome LIKE ? LIMIT 1",
                    (session_id, f'%"{idem_schluessel}"%'),
                ).fetchone()
                if dup:
                    status = "WIEDERHOLUNG"
                    grund = f"identischer verifizierter Effekt bereits vorhanden: {dup[0]}"

            outcome = {
                "phase": "zulassung",
                "idempotenz_schluessel": idem_schluessel,
                "pruefungen": {
                    "capability": capability_ok, "generation": generation_ok,
                    "vorbedingung": vorbedingung_ok,
                },
            }
            if grund:
                outcome["grund"] = grund

            effect_id = _uid("eff")
            c.execute(
                "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                "target, argv, requested_generation, status, outcome, ts, verified_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    effect_id, episode_id, USER_ID, tool_name, _kurz_redigiert(target, 300),
                    _argv_normalisiert_redigiert(tool_input), aktuelle_generation, status,
                    json.dumps(outcome, ensure_ascii=False), _jetzt(), None,
                ),
            )
            if arow is not None:
                c.execute(
                    "UPDATE active_turns SET effect_id=? WHERE session_id=?",
                    (effect_id, session_id),
                )
            c.commit()
    except Exception as e:
        # Fail-silent gemaess harter Grenze 4 -- das Werkzeug laeuft so oder so
        # (cmd_hook() gibt fuer PreToolUse ohnehin keine Entscheidung zurueck).
        # Bestmoeglicher Nachtrag: eine UNGEPRUEFT-Zeile, wenn selbst das noch
        # in der Restzeit geht; misslingt auch das, bleibt die Sitzung einfach
        # ohne Zulassungszeile fuer diesen Aufruf -- merken() faengt das unten
        # als Fallback ab.
        _log(f"zulassen fehler sid={session_id} tool={tool_name}: {e}")
        try:
            with contextlib.closing(schreib_verbindung()) as c2:
                c2.execute(
                    "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                    "target, argv, requested_generation, status, outcome, ts, verified_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _uid("eff"), None, USER_ID, tool_name, _kurz_redigiert(target, 300),
                        _argv_normalisiert_redigiert(tool_input), 1, "UNGEPRUEFT",
                        json.dumps({"grund": f"pruefung fehlgeschlagen: {e}"}, ensure_ascii=False),
                        _jetzt(), None,
                    ),
                )
                c2.commit()
        except Exception:
            pass  # selbst der Nachtrag darf nie eine Sitzung stoeren


def _wirkung_pruefen(tool_name: str, tool_input, tool_response) -> tuple:
    """PostToolUse -- das tatsaechliche Ergebnis, gehasht (Zeros Muster:
    {'ok':bool,'bytes':n,'sha256':...}) statt abgeschnittener Rohtext.
    Gibt (ok, outcome_objekt) zurueck."""
    fehlerhaft = _ist_fehlerhaft(tool_response)
    if tool_name == "Bash":
        exit_code = None
        text = ""
        if isinstance(tool_response, dict):
            if "exit_code" in tool_response:
                exit_code = tool_response.get("exit_code")
            text = str(tool_response.get("stdout") or "") + str(tool_response.get("stderr") or "")
        else:
            text = str(tool_response or "")
        roh = text.encode("utf-8", "replace")
        ok = (exit_code == 0) if exit_code is not None else (not fehlerhaft)
        return ok, {"ok": ok, "bytes": len(roh), "sha256": hashlib.sha256(roh).hexdigest(),
                     "exit_code": exit_code}

    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        pfad = None
        if isinstance(tool_input, dict):
            pfad = tool_input.get("file_path") or tool_input.get("notebook_path")
        if pfad and Path(pfad).is_file():
            try:
                roh = Path(pfad).read_bytes()
                ok = not fehlerhaft
                return ok, {"ok": ok, "bytes": len(roh), "sha256": hashlib.sha256(roh).hexdigest()}
            except Exception as e:
                return False, {"ok": False, "bytes": 0, "sha256": None, "fehler": str(e)}
        return (not fehlerhaft), {
            "ok": not fehlerhaft, "bytes": 0, "sha256": None,
            "hinweis": "Zieldatei nach Lauf nicht gefunden",
        }

    text = _kurz(tool_response, 2000).encode("utf-8", "replace")
    ok = not fehlerhaft
    return ok, {"ok": ok, "bytes": len(text), "sha256": hashlib.sha256(text).hexdigest()}


_TUE_DDL = """CREATE TABLE IF NOT EXISTS f2_ich_tue (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    sitzung TEXT,
    was     TEXT NOT NULL,
    art     TEXT,
    schema  TEXT NOT NULL)"""


def _ich_tue(was: str, art: str = "auftrag", sitzung: str = "") -> None:
    """Eine Zeile ueber die eigene Taetigkeit. Wirft nie."""
    was = " ".join((was or "").split())[:400]
    if not was:
        return
    try:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=5.0)) as c:
            c.execute(_TUE_DDL)
            c.execute("INSERT INTO f2_ich_tue (ts, sitzung, was, art, schema) "
                      "VALUES (?,?,?,?,?)",
                      (datetime.now(timezone.utc).strftime(
                          "%Y-%m-%dT%H:%M:%SZ"), sitzung, was, art,
                       "F2WP1207_ICHTUE/v1"))
            # Kurz halten: was vor einer Stunde war, ist keine Taetigkeit mehr.
            c.execute("DELETE FROM f2_ich_tue WHERE id NOT IN "
                      "(SELECT id FROM f2_ich_tue ORDER BY id DESC LIMIT 40)")
            c.commit()
    except Exception:
        pass


def merken(payload: dict) -> None:
    """PostToolUse -- Ereignisspur (unveraendert) + Wirkungsverifikation
    (PHASE 2, ZECP17). Aktualisiert dieselbe effects-Zeile, die zulassen()
    (PreToolUse) angelegt hat (gefunden ueber active_turns.effect_id); nur
    wenn dort status='ZUGELASSEN' stand, wird auf VERIFIED/FEHLGESCHLAGEN
    umgeschaltet -- ABGELEHNT/WIEDERHOLUNG/UNGEPRUEFT bleiben als Befund
    stehen (das IST die Information), bekommen aber trotzdem verified_at
    und einen Nachtrag mit dem tatsaechlichen Ergebnis. Fehlt eine
    PreToolUse-Zeile ganz (Timeout/Fehler/Fallback), legt merken() selbst
    eine an -- das Journal darf nie leer bleiben, nur weil die Zulassung es
    nicht rechtzeitig geschafft hat. Zusaetzlich: je verifiziertem Effekt
    eine causal_episodes-Zeile (hier zum ersten Mal ueberhaupt beschrieben,
    Kredit bleibt 0 -- das ist P3)."""
    session_id = str(payload.get("session_id") or "unknown")
    tool_name = payload.get("tool_name") or payload.get("hook_event_name") or "?"
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")

    try:
        with contextlib.closing(schreib_verbindung()) as c:
            mem_id = _uid(f"ereignis-{session_id}")
            wert = {"input": _kurz_redigiert(tool_input, 220), "response": _kurz_redigiert(tool_response, 220)}
            c.execute(
                "INSERT INTO durable_memory (memory_id, kind, subject, value, "
                "source_turn_id, user_id, ts, provenance) VALUES (?,?,?,?,?,?,?,?)",
                (
                    mem_id, "ereignis", f"tool:{tool_name}",
                    json.dumps(_gm_redact_obj(wert), ensure_ascii=False),
                    None, USER_ID, _jetzt(), f"hook:PostToolUse:session={session_id}",
                ),
            )

            # PHASE 6/ZECP10, P6a Punkt 2 -- gw_herkunft. Provenienzzeile je
            # NEU geschriebener durable_memory-Zeile. `merken()` ist [LIVE
            # geprueft, 2026-08-26] der EINZIGE Schreibpfad in diese Tabelle
            # in der gesamten Datei -- jede Zeile hier entsteht also
            # zwingend aus tool_input/tool_response, nie aus des Nutzers
            # eigener Eingabe oder dem Korpus. fremdtext=1 ist deshalb hier
            # keine geratene Heuristik, sondern eine Tatsache ueber DIESEN
            # einen Schreibpfad -- ehrlich gemeldeter Befund, nicht "immer 1
            # weil bequem": sobald ein zweiter Schreibpfad (z.B. explizites
            # Merken von des Nutzers eigenem Text) entsteht, muss der dortige
            # Aufrufer sein eigenes fremdtext setzen, nicht diese Konstante.
            gw_turn_row = c.execute(
                "SELECT turn_id FROM active_turns WHERE session_id=?", (session_id,)
            ).fetchone()
            c.execute(
                "INSERT INTO gw_herkunft(memory_id, turn_id, session_id, ts, "
                "fremdtext, werkzeuge) VALUES (?,?,?,?,?,?)",
                (
                    mem_id, gw_turn_row[0] if gw_turn_row else None, session_id,
                    _jetzt(), 1, json.dumps([tool_name], ensure_ascii=False),
                ),
            )

            if tool_name in ZUSTANDSAENDERND:
                ok, wirkung = _wirkung_pruefen(tool_name, tool_input, tool_response)

                arow = c.execute(
                    "SELECT episode_id, effect_id, turn_id FROM active_turns WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                episode_id = arow[0] if arow else None
                effect_id = arow[1] if arow else None
                turn_id = arow[2] if arow else None

                zeile = c.execute(
                    "SELECT status, outcome FROM effects WHERE effect_id=?", (effect_id,)
                ).fetchone() if effect_id else None

                if zeile:
                    alter_status, alter_outcome_roh = zeile
                    try:
                        alter_outcome = json.loads(alter_outcome_roh) if alter_outcome_roh else {}
                    except Exception:
                        alter_outcome = {"unlesbar": alter_outcome_roh}
                    neuer_status = "VERIFIED" if ok else "FEHLGESCHLAGEN"
                    if alter_status not in ("ZUGELASSEN",):
                        neuer_status = alter_status  # ABGELEHNT/WIEDERHOLUNG/UNGEPRUEFT bleiben stehen
                    alter_outcome["nachtrag"] = wirkung
                    c.execute(
                        "UPDATE effects SET status=?, outcome=?, verified_at=? WHERE effect_id=?",
                        (neuer_status, json.dumps(alter_outcome, ensure_ascii=False), _jetzt(), effect_id),
                    )
                else:
                    # Fallback: keine PreToolUse-Zeile gefunden (Timeout, Fehler,
                    # oder Aufruf ausserhalb eines echten Sitzungszyklus).
                    srow = c.execute(
                        "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
                    ).fetchone()
                    generation = srow[0] if srow else 1
                    effect_id = _uid("eff")
                    target = _effect_ziel(tool_input, tool_name)
                    c.execute(
                        "INSERT INTO effects (effect_id, episode_id, user_id, capability, "
                        "target, argv, requested_generation, status, outcome, ts, verified_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            effect_id, episode_id, USER_ID, tool_name, _kurz_redigiert(target, 300),
                            _argv_normalisiert_redigiert(tool_input), generation,
                            "VERIFIED" if ok else "FEHLGESCHLAGEN",
                            json.dumps(
                                {"nachtrag": wirkung,
                                 "hinweis": "keine PreToolUse-Zeile gefunden (Timeout/Fehler/Fallback)"},
                                ensure_ascii=False,
                            ),
                            _jetzt(), _jetzt(),
                        ),
                    )

                c.execute(
                    "INSERT INTO causal_episodes (causal_id, episode_id, effect_id, "
                    "observation_turn_id, outcome_hash, credit, reentered, ts) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (_uid("c"), episode_id, effect_id, turn_id, wirkung.get("sha256"), 0, 0, _jetzt()),
                )
            c.commit()
    except Exception as e:
        _log(f"merken fehler sid={session_id} tool={tool_name}: {e}")
        return

    # P5d: Pacht auf die angefasste Datei erneuern -- NUR fuer die drei
    # echten Dateiwerkzeuge (Bash-Ziele sind keine verlaesslichen Dateipfade,
    # siehe target-Ableitung oben, die bei Bash den Befehlstext nimmt).
    # Fail-silent, ausserhalb der schreib_verbindung()-Transaktion oben, weil
    # lease_halten() seine eigene kurze Verbindung oeffnet -- eine
    # fehlschlagende Pacht darf die Ereignisspur nicht mit hinunterreissen.
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit") and isinstance(tool_input, dict):
        pfad = tool_input.get("file_path") or tool_input.get("notebook_path")
        if pfad:
            try:
                with contextlib.closing(verbindung()) as c3:
                    genrow = c3.execute(
                        "SELECT generation FROM sessions WHERE session_id=?", (session_id,)
                    ).fetchone()
                generation = genrow[0] if genrow else 1
            except Exception:
                generation = 1
            lease_halten(pfad, session_id, generation)


def _konfig_dyn_get(schluessel: str, rueckfall: str = "") -> str:
    try:
        with contextlib.closing(verbindung()) as c:
            row = c.execute("SELECT wert FROM star_konfig WHERE schluessel=?", (schluessel,)).fetchone()
            return row[0] if row else rueckfall
    except Exception as e:
        _log(f"_konfig_dyn_get fehler schluessel={schluessel}: {e}")
        return rueckfall


def _konfig_dyn_set(schluessel: str, wert: str, quelle: str = "phase13") -> None:
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            c.execute(
                "INSERT INTO star_konfig (schluessel, wert, typ, quelle, geaendert) VALUES (?,?,?,?,?) "
                "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, quelle=excluded.quelle, "
                "geaendert=excluded.geaendert",
                (schluessel, wert, "str", quelle, _jetzt()),
            )
            c.commit()
    except Exception as e:
        _log(f"_konfig_dyn_set fehler schluessel={schluessel}: {e}")


_SPRACHE_DE_CACHE: Optional[bool] = None


def _sprache_ist_deutsch() -> bool:
    """PHASE 25-Override-Pfad (Nutzer, explizite Sprachwahl je Instanz,
    2026-08-26): liest sprache_default direkt aus star_konfig -- KEIN Import
    von einrichtung.py (kein Kreisimport, gleiche Tabelle/Spalte, dieselbe
    grobe Erkennung wie dort _sprachkuerzel()). Instanz-lokal per Definition:
    jede Maschine hat ihre eigene unified.db/eigenes sprache_default, ai-core-
    node bleibt also unberuehrt, solange dort niemand explizit 'Deutsch'
    setzt. Fail-closed bei DB-Fehlern -> False (Englisch bleibt Vorgabe)."""
    global _SPRACHE_DE_CACHE
    if _SPRACHE_DE_CACHE is None:
        wert = ""
        try:
            with contextlib.closing(verbindung()) as c:
                row = c.execute(
                    "SELECT wert FROM star_konfig WHERE schluessel='sprache_default'"
                ).fetchone()
                if row and row[0]:
                    wert = str(row[0])
        except Exception as e:
            _log(f"sprache_default lesen fehler (bleibe bei Englisch): {e}")
        s = wert.strip().lower()
        _SPRACHE_DE_CACHE = s in (
            "de", "german", "deutsch", "de-de", "de-at", "de-ch",
            "österreichisch", "oesterreichisch",
        )
    return _SPRACHE_DE_CACHE


def _sprachvariante_lesen(p: Path, rueckfall: str) -> str:
    """Gemeinsamer Loader fuer die vier PHASE-25-Override-Dateien (persona/
    sebukku/architekt_governance/architekt_tiefensitzung): wenn sprache_
    default=Deutsch UND eine `<stamm>.de.<endung>`-Datei danaben existiert,
    die nehmen -- sonst unveraendert die bisherige (englische) Datei. Kein
    zweiter gepflegter Text-Speicher projektweit (PHASE 25 Auflage): die
    .de-Datei existiert nur, wo sie von Hand/per gen+Kuration angelegt wurde
    (aktuell: another instance), fehlt sie, faellt das hier lautlos auf
    Englisch zurueck -- kein Fehlerzustand."""
    if _sprache_ist_deutsch():
        de_pfad = p.with_name(p.stem + ".de" + p.suffix)
        if de_pfad.exists():
            try:
                return de_pfad.read_text(encoding="utf-8")
            except Exception as e:
                _log(f"{de_pfad.name} fehlt/unlesbar, falle auf Englisch zurueck: {e}")
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        _log(f"{p.name} fehlt/unlesbar: {e}")
        return rueckfall


def sebukku_marke_pruefen(session_id: str) -> Optional[dict]:
    """None = keine Marke (Sitzung unbeeintraechtigt). Sonst {grund, ts,
    effect_id}. SITZUNGSGEBUNDEN -- der Schluessel ist session_id, niemals
    global (Konzeptdokument §5.5.2, fett markiert)."""
    try:
        with contextlib.closing(verbindung()) as c:
            row = c.execute(
                "SELECT grund, ts, effect_id FROM star_sebukku WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return {"grund": row[0], "ts": row[1], "effect_id": row[2]}
    except Exception:
        return None  # Tabelle existiert evtl. noch nicht -- dann sicher keine Marke


_RAUM_FOCUS_PLATZHALTER = "unknown at join time"


_RAUM_STALE_MINUTEN = 45  # wie active_workers(stale_minutes=45) im alten research_room.py


_RAUM_NAMEN_DATEI = STERN_DIR / "daten" / "raum_namen.json"


def _raum_spitzname_ziehen(platz: int) -> str:
    """PHASE 37 -- zufaellige dystopisch-duestere Kurzbezeichnung aus
    daten/raum_namen.json fuer die .rname-Anzeige in /stat (statt roher
    'Sitzung N'). Frisch geladen (keine Modul-Caches, die Datei ist winzig
    und wird nur EINMAL je echtem Beitritt gelesen). Fail-silent: fehlt/ist
    kaputt die Datei, faellt es auf 'Sitzung N' zurueck -- nie ein Crash."""
    try:
        pool = json.loads(_RAUM_NAMEN_DATEI.read_text(encoding="utf-8"))
        if isinstance(pool, list) and pool:
            return str(random.choice(pool))
    except Exception as e:
        _log(f"raum_spitzname laden fehler: {e}")
    return f"Sitzung {platz}"


def _zero_raum_spitzname_migrieren(c) -> None:
    """Selbstheilende Schema-Migration (real gefunden, PHASE 42b/c-Deploy
    auf machine-b, 2026-08-26): `daten/schema_leer.sql` (Vorlage fuer
    Frischinstallationen) hatte nie eine `spitzname`-Spalte in `zero_raum`
    -- auf a dev box existiert sie trotzdem (irgendwann per Hand
    nachgezogen, nie in die Vorlage zurueckgespiegelt), auf einer frischer
    aufgesetzten DB (another machine) fehlte sie und liess JEDEN
    Raum-Beitritt mit 'no such column' scheitern. `PRAGMA table_info`
    ist billig und idempotent -- kein Zustand, der zweimal migriert werden
    koennte, kein Schaden bei wiederholtem Aufruf."""
    try:
        spalten = {row[1] for row in c.execute("PRAGMA table_info(zero_raum)")}
        if "spitzname" not in spalten:
            c.execute("ALTER TABLE zero_raum ADD COLUMN spitzname TEXT")
            _log("zero_raum: Spalte 'spitzname' nachtraeglich migriert (fehlte auf dieser DB)")
    except Exception as e:
        _log(f"_zero_raum_spitzname_migrieren fehler (nicht kritisch): {e}")


def raum_beitreten_und_pulsen(session_id: str, model: str) -> str:
    """Beitritt (oder erneuter Puls, falls schon Zeile vorhanden -- eine
    Sitzung, die SessionStart mehrfach ausloest: /clear, /resume, /compact,
    /fork) + Liste der anderen aktiven Sitzungen. Ersetzt
    rooms_hook.py:handle_session_start()."""
    jetzt = _jetzt()
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            _zero_raum_spitzname_migrieren(c)
            vorhanden = c.execute(
                "SELECT platz FROM zero_raum WHERE session_id=?", (session_id,)
            ).fetchone()
            if vorhanden:
                platz = vorhanden[0]
                beitritt_text = "rejoin/pulse"
                # spitzname bleibt sitzungslebenslang stabil -- die DO UPDATE
                # unten laesst die Spalte unangetastet, dieser Wert wird nur
                # im (hier nicht genommenen) INSERT-Zweig gebraucht.
                spitzname = None
            else:
                row = c.execute(
                    "SELECT COUNT(*) FROM zero_raum WHERE mensch=? AND zustand='arbeitet'",
                    (USER_ID,),
                ).fetchone()
                platz = (row[0] if row else 0) + 1
                beitritt_text = "joined"
                spitzname = _raum_spitzname_ziehen(platz)  # EINMAL, nur bei echtem Erstbeitritt
            c.execute(
                "INSERT INTO zero_raum(session_id,mensch,platz,was,womit,zustand,seit,spitzname) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET zustand='arbeitet', seit=excluded.seit, "
                "was=excluded.was",
                (session_id, USER_ID, platz, _RAUM_FOCUS_PLATZHALTER, f"claude-code:{model}",
                 "arbeitet", jetzt, spitzname),
            )
            schwelle = jetzt - _RAUM_STALE_MINUTEN * 60
            # Echte Selbstheilung statt nur Anzeige-Filter (des Nutzers Vorgabe:
            # keine Leichen -- zustand muss Realitaet sein, nicht bloss beim
            # Lesen weggefiltert werden). Eigene Zeile ist safe: gerade mit
            # seit=jetzt geschrieben, also >= schwelle, wird hier nie erwischt.
            c.execute(
                "UPDATE zero_raum SET zustand='frei' WHERE zustand='arbeitet' AND seit < ?",
                (schwelle,),
            )
            c.commit()
            andere = c.execute(
                "SELECT session_id, was, seit FROM zero_raum WHERE zustand='arbeitet' "
                "AND session_id != ? AND seit >= ? ORDER BY seit DESC",
                (session_id, schwelle),
            ).fetchall()
    except Exception as e:
        _log(f"raum_beitreten fehler sid={session_id}: {e}")
        return f"room center: Fehler beim Beitritt ({e})."

    _raum_ruf_schreiben(session_id, "JOIN" if beitritt_text == "joined" else "PULSE",
                        f"session={session_id} platz={platz}")

    zeilen = [f"room center: {beitritt_text} as {session_id}."]
    if andere:
        zeilen.append(f"{len(andere)} other active session(s):")
        for sid, was, seit in andere:
            zeilen.append(f"- {sid} focus={was} last_pulse={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(seit))}")
    else:
        zeilen.append("no other active sessions in room now.")

    # P5d: Kollisionsmeldung, keine Sperre -- alle aktiven Pachten anderer
    # Sitzungen, damit ein frischer SessionStart sofort sieht, woran gerade
    # gearbeitet wird, ohne dass irgendetwas blockiert.
    hinweise = lease_hinweise(ausser_sitzung=session_id)
    if hinweise:
        zeilen.append(f"{len(hinweise)} file(s) currently leased by other session(s):")
        zeilen.extend(f"- {h}" for h in hinweise)

    return "\n".join(zeilen)


def raum_verlassen(session_id: str) -> None:
    """Ersetzt rooms_hook.py:handle_session_end(). Zeile bleibt bestehen
    (zustand='frei') statt geloescht zu werden -- gleiche Semantik wie das
    alte status=COMPLETE (Historie bleibt sichtbar, zaehlt aber nicht mehr
    als 'aktiv')."""
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            c.execute("UPDATE zero_raum SET zustand='frei' WHERE session_id=?", (session_id,))
            c.commit()
    except Exception as e:
        _log(f"raum_verlassen fehler sid={session_id}: {e}")
    _raum_ruf_schreiben(session_id, "LEAVE", f"session={session_id}")


def raum_puls_erneuern(session_id: str) -> None:
    """Herzschlag fuer eine laufende Sitzung -- laeuft bei JEDEM
    UserPromptSubmit (nicht nur SessionStart/`/clear`/`/resume`/`/compact`/
    `/fork`), damit lang laufende Sitzungen `seit` nicht einmalig am Beitritt
    stehen lassen und danach durch den Anzeige-Schwellenwert
    (_RAUM_STALE_MINUTEN) unsichtbar werden, obwohl real weitergearbeitet
    wird. Kein Re-Join, keine neue JOIN/PULSE-Zeile in zero_raum_ruf, keine
    volle Neuberechnung der anderen Sitzungen -- nur `seit` auffrischen.
    Eigene Zeile zuerst auffrischen (beweist Lebendigkeit unabhaengig vom
    vorherigen zustand), DANACH die Verfall-Kehraus fuer alle anderen, damit
    die eigene, gerade aufgefrischte Zeile dabei nie erwischt werden kann.

    Das macht Verfall WIRKLICH statt nur beim Anzeigen weggefiltert
    (des Nutzers Vorgabe: keine Leichen im Raum -- zustand muss Realitaet sein,
    entweder eingeloggt oder beim Verschwinden automatisch ausgeloggt).
    Ergaenzt raum_verlassen() (SessionEnd, sofortiger korrekter Abgang) als
    Auffangnetz fuer Abstuerze/Kills, die nie SessionEnd ausloesen. Ein
    einzelnes indiziertes UPDATE je Statement, sub-millisekunden-billig.
    Fail-silent wie alles hier -- darf den Hook nie stoeren."""
    jetzt = _jetzt()
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            c.execute(
                "UPDATE zero_raum SET zustand='arbeitet', seit=? WHERE session_id=?",
                (jetzt, session_id),
            )
            c.execute(
                "UPDATE zero_raum SET zustand='frei' WHERE zustand='arbeitet' AND seit < ?",
                (jetzt - _RAUM_STALE_MINUTEN * 60,),
            )
            c.commit()
    except Exception as e:
        _log(f"raum_puls_erneuern fehler sid={session_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════
# ABSCHNITT: RAUM-NACHRICHTEN (Nutzer-Auftrag 2026-08-27, woertlich: "ihr
# habt im Room keine Moeglichkeit miteinander zu reden? das soll ein Agent
# loesen und moeglich machen.") -- echter Nachrichtenkanal ZWISCHEN
# Sitzungen/Agenten im Raum, additiv zu zero_raum (wer ist da)/zero_raum_ruf
# (Ereignislog, bleibt unveraendert -- NACHRICHT wird zusaetzlich dort
# vermerkt, kurz, ohne den Volltext, siehe raum_nachricht_senden()). Zwei
# neue Tabellen, selbstheilend per CREATE TABLE IF NOT EXISTS angelegt wie
# themen_status oben (kein schema_leer.sql-Eintrag noetig, gleiche
# Konvention/Praezedenzfall vom selben Tag).
#
# WARUM ZWEI TABELLEN STATT NUR EINER raum_nachricht MIT gelesen_am (wie im
# Auftrag als Grundstruktur skizziert, "dein Ermessen bei Details, aber
# pruef sie gegen bestehenden Code"): eine einzelne gelesen_am-Spalte
# funktioniert nur, wenn GENAU EIN Empfaenger existiert. Bei --alle
# (an_session_id IS NULL) haben MEHRERE Sitzungen dieselbe Zeile zu lesen --
# wuerde die erste lesende Sitzung gelesen_am setzen, verschwaende die
# Nachricht sofort auch fuer jede andere Sitzung, die sie noch nie gesehen
# hat (Bug, real durchdacht, nicht erst live gefunden). raum_nachricht_
# gelesen fuehrt den Lesestatus deshalb PRO EMPFAENGER, nur fuer Broadcasts
# gebraucht (direkte Nachrichten behalten die einfache gelesen_am-Spalte,
# weil dort ohnehin nur ein Empfaenger existiert -- kein unnoetiger zweiter
# Schreibpfad fuer den haeufigeren Fall).
#
# EMPFANG ist NIE aktives Pollen: _raum_nachrichten_kontext_text() laeuft
# automatisch bei JEDEM SessionStart UND UserPromptSubmit (siehe cmd_hook(),
# genau die zwei Stellen, die bereits additionalContext ausliefern koennen
# -- PostToolUse/PreToolUse drucken normalerweise nichts, siehe cmd_hook()-
# Kopf), analog zu raum_beitreten_und_pulsen()/raum_puls_erneuern(). Holt
# ungelesene Nachrichten UND markiert sie im selben Zug als gelesen -- keine
# Sitzung sieht dieselbe Nachricht zweimal, keine Sitzung muss je aktiv
# nachfragen. Kein LLM-Aufruf hier (reines SQL), §1.9.2 gewahrt.
# ═══════════════════════════════════════════════════════════════════════
def _sicherstellen_raum_nachricht_tabellen(c) -> None:
    c.execute(
        "CREATE TABLE IF NOT EXISTS raum_nachricht("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, von_session_id TEXT NOT NULL, "
        "an_session_id TEXT, text TEXT NOT NULL, erstellt_am REAL NOT NULL, gelesen_am REAL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS raum_nachricht_gelesen("
        "nachricht_id INTEGER NOT NULL, session_id TEXT NOT NULL, gelesen_am REAL NOT NULL, "
        "PRIMARY KEY (nachricht_id, session_id))"
    )


_RAUM_NACHRICHT_ABHOL_LIMIT = 10  # je Hook-Aufruf hoechstens so viele neue Nachrichten anhaengen


def raum_nachricht_senden(von_session_id: str, text: str, an_session_id: Optional[str] = None) -> dict:
    """Schreibt EINE neue Zeile -- direkte Nachricht (an_session_id gesetzt)
    oder Broadcast (an_session_id NULL, sichtbar fuer ALLE ausser dem
    Absender, auch fuer Sitzungen die erst spaeter pulsen, solange die Zeile
    fuer sie noch ungelesen ist). `text` wird nicht inhaltlich validiert,
    nur hart gekappt (Missbrauchsschutz, kein Freitext-Roman im Hook-
    Kontext einer fremden Sitzung)."""
    von_session_id = (von_session_id or "").strip() or "manuell"
    text = _kurz((text or "").strip(), 2000)
    if not text:
        return {"ok": False, "grund": "leerer Text"}
    an_session_id = (an_session_id or "").strip() or None
    jetzt = _jetzt()
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            _sicherstellen_raum_nachricht_tabellen(c)
            cur = c.execute(
                "INSERT INTO raum_nachricht (von_session_id, an_session_id, text, erstellt_am, gelesen_am) "
                "VALUES (?,?,?,?,NULL)",
                (von_session_id, an_session_id, text, jetzt),
            )
            nachricht_id = cur.lastrowid
            c.commit()
    except Exception as e:
        _log(f"raum_nachricht_senden fehler von={von_session_id} an={an_session_id}: {e}")
        return {"ok": False, "grund": str(e)}
    # Kurzspur im bestehenden Ereignislog -- ohne Volltext (der lebt allein
    # in raum_nachricht), damit zero_raum_ruf nicht zum zweiten Nachrichten-
    # speicher wird, nur ein Hinweis "hier ist was passiert".
    _raum_ruf_schreiben(von_session_id, "NACHRICHT",
                         f"an={an_session_id or 'ALLE'} id={nachricht_id} text={_kurz(text, 80)}")
    return {"ok": True, "id": nachricht_id, "an": an_session_id or "ALLE"}


def _raum_nachrichten_abholen_und_markieren(session_id: str, limit: int = _RAUM_NACHRICHT_ABHOL_LIMIT) -> list:
    """Liest ungelesene Nachrichten fuer `session_id` (direkt ODER Broadcast,
    die diese Sitzung noch nicht gesehen hat) und markiert sie SOFORT als
    gelesen (direkt: gelesen_am, Broadcast: eigene Zeile in
    raum_nachricht_gelesen) -- danach taucht dieselbe Nachricht fuer diese
    Sitzung nie wieder auf. Fail-silent wie alles hier, darf einen Hook
    nie stoeren."""
    if not session_id or session_id == "unknown":
        return []
    jetzt = _jetzt()
    treffer = []
    try:
        with contextlib.closing(schreib_verbindung()) as c:
            _sicherstellen_raum_nachricht_tabellen(c)
            zeilen = c.execute(
                "SELECT n.id, n.von_session_id, n.an_session_id, n.text, n.erstellt_am "
                "FROM raum_nachricht n WHERE n.von_session_id != ? AND ("
                "  (n.an_session_id = ? AND n.gelesen_am IS NULL)"
                "  OR (n.an_session_id IS NULL AND NOT EXISTS ("
                "        SELECT 1 FROM raum_nachricht_gelesen g "
                "        WHERE g.nachricht_id = n.id AND g.session_id = ?))"
                ") ORDER BY n.erstellt_am ASC LIMIT ?",
                (session_id, session_id, session_id, limit),
            ).fetchall()
            for nid, von, an, text, erstellt_am in zeilen:
                if an is not None:
                    c.execute("UPDATE raum_nachricht SET gelesen_am=? WHERE id=?", (jetzt, nid))
                else:
                    c.execute(
                        "INSERT INTO raum_nachricht_gelesen (nachricht_id, session_id, gelesen_am) "
                        "VALUES (?,?,?) ON CONFLICT(nachricht_id, session_id) DO NOTHING",
                        (nid, session_id, jetzt),
                    )
                treffer.append({"id": nid, "von": von, "broadcast": an is None,
                                 "text": text, "erstellt_am": erstellt_am})
            c.commit()
    except Exception as e:
        _log(f"raum_nachrichten_abholen fehler sid={session_id}: {e}")
        return []
    return treffer


def _raum_nachrichten_kontext_text(session_id: str) -> Optional[str]:
    """Baut den additionalContext-Block aus frisch abgeholten Nachrichten --
    None, wenn keine neuen da sind (kein Fuelltext, gleiche Disziplin wie
    _themen_status_uebersicht_text())."""
    treffer = _raum_nachrichten_abholen_und_markieren(session_id)
    if not treffer:
        return None
    n = len(treffer)
    zeilen = [f"Der Raum -- {n} neue Nachricht{'en' if n != 1 else ''} von anderen Sitzungen:"]
    for t in treffer:
        art = "an alle" if t["broadcast"] else "direkt an dich"
        zeilen.append(f"  - [{art}] von {t['von']}: {t['text']}")
    zeilen.append('(Antworten: `stern.py raum-nachricht-senden --an <session_id|--alle> --text "..."`)')
    return "\n".join(zeilen)


def _architekt_governance_intervall(signal_anzahl: int) -> int:
    """PHASE 17v2 (Nachtrag 'Kadenz, Tiefensitzung, Mandat, Darstellung'):
    ersetzt die feste 25-Zug-Kadenz durch eine anlaufende Kadenz -- die
    ERSTEN 2 Signale alle 10 Zuege, die NAECHSTEN 3 alle 25 Zuege, DANACH
    dauerhaft alle 40 Zuege. `signal_anzahl` ist, wie viele Signale bereits
    ausgeliefert wurden (0 = noch keins) -- bestimmt, welches Regime das
    NAECHSTE Signal hat."""
    if signal_anzahl < 2:
        return 10
    if signal_anzahl < 5:
        return 25
    return 40


def architekt_governance_zug() -> dict:
    """PHASE 17 Punkt 4, PHASE 17v2 eskaliert -- ein Zug = ein 'Stop'-Ereignis
    (siehe cmd_hook). GLOBAL gezaehlt (nicht sitzungsgebunden -- Konzeptdokument:
    'Zaehler in star_konfig', keine <sid>-Bindung wie bei persona.zaehler.<sid>),
    weil die Selbstpflegeschleife die gesamte Nutzung betrifft, nicht eine
    einzelne Sitzung.

    Zwei Zaehler, bewusst getrennt:
    - architekt_governance.zug_zaehler: cummulativ ueber ALLE Zuege je,
      unveraendert aus PHASE 17 (nur informativ, fuer die Signal-Anzeige
      "bei Zug N").
    - architekt_governance.zuege_seit_signal: seit dem LETZTEN ausgelieferten
      Signal, NEU in PHASE 17v2 -- das ist der Zaehler, der gegen das
      aktuelle Kadenz-Regime (_architekt_governance_intervall) geprueft und
      bei Ausloesung auf 0 zurueckgesetzt wird.
    - architekt_governance.signal_anzahl: wie viele Signale INSGESAMT schon
      ausgeliefert wurden -- bestimmt das aktuelle Regime (10er/25er/40er)."""
    try:
        zaehler = int(_konfig_dyn_get("architekt_governance.zug_zaehler", "0") or "0") + 1
    except Exception:
        zaehler = 1
    _konfig_dyn_set("architekt_governance.zug_zaehler", str(zaehler), quelle="phase17-stop")

    try:
        seit_signal = int(_konfig_dyn_get("architekt_governance.zuege_seit_signal", "0") or "0") + 1
    except Exception:
        seit_signal = 1
    try:
        signal_anzahl = int(_konfig_dyn_get("architekt_governance.signal_anzahl", "0") or "0")
    except Exception:
        signal_anzahl = 0

    intervall = _architekt_governance_intervall(signal_anzahl)
    faellig = seit_signal >= intervall
    if faellig:
        seit_signal = 0
        signal_anzahl += 1
        _konfig_dyn_set("architekt_governance.signal_anzahl", str(signal_anzahl), quelle="phase17-stop")
        _konfig_dyn_set("architekt_governance.signal_faellig", "1", quelle="phase17-stop")
    _konfig_dyn_set("architekt_governance.zuege_seit_signal", str(seit_signal), quelle="phase17-stop")
    return {
        "zug_zaehler": zaehler, "zuege_seit_signal": seit_signal,
        "signal_anzahl": signal_anzahl, "intervall_verwendet": intervall,
        "faellig": faellig,
    }


_ARCHITEKT_GOVERNANCE_TEXT_CACHE: Optional[str] = None


def _architekt_governance_text() -> str:
    """Instruktionstext fuer die Hauptinstanz bei einer faelligen 25-Zug-
    Marke -- liegt als Datei in daten/ (derselbe Grund wie persona.md/
    sebukku.txt: Tonvorrat/Instruktion bleibt Dateisache, nur Zustand geht
    in unified.db, siehe Abschnittskopf PERSONA/SEBUKKU weiter oben)."""
    global _ARCHITEKT_GOVERNANCE_TEXT_CACHE
    if _ARCHITEKT_GOVERNANCE_TEXT_CACHE is not None:
        return _ARCHITEKT_GOVERNANCE_TEXT_CACHE
    p = STERN_DIR / "daten" / "architekt_governance.md"
    _ARCHITEKT_GOVERNANCE_TEXT_CACHE = _sprachvariante_lesen(p, "")
    return _ARCHITEKT_GOVERNANCE_TEXT_CACHE


def _architekt_governance_signal_pruefen() -> Optional[str]:
    """Wird aus UserPromptSubmit aufgerufen (siehe cmd_hook). Liest das
    Flag, das architekt_governance_zug() bei Stop gesetzt hat -- hoechstens
    EINMAL ausgeliefert (Flag wird sofort zurueckgesetzt), danach normal
    weiterzaehlen bis zur naechsten 25er-Marke."""
    if _konfig_dyn_get("architekt_governance.signal_faellig", "0") != "1":
        return None
    _konfig_dyn_set("architekt_governance.signal_faellig", "0", quelle="userpromptsubmit")
    text = _architekt_governance_text()
    if not text:
        return None
    zaehler = _konfig_dyn_get("architekt_governance.zug_zaehler", "?")
    signal_anzahl = _konfig_dyn_get("architekt_governance.signal_anzahl", "?")
    intervall = _architekt_governance_intervall(max(int(signal_anzahl) - 1, 0) if str(signal_anzahl).isdigit() else 0)
    return (
        f"[PHASE 17 -- Architekten-Governance-Marke Nr. {signal_anzahl} bei Zug {zaehler} "
        f"(Kadenz-Regime: alle {intervall} Zuege)]\n\n{text}"
    )
