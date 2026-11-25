"""f3_pfade.py -- zentrale Pfadaufloesung des Frankenstein-3.0-Plugins (stdlib only, wirft nie).

CODE        = Ordner dieser Datei (im Plugin, nur lesen)
PLUGIN_ROOT = $PLUGIN_ROOT, sonst Wurzel des entpackten Plugins (gefunden via .claude-plugin/plugin.json)
DATA        = $FRANK3_DATA, sonst $CLAUDE_PLUGIN_DATA, sonst $XDG_DATA_HOME/frankenstein3, sonst $HOME/.local/share/frankenstein3  (Laufzeit, schreibbar)
DB          = DATA/unified.db  (wird beim ersten Start aus schema_leer.sql frisch angelegt)
LOG         = DATA/hook.log
Nichts hier liest oder schreibt ~/.claude/star oder ~/.local/share/agentzero.

GRF/ClayCode:
  R_t = (PLUGIN_ROOT, DATA, DB, LOG)  -- aufloesbarer Zustand, lazy neu gemessen pro Zugriff
  E_t = os.environ                    -- Evidenz (Environment)
  F   = _resolve_data_dir() / _resolve_db_path()  -- reine Funktionen der Umgebung
  F3_DB_PATH = bestehender Dateipfad mit DB-Suffix => genau diese Datei (nicht Parent + unified.db)
  F3_DB_PATH = bestehendes Verzeichnis => <verzeichnis>/unified.db
  Die Modulkonstanten werden erst beim Zugriff berechnet (PEP 562), damit ein
  Import nie von einem fehlerhaften Environment abhaengt und die Aufloesung
  jederzeit gegen die aktuelle Umgebung messbar bleibt.

Invarianten (ClayCode):
  - Kein hard-codierter /home/-Pfad und kein Maschinenname im Quelltext.
  - DATA wird niemals aus PLUGIN_ROOT abgeleitet (Code != Daten).
  - Relative Werte in FRANK3_DATA|CLAUDE_PLUGIN_DATA|XDG_DATA_HOME|PLUGIN_ROOT loesen PfadeError aus.
  - ON_VIOLATION -> TriggerEmergencyDeescalation (hier: PfadeError, Aufruf bricht ab).
  - F3_DB_PATH auf existierende DB-Datei liefert diese Datei unveraenderlich (ON_VIOLATION -> PfadeError).
  - F3_DB_PATH auf existierendes Verzeichnis haengt unified.db an (ON_VIOLATION -> PfadeError).
  - get_db_path() hat keinen data_dir-Parameter mehr (toter Parameter entfernt).
    Ein expliziter DB-Override geht ausschliesslich ueber F3_DB_PATH.
  - DRY-RUN ISOLATION: When F3_DRY_RUN=1, resolver MUST return F3_DB_PATH target
    (or error if F3_DB_PATH unset), ignoring FRANK3_DATA/CLAUDE_PLUGIN_DATA/XDG/HOME.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

CODE = Path(__file__).resolve().parent

#: Name des Datenverzeichnisses unter XDG_DATA_HOME bzw. im lokalen Share.
DATA_DIR_NAME = "frankenstein3"

#: Dateiendungen, die einen Pfad als explizite SQLite-Datenbank-Datei kennzeichnen.
DB_FILE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".db3"})


class PfadeError(Exception):
    """Fehler bei Pfadaufloesung (relative Pfade, fehlende Marker, etc.)."""


def _resolve_absolute(path_str: str, var_name: str) -> Path:
    """Expandiert ~, macht absolut, weist relative Pfade zurueck."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        raise PfadeError(
            f"{var_name}: relativer Pfad nicht erlaubt: {path_str!r} (muss absolut sein oder ~ enthalten)"
        )
    return p.resolve()


def _find_plugin_root(start: Path) -> Path:
    """Geht von start aus nach oben, bis .claude-plugin/plugin.json gefunden wird.

    Die Suche ist absichtlich unabhaengig vom Verzeichnisnamen: der Marker
    entscheidet, nicht der Name des Kopier-Ziels.
    """
    current = start
    for _ in range(10):  # Sicherheitsgrenze gegen Endlosschleifen
        marker = current / ".claude-plugin" / "plugin.json"
        if marker.is_file():
            return current
        if current.parent == current:  # Wurzel erreicht
            break
        current = current.parent
    raise PfadeError(
        f"Plugin-Wurzel nicht gefunden: .claude-plugin/plugin.json nicht in Elternverzeichnissen von {start}"
    )


