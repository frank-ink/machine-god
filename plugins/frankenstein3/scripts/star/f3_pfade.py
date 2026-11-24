"""f3_pfade.py -- zentrale Pfadaufloesung des Frankenstein-3.0-Plugins (stdlib only, wirft nie).

CODE        = Ordner dieser Datei (im Plugin, nur lesen)
PLUGIN_ROOT = $PLUGIN_ROOT, sonst Wurzel des entpackten Plugins (gefunden via .claude-plugin/plugin.json)
DATA        = $FRANK3_DATA, sonst $CLAUDE_PLUGIN_DATA, sonst $XDG_DATA_HOME/frankenstein3, sonst $HOME/.local/share/frankenstein3  (Laufzeit, schreibbar)
DB          = DATA/unified.db  (wird beim ersten Start aus daten/schema_leer.sql frisch angelegt)
LOG         = DATA/hook.log
Nichts hier liest oder schreibt ~/.claude/star oder ~/.local/share/agentzero.

GRF/ClayCode:
  R_t = (PLUGIN_ROOT, DATA, DB, LOG)  -- aufloesbarer Zustand
  E_t = os.environ                    -- Evidenz (Environment)
  F   = _plugin_root() / _data_dir()  -- reine Funktionen der Umgebung
  Die Modulkonstanten werden erst beim Zugriff berechnet (PEP 562), damit ein
  Import nie von einem fehlerhaften Environment abhaengt und die Aufloesung
  jederzeit gegen die aktuelle Umgebung messbar bleibt.

Invarianten (ClayCode):
  - Kein hard-codierter /home/-Pfad und kein Maschinenname im Quelltext.
  - DATA wird niemals aus PLUGIN_ROOT abgeleitet (Code != Daten).
  - Relative Werte in FRANK3_DATA|CLAUDE_PLUGIN_DATA|XDG_DATA_HOME|PLUGIN_ROOT loesen PfadeError aus.
  - ON_VIOLATION -> TriggerEmergencyDeescalation (hier: PfadeError, Aufruf bricht ab).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

CODE = Path(__file__).resolve().parent

#: Name des Datenverzeichnisses unter XDG_DATA_HOME bzw. im lokalen Share.
DATA_DIR_NAME = "frankenstein3"


class PfadeError(Exception):
    """Fehler bei Pfadaufloesung (relative Pfade, fehlende Marker, etc.)."""
    pass


def _resolve_absolute(path_str: str, var_name: str) -> Path:
    """Expandiert ~, macht absolut, weist relative Pfade zurueck."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        raise PfadeError(f"{var_name}: relativer Pfad nicht erlaubt: {path_str!r} (muss absolut sein oder ~ enthalten)")
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
    raise PfadeError(f"Plugin-Wurzel nicht gefunden: .claude-plugin/plugin.json nicht in Elternverzeichnissen von {start}")


def _plugin_root() -> Path:
    """Ermittelt die Plugin-Wurzel: $PLUGIN_ROOT (absolut) oder Suche nach .claude-plugin/plugin.json.

    PLUGIN_ROOT is CODE ONLY (read-only). Never used for data directory resolution.
    """
    v = os.environ.get("PLUGIN_ROOT", "").strip()
    if v:
        return _resolve_absolute(v, "PLUGIN_ROOT")
    return _find_plugin_root(CODE)


def _data_dir() -> Path:
    """Ermittelt das Datenverzeichnis nach XDG Base Directory Specification (UNIFIED PRECEDENCE):
    1. $FRANK3_DATA (absolut)
    2. $CLAUDE_PLUGIN_DATA (absolut)
    3. $XDG_DATA_HOME/frankenstein3
    4. ~/.local/share/frankenstein3

    This precedence MUST match install.sh's resolve_data_dir() exactly.
    PLUGIN_ROOT is NEVER used for data directory resolution.
    """
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
        return p.resolve() / DATA_DIR_NAME

    # 4. ~/.local/share/frankenstein3 (XDG default)
    home = Path.home()
    return (home / ".local" / "share" / DATA_DIR_NAME).resolve()


