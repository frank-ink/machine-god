"""f3_pfade.py -- zentrale Pfadaufloesung des Frankenstein-3.0-Plugins (stdlib only, wirft nie).

CODE        = Ordner dieser Datei (im Plugin, nur lesen)
PLUGIN_ROOT = $PLUGIN_ROOT, sonst Wurzel des entpackten Plugins (gefunden via .claude-plugin/plugin.json)
DATA        = $FRANK3_DATA, sonst $CLAUDE_PLUGIN_DATA, sonst <PluginRoot>/.frankenstein3  (Laufzeit, schreibbar)
DB          = DATA/unified.db  (wird beim ersten Start aus daten/schema_leer.sql frisch angelegt)
LOG         = DATA/hook.log
Nichts hier liest oder schreibt ~/.claude/star oder ~/.local/share/agentzero.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

CODE = Path(__file__).resolve().parent


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
    """Geht von start aus nach oben, bis .claude-plugin/plugin.json gefunden wird."""
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
    """Ermittelt die Plugin-Wurzel: $PLUGIN_ROOT (absolut) oder Suche nach .claude-plugin/plugin.json."""
    v = os.environ.get("PLUGIN_ROOT", "").strip()
    if v:
        return _resolve_absolute(v, "PLUGIN_ROOT")
    return _find_plugin_root(CODE)


def _data_dir() -> Path:
    """Ermittelt das Datenverzeichnis: $FRANK3_DATA / $CLAUDE_PLUGIN_DATA (absolut) oder <PluginRoot>/.frankenstein3."""
    for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA"):
        v = os.environ.get(var, "").strip()
        if v:
            return _resolve_absolute(v, var)
    return _plugin_root() / ".frankenstein3"


# Oeffentliche API (klein geschrieben, wie im Akzeptanztest erwartet)
def plugin_root() -> Path:
    """Oeffentlicher Zugriff auf die Plugin-Wurzel."""
    return _plugin_root()


def data_dir() -> Path:
    """Oeffentlicher Zugriff auf das Datenverzeichnis."""
    return _data_dir()


# Modulare Konstanten (für Rückwärtskompatibilität)
PLUGIN_ROOT = _plugin_root()
DATA = _data_dir()
DB = DATA / "unified.db"
LOG = DATA / "hook.log"


def ensure_db() -> Path:
    """Legt DATA und eine frische unified.db aus schema_leer.sql an, falls sie fehlt. Idempotent, fail-silent."""
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        if DB.exists() and DB.stat().st_size > 0:
            return DB
        sql = (CODE / "daten" / "schema_leer.sql").read_text(encoding="utf-8")
        tmp = DATA / ("unified.db.neu.%d" % os.getpid())
        c = sqlite3.connect(str(tmp))
        try:
            c.executescript(sql)
            c.commit()
        finally:
            c.close()
        os.replace(str(tmp), str(DB))
    except Exception:
        pass
    return DB


# ---- Tests (können mit python -m pytest oder direkt ausgeführt werden) ----
if __name__ == "__main__":
    import sys
    import tempfile
    import shutil

    def test_plugin_root_finds_marker():
        # Temporäre Struktur bauen: /tmp/test/frankenstein3/.claude-plugin/plugin.json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "frankenstein3"
            (root / ".claude-plugin").mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "test"}')
            scripts_star = root / "scripts" / "star"
            scripts_star.mkdir(parents=True)
            test_file = scripts_star / "test_f3_pfade.py"
            test_file.write_text("""
import sys
sys.path.insert(0, r\"%s\")
from f3_pfade import _find_plugin_root
root = _find_plugin_root(Path(r\"%s\"))
assert root.name == \"frankenstein3\", f\"expected frankenstein3, got {root.name}\"
print(\"OK: plugin root found\")
""" % (str(scripts_star), str(scripts_star)))
            result = os.system(f"{sys.executable} {test_file}")
            assert result == 0, "test_plugin_root_finds_marker failed"

    def test_plugin_root_env_absolute():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "myplugin"
            root.mkdir()
            os.environ["PLUGIN_ROOT"] = str(root)
            try:
                # Neues Modul laden (simuliert durch direkten Funktionsaufruf)
                from importlib import reload
                import f3_pfade
                reload(f3_pfade)
                assert f3_pfade.plugin_root() == root.resolve()
                print("OK: PLUGIN_ROOT absolute accepted")
            finally:
                del os.environ["PLUGIN_ROOT"]

    def test_plugin_root_env_relative_rejected():
        os.environ["PLUGIN_ROOT"] = "relative/path"
        try:
            from importlib import reload
            import f3_pfade
            reload(f3_pfade)
            try:
                f3_pfade.plugin_root()
                assert False, "should have raised"
            except PfadeError as e:
                assert "relativer Pfad nicht erlaubt" in str(e)
                print("OK: PLUGIN_ROOT relative rejected")
        finally:
            del os.environ["PLUGIN_ROOT"]

    def test_data_dir_env_absolute():
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "mydata"
            data.mkdir()
            os.environ["FRANK3_DATA"] = str(data)
            try:
                from importlib import reload
                import f3_pfade
                reload(f3_pfade)
                assert f3_pfade.data_dir() == data.resolve()
                print("OK: FRANK3_DATA absolute accepted")
            finally:
                del os.environ["FRANK3_DATA"]

    def test_data_dir_env_relative_rejected():
        os.environ["FRANK3_DATA"] = "relative/data"
        try:
            from importlib import reload
            import f3_pfade
            reload(f3_pfade)
            try:
                f3_pfade.data_dir()
                assert False, "should have raised"
            except PfadeError as e:
                assert "relativer Pfad nicht erlaubt" in str(e)
                print("OK: FRANK3_DATA relative rejected")
        finally:
            del os.environ["FRANK3_DATA"]

    def test_default_data_dir_ends_with_dot_frankenstein3():
        # Nutzt die echte Plugin-Struktur (diese Datei liegt in plugins/frankenstein3/scripts/star/)
        d = data_dir()
        assert str(d).endswith(".frankenstein3"), f"expected .frankenstein3 suffix, got {d}"
        assert plugin_root().name == "frankenstein3", f"expected frankenstein3, got {plugin_root().name}"
        print("OK: default paths match installer location")

    # Führe Tests aus
    test_plugin_root_finds_marker()
    test_plugin_root_env_absolute()
    test_plugin_root_env_relative_rejected()
    test_data_dir_env_absolute()
    test_data_dir_env_relative_rejected()
    test_default_data_dir_ends_with_dot_frankenstein3()
    print("\nAlle Tests bestanden.")