def _plugin_root() -> Path:
    """Ermittelt die Plugin-Wurzel: $PLUGIN_ROOT (absolut) oder Suche nach .claude-plugin/plugin.json.

    PLUGIN_ROOT is CODE ONLY (read-only). Never used for data directory resolution.
    """
    v = os.environ.get("PLUGIN_ROOT", "").strip()
    if v:
        return _resolve_absolute(v, "PLUGIN_ROOT")
    return _find_plugin_root(CODE)


def resolve_plugin_root() -> Path:
    """Public alias for _plugin_root(), kept for status.py compatibility."""
    return _plugin_root()


def _resolve_data_dir() -> Path:
    """Ermittelt das Datenverzeichnis nach XDG Base Directory Specification (UNIFIED PRECEDENCE):
    1. $FRANK3_DATA (absolut)
    2. $CLAUDE_PLUGIN_DATA (absolut)
    3. $XDG_DATA_HOME/frankenstein3
    4. ~/.local/share/frankenstein3

    This precedence MUST match install.sh's resolve_data_dir() exactly.
    PLUGIN_ROOT is NEVER used for data directory resolution.
    Single source of truth used by _resolve_db_path() and all callers.
    """
    # DRY-RUN ISOLATION: In dry-run mode, data directory resolution is bypassed
    # entirely by _resolve_db_path(). This function is still called by check()
    # and other non-DB-path callers, so it retains normal behavior.
    # The dry-run guard lives in _resolve_db_path() where DB path is resolved.

    # 1. FRANK3_DATA (highest priority, explicit user override)
    v = os.environ.get("FRANK3_DATA", "").strip()
    if v:
        return _resolve_absolute(v, "FRANK3_DATA")

    # 2. CLAUDE_PLUGIN_DATA
    v = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if v:
        return _resolve_absolute(v, "CLAUDE_PLUGIN_DATA")

    # 3. XDG_DATA_HOME/frankenstein3
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        p = Path(xdg).expanduser()
        if not p.is_absolute():
            raise PfadeError(f"XDG_DATA_HOME: relativer Pfad nicht erlaubt: {xdg!r}")
        return (p.resolve() / DATA_DIR_NAME).resolve()

    # 4. ~/.local/share/frankenstein3 (XDG default)
    home = Path.home()
    return (home / ".local" / "share" / DATA_DIR_NAME).resolve()


def _data_dir() -> Path:
    """Public alias for _resolve_data_dir(), kept for compatibility."""
    return _resolve_data_dir()


def resolve_data_dir() -> Path:
    """Public alias for _resolve_data_dir(), kept for status.py compatibility."""
    return _resolve_data_dir()


def _resolve_db_path() -> Path:
    """Single source of truth for DB path resolution.

    Precedence (highest first):
      1. DRY-RUN ISOLATION: F3_DRY_RUN=1 requires F3_DB_PATH set, returns it (ignores all other vars)
      2. F3_DB_PATH (explicit override, must be absolute or ~)
         - existing directory      -> <dir>/unified.db
         - existing file           -> that exact file (never parent + unified.db)
         - missing, DB suffix      -> that exact file (intended new database file)
         - missing, other suffix   -> <path>/unified.db (treated as directory)
      3. _resolve_data_dir() / "unified.db"

    Fail-closed on relative F3_DB_PATH.
    """
    # DRY-RUN ISOLATION GUARD: When F3_DRY_RUN=1, resolver MUST return F3_DB_PATH
    # target (or error if F3_DB_PATH unset), ignoring FRANK3_DATA/CLAUDE_PLUGIN_DATA/XDG/HOME.
    if is_dry_run():
        f3_db = os.environ.get("F3_DB_PATH", "").strip()
        if not f3_db:
            raise PfadeError(
                "F3_DRY_RUN=1 requires F3_DB_PATH to be set (absolute path or ~). "
                "Dry-run isolation forbids falling back to FRANK3_DATA/CLAUDE_PLUGIN_DATA/XDG/HOME."
            )
        p = _resolve_absolute(f3_db, "F3_DB_PATH")
        if p.is_dir():
            return (p / "unified.db").resolve()
        if p.is_file():
            return p.resolve()
        if p.suffix.lower() in DB_FILE_SUFFIXES:
            return p.resolve()
        return (p / "unified.db").resolve()

    # 1. F3_DB_PATH takes absolute precedence (normal mode)
    f3_db = os.environ.get("F3_DB_PATH", "").strip()
    if f3_db:
        p = _resolve_absolute(f3_db, "F3_DB_PATH")
        if p.is_dir():
            return (p / "unified.db").resolve()
        if p.is_file():
            return p.resolve()
        if p.suffix.lower() in DB_FILE_SUFFIXES:
            return p.resolve()
        return (p / "unified.db").resolve()

    # 2. Fall through to unified data directory precedence
    return (_resolve_data_dir() / "unified.db").resolve()