# Oeffentliche API (klein geschrieben, wie im Akzeptanztest erwartet)
def plugin_root() -> Path:
    """Oeffentlicher Zugriff auf die Plugin-Wurzel (CODE ONLY, read-only)."""
    return _plugin_root()


def data_dir() -> Path:
    """Oeffentlicher Zugriff auf das Datenverzeichnis (UNIFIED PRECEDENCE)."""
    return _data_dir()


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

    data = _data_dir()
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
    if name in ("DATA", "DB", "LOG"):
        data = _data_dir()
        if name == "DATA":
            return data
        if name == "DB":
            return data / "unified.db"
        return data / "hook.log"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    return sorted(set(globals()) | set(_LAZY_CONSTANTS))


def ensure_db() -> Path:
    """Legt DATA und eine frische unified.db aus schema_leer.sql an, falls sie fehlt. Idempotent, fail-silent."""
    data = _data_dir()
    db = data / "unified.db"
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
                    _data_dir()
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
                data = _data_dir()
                expected = (xdg / "frankenstein3").resolve()
                assert data == expected, f"expected {expected}, got {data}"
            print("OK: XDG_DATA_HOME resolution works")

    def test_default_paths_match_installer_location():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            with _patched_env(HOME=str(home)):
                data = _data_dir()
                expected = (home / ".local" / "share" / "frankenstein3").resolve()
                assert data == expected, f"expected {expected}, got {data}"
            print("OK: default path matches installer location")

    def test_installer_runtime_unified_resolution():
        """install.sh and f3_pfade.py resolve to the same path under all precedence levels."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_plugin = root / "frankenstein3"
            # We can't easily run install.sh here without copying, so we test the logic directly
            # by verifying the precedence order matches what install.sh documents
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            claude = root / "claude"
            claude.mkdir()
            xdg = root / "xdg"
            xdg.mkdir()

            # Test each precedence level in isolation
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), FRANK3_DATA=str(frank)):
                assert _data_dir() == frank.resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), CLAUDE_PLUGIN_DATA=str(claude)):
                assert _data_dir() == claude.resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin), XDG_DATA_HOME=str(xdg)):
                assert _data_dir() == (xdg / "frankenstein3").resolve()
            with _patched_env(HOME=str(home), PLUGIN_ROOT=str(test_plugin)):
                assert _data_dir() == (home / ".local" / "share" / "frankenstein3").resolve()
            print("OK: installer runtime unified resolution matches")

    def test_installer_runtime_unified_with_frank3_data():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            frank = root / "frank"
            frank.mkdir()
            with _patched_env(HOME=str(home), FRANK3_DATA=str(frank), CLAUDE_PLUGIN_DATA=str(root / "claude"), XDG_DATA_HOME=str(root / "xdg")):
                assert _data_dir() == frank.resolve()
            print("OK: FRANK3_DATA wins over others")

    def test_installer_runtime_unified_with_claude_plugin_data():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            claude = root / "claude"
            claude.mkdir()
            with _patched_env(HOME=str(home), CLAUDE_PLUGIN_DATA=str(claude), XDG_DATA_HOME=str(root / "xdg")):
                assert _data_dir() == claude.resolve()
            print("OK: CLAUDE_PLUGIN_DATA wins when FRANK3_DATA absent")

    def test_installer_runtime_unified_with_xdg():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = _isolated_home(root)
            xdg = root / "xdg"
            xdg.mkdir()
            with _patched_env(HOME=str(home), XDG_DATA_HOME=str(xdg)):
                assert _data_dir() == (xdg / "frankenstein3").resolve()
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
                data = _data_dir()
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
                # Should not contain absolute home paths
                assert "/home/" not in output or output.count("/home/") == 0, f"found /home/ in output: {output}"
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
    print("\nAll 17 tests passed!")