def get_db_path(data_dir: Path | None = None) -> Path:
    """Resolve the unified.db path.

    Der totere data_dir-Parameter wurde entfernt: get_db_path() nimmt kein
    Argument mehr. Ein uebergebenes Argument wird abgelehnt, damit kein
    falscher Pfad stillschweigend verwendet wird. Ein expliziter DB-Override
    geht ausschliesslich ueber die Umgebungsvariable F3_DB_PATH.
    """
    if data_dir is not None:
        raise PfadeError(
            "get_db_path() takes no argument; explicit DB override only via F3_DB_PATH"
        )
    return _resolve_db_path()


def get_schema_path(plugin_root: Path) -> Path:
    """Return the path to the empty schema SQL file."""
    return plugin_root / "daten" / "schema_leer.sql"


# Unified truthy set for F3_DRY_RUN (matches install.sh's _normalize_f3_dry_run):
#   truthy  = {'1', 'true', 'yes', 'on'}  (case-insensitive)
#   falsy   = {'0', 'false', 'no', 'off', ''} (case-insensitive)
# Unknown values are treated as falsy (fail-closed).
_TRUTHY_DRY_RUN = frozenset({"1", "true", "yes", "on"})


def is_dry_run() -> bool:
    """Return True when F3_DRY_RUN is set to a truthy value.

    Used by ensure_db() and callers to skip any real database writes.
    """
    raw = os.environ.get("F3_DRY_RUN", "").strip().lower()
    return raw in _TRUTHY_DRY_RUN


# Oeffentliche API (klein geschrieben, wie im Akzeptanztest erwartet)
def plugin_root() -> Path:
    """Oeffentlicher Zugriff auf die Plugin-Wurzel (CODE ONLY, read-only)."""
    return _plugin_root()


def data_dir() -> Path:
    """Oeffentlicher Zugriff auf das Datenverzeichnis (UNIFIED PRECEDENCE)."""
    return _resolve_data_dir()


def check() -> str:
    """Gibt alle auflosenden Pfade nur als env-relative Angaben zurueck.

    Keine absoluten /home/-Pfade im Output; Verzeichnisse unter $HOME werden
    mit ~ abgekuerzt. Die Ausgabe zeigt die Umgebungs-Variable, die den Wert
    liefert, sowie das aufgeloste Ziel.
    """
    home = Path.home()

    def _home_relative(p: Path) -> str:
        try:
            return "~/" + str(p.relative_to(home))
        except ValueError:
            return str(p)

    root = _plugin_root()
    lines = []

    pr_env = os.environ.get("PLUGIN_ROOT", "").strip()
    if pr_env:
        lines.append(f"PLUGIN_ROOT=$PLUGIN_ROOT -> {_home_relative(root)}")
    else:
        lines.append(f"PLUGIN_ROOT=<marker .claude-plugin/plugin.json> -> {_home_relative(root)}")

    data = _resolve_data_dir()
    if os.environ.get("FRANK3_DATA", "").strip():
        src = "$FRANK3_DATA"
    elif os.environ.get("CLAUDE_PLUGIN_DATA", "").strip():
        src = "$CLAUDE_PLUGIN_DATA"
    elif os.environ.get("XDG_DATA_HOME", "").strip():
        src = "$XDG_DATA_HOME/frankenstein3"
    else:
        src = "$HOME/.local/share/frankenstein3"

    lines.append(f"DATA={src} -> {_home_relative(data)}")
    lines.append(f"DB=DATA/unified.db -> {_home_relative(data / 'unified.db')}")
    lines.append(f"LOG=DATA/hook.log -> {_home_relative(data / 'hook.log')}")
    return "\n".join(lines)


# Modulare Konstanten (fuer Rueckwaertskompatibilitaet).
# Sie werden bewusst lazy berechnet (PEP 562): der Import haengt nie an der
# Umgebung, und jeder Zugriff misst die aktuelle Umgebung neu.
_LAZY_CONSTANTS = ("PLUGIN_ROOT", "DATA", "DB", "LOG")


def __getattr__(name: str) -> Path:
    if name == "PLUGIN_ROOT":
        return _plugin_root()
    if name == "DATA":
        return _resolve_data_dir()
    if name == "DB":
        # Use unified resolver for DB attribute access
        return _resolve_db_path()
    if name == "LOG":
        return _resolve_data_dir() / "hook.log"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    return sorted(set(globals()) | set(_LAZY_CONSTANTS))


def ensure_db() -> Path:
    """Legt DATA und eine frische unified.db aus schema_leer.sql an, falls sie fehlt. Idempotent, fail-silent."""
    if is_dry_run():
        # In dry-run mode never create or touch the real database.
        # Return the resolved DB path (which respects F3_DB_PATH for fixture DBs)
        return _resolve_db_path()
    data = _resolve_data_dir()
    db = _resolve_db_path()
    try:
        data.mkdir(parents=True, exist_ok=True)
        if db.exists() and db.stat().st_size > 0:
            return db
        sql = (CODE / "daten" / "schema_leer.sql").read_text(encoding="utf-8")
        tmp = data / ("unified.db.neu.%d" % os.getpid())
        c = sqlite3.connect(str(tmp))
        try:
            c.executescript(sql)
            c.commit()
        finally:
            c.close()
        os.replace(str(tmp), str(db))
    except Exception:
        pass
    return db


# ---- Tests (koennen mit python -m pytest oder direkt ausgefuehrt werden) ----
if __name__ == "__main__":
    import contextlib
    import subprocess
    import sys
    import tempfile

    parser = argparse.ArgumentParser(description="f3_pfade Pfadaufloesung pruefen")
    parser.add_argument("--check", action="store_true", help="Nur env-relative Pfade ausgeben und beenden")
    args = parser.parse_args()

    if args.check:
        print(check())
        raise SystemExit(0)

    @contextlib.contextmanager
    def _patched_env(**values):
        """Setzt Environment-Variablen in os.environ und stellt sie danach wieder her."""
        missing = object()
        previous = {key: os.environ.get(key, missing) for key in values}
        try:
            for key, value in values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = str(value)
            yield os.environ
        finally:
            for key, value in previous.items():
                if value is missing:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def _isolated_home(root):
        """Temporaeres HOME; das echte $HOME wird nie benutzt."""
        home = Path(root) / "home"
        home.mkdir(parents=True, exist_ok=True)
        return home

    def test_plugin_root_finds_marker():
        # Temporaere Struktur mit beliebigem Namen: der Marker entscheidet, nicht der Name.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copied-plugin-any-name"
            (root / ".claude-plugin").mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "test"}', encoding="utf-8")
            scripts_star = root / "scripts" / "star"
            scripts_star.mkdir(parents=True)
            found = _find_plugin_root(scripts_star)
            assert found == root.resolve(), f"expected {root.resolve()}, got {found}"
            print("OK: plugin root found (name independent)")

    def test_plugin_root_env_absolute():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-plugin-root"
            root.mkdir()
            with _patched_env(PLUGIN_ROOT=str(root)):
                assert _plugin_root() == root.resolve()
            print("OK: PLUGIN_ROOT env absolute honored")

    def test_data_dir_env_relative_rejected():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), FRANK3_DATA="relative/path"):
                try:
                    _resolve_data_dir()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
            print("OK: relative FRANK3_DATA rejected")

    def test_data_dir_xdg():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            xdg = root / "xdg"
            xdg.mkdir()
            with _patched_env(HOME=str(home), XDG_DATA_HOME=str(xdg)):
                data = _resolve_data_dir()
                expected = (xdg / "frankenstein3").resolve()
                assert data == expected, f"expected {expected}, got {data}"
            print("OK: XDG_DATA_HOME resolution works")

    def test_default_paths_match_installer_location():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home)):
                data = _resolve_data_dir()
                expected = (home / ".local" / "share" / "frankenstein3").resolve()
                assert data == expected, f"expected {expected}, got {data}"
            print("OK: default path matches installer location")

    def test_installer_runtime_unified_resolution():
        """install.sh and f3_pfade.py resolve to the same path under all precedence levels."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_plugin = root / "frankenstein3"
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            claude = root / "claude"
            claude.mkdir()
            xdg = root / "xdg"
            xdg.mkdir()

            # Test each precedence level in isolation
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), FRANK3_DATA=str(frank)):
                assert _resolve_data_dir() == frank.resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), CLAUDE_PLUGIN_DATA=str(claude)):
                assert _resolve_data_dir() == claude.resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), XDG_DATA_HOME=str(xdg)):
                assert _resolve_data_dir() == (xdg / "frankenstein3").resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin)):
                assert _resolve_data_dir() == (home / ".local" / "share" / "frankenstein3").resolve()
            print("OK: installer runtime unified resolution matches")

    def test_installer_runtime_unified_with_frank3_data():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            with _patched_env(HOME=str(home), FRANK3_DATA=str(frank), CLAUDE_PLUGIN_DATA=str(root / "claude"), XDG_DATA_HOME=str(root / "xdg")):
                assert _resolve_data_dir() == frank.resolve()
            print("OK: FRANK3_DATA wins over others")

    def test_installer_runtime_unified_with_claude_plugin_data():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            claude = root / "claude"
            claude.mkdir()
            with _patched_env(HOME=str(home), CLAUDE_PLUGIN_DATA=str(claude), XDG_DATA_HOME=str(root / "xdg")):
                assert _resolve_data_dir() == claude.resolve()
            print("OK: CLAUDE_PLUGIN_DATA wins when FRANK3_DATA absent")

    def test_installer_runtime_unified_with_xdg():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            xdg = root / "xdg"
            xdg.mkdir()
            with _patched_env(HOME=str(home), XDG_DATA_HOME=str(xdg)):
                assert _resolve_data_dir() == (xdg / "frankenstein3").resolve()
            print("OK: XDG_DATA_HOME wins when higher vars absent")

    def test_installer_never_writes_under_plugin_root():
        """DATA directory must never be resolved under PLUGIN_ROOT (code != data)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = root / "plugin"
            plugin.mkdir()
            (plugin / ".claude-plugin").mkdir()
            (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "test"}', encoding="utf-8")
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(plugin)):
                data = _resolve_data_dir()
                # data must not be inside plugin root
                try:
                    data.relative_to(plugin.resolve())
                    assert False, f"data_dir {data} resolved under PLUGIN_ROOT {plugin}"
                except ValueError:
                    pass  # expected: data is outside plugin root
            print("OK: installer never writes under plugin root")

    # --- check() function tests ---
    def test_check_no_absolute_home_paths():
        """check() output must not contain absolute /home/... or /Users/... paths."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home)):
                output = check()
                assert "/home/" not in output, f"found /home/ in output: {output}"
                assert "/Users/" not in output, f"found /Users/ in output: {output}"
                # Should use ~ notation for paths under home
                assert "~/" in output, f"expected ~/ notation in output: {output}"
            print("OK: check() has no absolute home paths")

    def test_check_relative_frank3_data_raises():
        """check() should raise PfadeError when FRANK3_DATA is relative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), FRANK3_DATA="relative/path"):
                try:
                    check()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
            print("OK: check() rejects relative FRANK3_DATA")

    def test_check_relative_claude_plugin_data_raises():
        """check() should raise PfadeError when CLAUDE_PLUGIN_DATA is relative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), CLAUDE_PLUGIN_DATA="relative/path"):
                try:
                    check()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
            print("OK: check() rejects relative CLAUDE_PLUGIN_DATA")

    def test_check_relative_xdg_data_home_raises():
        """check() should raise PfadeError when XDG_DATA_HOME is relative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), XDG_DATA_HOME="relative/path"):
                try:
                    check()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
            print("OK: check() rejects relative XDG_DATA_HOME")

    def test_check_relative_plugin_root_raises():
        """check() should raise PfadeError when PLUGIN_ROOT is relative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), PLUGIN_ROOT="relative/path"):
                try:
                    check()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
            print("OK: check() rejects relative PLUGIN_ROOT")

    def test_check_src_label_matches_precedence():
        """check() src label must match the actual precedence branch that wins."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            claude = root / "claude"
            claude.mkdir()
            xdg = root / "xdg"
            xdg.mkdir()

            # FRANK3_DATA wins
            with _patched_env(HOME=str(home), FRANK3_DATA=str(frank), CLAUDE_PLUGIN_DATA=str(claude), XDG_DATA_HOME=str(xdg)):
                output = check()
                assert "DATA=$FRANK3_DATA" in output, f"expected FRANK3_DATA src, got: {output}"

            # CLAUDE_PLUGIN_DATA wins (FRANK3_DATA not set)
            with _patched_env(HOME=str(home), CLAUDE_PLUGIN_DATA=str(claude), XDG_DATA_HOME=str(xdg), FRANK3_DATA=None):
                output = check()
                assert "DATA=$CLAUDE_PLUGIN_DATA" in output, f"expected CLAUDE_PLUGIN_DATA src, got: {output}"

            # XDG_DATA_HOME wins (higher vars not set)
            with _patched_env(HOME=str(home), XDG_DATA_HOME=str(xdg), FRANK3_DATA=None, CLAUDE_PLUGIN_DATA=None):
                output = check()
                assert "DATA=$XDG_DATA_HOME/frankenstein3" in output, f"expected XDG_DATA_HOME src, got: {output}"

            # Default wins (no vars set)
            with _patched_env(HOME=str(home), FRANK3_DATA=None, CLAUDE_PLUGIN_DATA=None, XDG_DATA_HOME=None):
                output = check()
                assert "DATA=$HOME/.local/share/frankenstein3" in output, f"expected HOME default src, got: {output}"
            print("OK: check() src label matches precedence branch")

    def test_get_db_path_rejects_argument():
        """get_db_path() must reject an explicit data_dir argument."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home)):
                try:
                    get_db_path(home / "some" / "dir")
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "takes no argument" in str(e)
            print("OK: get_db_path rejects explicit argument")

    def test_get_db_path_respects_f3_db_path():
        """get_db_path() must honor F3_DB_PATH over the derived DATA/unified.db."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "unified.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            with _patched_env(HOME=str(home), F3_DB_PATH=str(fixture_db)):
                assert get_db_path() == fixture_db.resolve()
            print("OK: get_db_path reads F3_DB_PATH")

    def test_is_dry_run_reads_f3_dry_run():
        """is_dry_run must read F3_DRY_RUN using the unified truthy set."""
        with _patched_env(F3_DRY_RUN="1"):
            assert is_dry_run() is True
        with _patched_env(F3_DRY_RUN="true"):
            assert is_dry_run() is True
        with _patched_env(F3_DRY_RUN="yes"):
            assert is_dry_run() is True
        with _patched_env(F3_DRY_RUN="on"):
            assert is_dry_run() is True
        with _patched_env(F3_DRY_RUN="0"):
            assert is_dry_run() is False
        with _patched_env(F3_DRY_RUN="false"):
            assert is_dry_run() is False
        with _patched_env(F3_DRY_RUN="no"):
            assert is_dry_run() is False
        with _patched_env(F3_DRY_RUN=""):
            assert is_dry_run() is False
        with _patched_env(F3_DRY_RUN=None):
            assert is_dry_run() is False
        # Case insensitivity
        with _patched_env(F3_DRY_RUN="TRUE"):
            assert is_dry_run() is True
        with _patched_env(F3_DRY_RUN="FALSE"):
            assert is_dry_run() is False
        # Unknown values are falsy (fail-closed)
        with _patched_env(F3_DRY_RUN="maybe"):
            assert is_dry_run() is False
        print("OK: is_dry_run reads F3_DRY_RUN with unified truthy set")

    def test_ensure_db_skips_in_dry_run():
        """ensure_db must not create the real DB when F3_DRY_RUN is set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            real_db = home / ".local" / "share" / "frankenstein3" / "unified.db"
            with _patched_env(HOME=str(home), F3_DRY_RUN="1"):
                result = ensure_db()
                # Should return the path but not create the file
                assert not real_db.exists(), f"ensure_db created real DB in dry-run: {real_db}"
            print("OK: ensure_db skips real DB in dry-run")

    # --- New tests for unified DB path resolution ---
    def test_resolve_db_path_f3_db_path_highest():
        """_resolve_db_path: F3_DB_PATH wins over everything."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture = root / "fixture.db"
            frank = root / "frank"
            frank.mkdir()
            with _patched_env(HOME=str(home), F3_DB_PATH=str(fixture), FRANK3_DATA=str(frank)):
                assert _resolve_db_path() == fixture.resolve()
            print("OK: _resolve_db_path F3_DB_PATH highest")

    def test_resolve_db_path_frank3_data_second():
        """_resolve_db_path: FRANK3_DATA/unified.db when F3_DB_PATH not set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            with _patched_env(HOME=str(home), FRANK3_DATA=str(frank), CLAUDE_PLUGIN_DATA=str(root / "claude")):
                assert _resolve_db_path() == (frank / "unified.db").resolve()
            print("OK: _resolve_db_path FRANK3_DATA second")

    def test_resolve_db_path_claude_plugin_data_third():
        """_resolve_db_path: CLAUDE_PLUGIN_DATA/unified.db when higher not set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            claude = root / "claude"
            claude.mkdir()
            with _patched_env(HOME=str(home), CLAUDE_PLUGIN_DATA=str(claude), XDG_DATA_HOME=str(root / "xdg")):
                assert _resolve_db_path() == (claude / "unified.db").resolve()
            print("OK: _resolve_db_path CLAUDE_PLUGIN_DATA third")

    def test_resolve_db_path_xdg_fourth():
        """_resolve_db_path: XDG_DATA_HOME/frankenstein3/unified.db when higher not set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            xdg = root / "xdg"
            xdg.mkdir()
            with _patched_env(HOME=str(home), XDG_DATA_HOME=str(xdg)):
                assert _resolve_db_path() == (xdg / "frankenstein3" / "unified.db").resolve()
            print("OK: _resolve_db_path XDG fourth")

    def test_resolve_db_path_home_fifth():
        """_resolve_db_path: ~/.local/share/frankenstein3/unified.db as final fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home)):
                assert _resolve_db_path() == (home / ".local" / "share" / "frankenstein3" / "unified.db").resolve()
            print("OK: _resolve_db_path HOME fifth")

    def test_resolve_db_path_relative_f3_db_path_raises():
        """_resolve_db_path must raise PfadeError on relative F3_DB_PATH."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home), F3_DB_PATH="relative/path"):
                try:
                    _resolve_db_path()
                    assert False, "expected PfadeError"
                except PfadeError as e:
                    assert "relativer Pfad nicht erlaubt" in str(e)
                    assert "F3_DB_PATH" in str(e)
            print("OK: _resolve_db_path rejects relative F3_DB_PATH")

    def test_get_db_path_uses_unified_resolver():
        """get_db_path() must delegate to _resolve_db_path (rejects data_dir param)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture = root / "fixture.db"
            frank = root / "frank"
            frank.mkdir()
            with _patched_env(HOME=str(home), F3_DB_PATH=str(fixture), FRANK3_DATA=str(frank)):
                # Calling with an argument must be rejected
                try:
                    get_db_path(frank)
                    assert False, "expected PfadeError"
                except PfadeError:
                    pass
                # No argument returns the unified resolver
                assert get_db_path() == fixture.resolve()
            print("OK: get_db_path uses unified resolver")

    # --- DRY-RUN ISOLATION TESTS ---
    def test_dry_run_requires_f3_db_path():
        """F3_DRY_RUN=1 without F3_DB_PATH must raise PfadeError (isolation guard)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            # FRANK3_DATA is set but F3_DB_PATH is not - should fail in dry-run
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", FRANK3_DATA=str(frank)):
                try:
                    _resolve_db_path()
                    assert False, "expected PfadeError: dry-run requires F3_DB_PATH"
                except PfadeError as e:
                    assert "F3_DRY_RUN=1 requires F3_DB_PATH" in str(e)
            print("OK: dry-run requires F3_DB_PATH")

    def test_dry_run_returns_f3_db_path_ignores_frank3_data():
        """F3_DRY_RUN=1 with F3_DB_PATH returns fixture, ignores FRANK3_DATA."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "test.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            frank = root / "frank"
            frank.mkdir()
            # Both FRANK3_DATA and F3_DB_PATH set, but dry-run should use F3_DB_PATH only
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_db), FRANK3_DATA=str(frank)):
                result = _resolve_db_path()
                assert result == fixture_db.resolve(), f"expected {fixture_db.resolve()}, got {result}"
                # Verify it did NOT use FRANK3_DATA path
                assert result != (frank / "unified.db").resolve()
            print("OK: dry-run returns F3_DB_PATH, ignores FRANK3_DATA")

    def test_dry_run_returns_f3_db_path_ignores_claude_plugin_data():
        """F3_DRY_RUN=1 with F3_DB_PATH returns fixture, ignores CLAUDE_PLUGIN_DATA."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "test.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            claude = root / "claude"
            claude.mkdir()
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_db), CLAUDE_PLUGIN_DATA=str(claude)):
                result = _resolve_db_path()
                assert result == fixture_db.resolve()
                assert result != (claude / "unified.db").resolve()
            print("OK: dry-run returns F3_DB_PATH, ignores CLAUDE_PLUGIN_DATA")

    def test_dry_run_returns_f3_db_path_ignores_xdg():
        """F3_DRY_RUN=1 with F3_DB_PATH returns fixture, ignores XDG_DATA_HOME."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "test.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            xdg = root / "xdg"
            xdg.mkdir()
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_db), XDG_DATA_HOME=str(xdg)):
                result = _resolve_db_path()
                assert result == fixture_db.resolve()
                assert result != (xdg / "frankenstein3" / "unified.db").resolve()
            print("OK: dry-run returns F3_DB_PATH, ignores XDG_DATA_HOME")

    def test_dry_run_returns_f3_db_path_ignores_home():
        """F3_DRY_RUN=1 with F3_DB_PATH returns fixture, ignores HOME default."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "test.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_db)):
                result = _resolve_db_path()
                assert result == fixture_db.resolve()
                assert result != (home / ".local" / "share" / "frankenstein3" / "unified.db").resolve()
            print("OK: dry-run returns F3_DB_PATH, ignores HOME default")

    def test_dry_run_with_f3_db_path_as_directory():
        """F3_DRY_RUN=1 with F3_DB_PATH as directory returns <dir>/unified.db."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_dir = root / "fixture_dir"
            fixture_dir.mkdir()
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_dir)):
                result = _resolve_db_path()
                assert result == (fixture_dir / "unified.db").resolve()
            print("OK: dry-run with F3_DB_PATH as directory")

    def test_dry_run_with_f3_db_path_as_new_file():
        """F3_DRY_RUN=1 with F3_DB_PATH as new .db file returns that exact file."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture" / "new.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            with _patched_env(HOME=str(home), F3_DRY_RUN="1", F3_DB_PATH=str(fixture_db)):
                result = _resolve_db_path()
                assert result == fixture_db.resolve()
            print("OK: dry-run with F3_DB_PATH as new .db file")

    def test_dry_run_case_insensitive():
        """F3_DRY_RUN truthy values (TRUE, Yes, ON) all trigger isolation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            fixture_db = root / "fixture.db"
            for val in ("TRUE", "Yes", "ON", "true", "yes", "on", "1"):
                with _patched_env(HOME=str(home), F3_DRY_RUN=val, F3_DB_PATH=str(fixture_db)):
                    result = _resolve_db_path()
                    assert result == fixture_db.resolve(), f"failed for F3_DRY_RUN={val}"
        print("OK: dry-run case insensitive truthy values")

    # Run all tests
    test_plugin_root_finds_marker()
    test_plugin_root_env_absolute()
    test_data_dir_env_relative_rejected()
    test_data_dir_xdg()
    test_default_paths_match_installer_location()
    test_installer_runtime_unified_resolution()
    test_installer_runtime_unified_with_frank3_data()
    test_installer_runtime_unified_with_claude_plugin_data()
    test_installer_runtime_unified_with_xdg()
    test_installer_never_writes_under_plugin_root()
    test_check_no_absolute_home_paths()
    test_check_relative_frank3_data_raises()
    test_check_relative_claude_plugin_data_raises()
    test_check_relative_xdg_data_home_raises()
    test_check_relative_plugin_root_raises()
    test_check_src_label_matches_precedence()
    test_get_db_path_rejects_argument()
    test_get_db_path_respects_f3_db_path()
    test_is_dry_run_reads_f3_dry_run()
    test_ensure_db_skips_in_dry_run()
    test_resolve_db_path_f3_db_path_highest()
    test_resolve_db_path_frank3_data_second()
    test_resolve_db_path_claude_plugin_data_third()
    test_resolve_db_path_xdg_fourth()
    test_resolve_db_path_home_fifth()
    test_resolve_db_path_relative_f3_db_path_raises()
    test_get_db_path_uses_unified_resolver()
    test_dry_run_requires_f3_db_path()
    test_dry_run_returns_f3_db_path_ignores_frank3_data()
    test_dry_run_returns_f3_db_path_ignores_claude_plugin_data()
    test_dry_run_returns_f3_db_path_ignores_xdg()
    test_dry_run_returns_f3_db_path_ignores_home()
    test_dry_run_with_f3_db_path_as_directory()
    test_dry_run_with_f3_db_path_as_new_file()
    test_dry_run_case_insensitive()
    print("\nAll tests passed!")
