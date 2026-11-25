"""Pfad-Aufloesung fuer FranKenstein 3 - portabel ueber alle Sprachen.

Alle Pfade werden ausschliesslich aus Umgebungsvariablen und dem Dateisystem
abgeleitet. Es gibt keine fest verdrahteten Benutzerverzeichnisse und keine
Maschinennamen; die Aufloesung bleibt damit auf eine andere Maschine kopierbar.

Diese Top-Level-Datei ist der autoritative Resolver. Das read-only-Skript
scripts/star/f3_pfade.py wird nicht mehr als Quelle der Praezedenz zitiert;
contract_env.json verweist auf diese Datei.

Umgebungsvariablen (Aufloesung, keine Hardcodierung):
  - FRANK3_DATA        : expliziter Data-Root-Override (hoechste Prioritaet)
  - FRANKENSTEIN3_ROOT : Data-Root / Plugin-Root-Override
  - CLAUDE_PLUGIN_DATA : alternativer Data-Root
  - XDG_DATA_HOME      : XDG Base Directory
  - HOME / USERPROFILE : Heimatverzeichnis-Fallbacks
  - F3_DB_PATH         : direkter Pfad zur unified.db (Datei oder Verzeichnis)
  - F3_DRY_RUN         : Trockenlauf, dann nur F3_DB_PATH massgeblich

Praezedenz (Data-Root, ohne unified.db):
  1. FRANK3_DATA
  2. FRANKENSTEIN3_ROOT
  3. Ableitung aus F3_DB_PATH (Data-Root: Elternverzeichnis bei Datei,
     Verzeichnis selbst bei Verzeichnis)
  4. CLAUDE_PLUGIN_DATA
  5. XDG_DATA_HOME/frankenstein3
  6. ~/.local/share/frankenstein3              (HOME)
  7. %USERPROFILE%/AppData/Local/frankenstein3

Praezedenz (DB-Pfad):
  1. FRANK3_DATA/unified.db
  2. FRANKENSTEIN3_ROOT/unified.db
  3. F3_DB_PATH (Datei oder Verzeichnis, siehe _infer_kind)
  4. CLAUDE_PLUGIN_DATA/unified.db
  5. XDG_DATA_HOME/frankenstein3/unified.db
  6. ~/.local/share/frankenstein3/unified.db
  7. %USERPROFILE%/AppData/Local/frankenstein3/unified.db

Dry-Run (F3_DRY_RUN truthy: 1|true|yes|on, case-insensitive):
  - F3_DB_PATH ist Pflicht (kein Fallback).
  - Alle anderen Pfad-Variablen werden ignoriert.
  - Der DB-Pfad-Resolver gibt F3_DB_PATH (tilde-expandiert) direkt zurueck.
  - Der Data-Root-Resolver gibt das Elternverzeichnis zurueck, wenn
    F3_DB_PATH eine Datei ist, und das Verzeichnis selbst, wenn F3_DB_PATH
    ein Verzeichnis ist.
  - Keine Schreibzugriffe: ensure_db() legt im Dry-Run nichts an (kein mkdir,
    keine DB-Initialisierung, keine Fixture-Erstellung, kein Self-Check,
    keine Registrierung).
  - Ungueltige F3_DRY_RUN-Werte loesen PfadeError aus (fail-closed).

Bundle-Layout (relativ, host-unabhaengig):
  - resolve_plugin_root() liefert das Verzeichnis dieser Datei.
  - resolve_bundle_path(...) verjoinigt relative Bundle-Komponenten.
  - resolve_manifest_paths() liefert env-abgeleitete Manifest-Pfade; der
    Eintrag 'resolver' zeigt auf diese Top-Level-Datei.

Pfade werden tilde-expandiert (HOME, sonst USERPROFILE), aber nicht aufgeloest
(keine Symlink-Aufloesung): Konfiguration und Ergebnis bleiben dadurch
identisch und vorhersagbar.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Iterator, Mapping, Optional


class PfadeError(RuntimeError):
    """Fehler bei der Pfad-Aufloesung (fail-closed, kein Silent-Fallback)."""


class PathKind(str, Enum):
    """Tagged union: ist der Pfad eine Datei oder ein Verzeichnis?"""

    FILE = "file"
    DIRECTORY = "directory"


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})
DB_FILE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db3")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _normalize_dry_run(raw: Optional[str]) -> str:
    """Normalisiert F3_DRY_RUN auf '1' (aktiv) oder '0' (inaktiv).

    Contract-Regel (contract_env.json -> dry_run): nur '1|true|yes|on'
    (case-insensitive) aktiviert den Dry-Run. Nur '0|false|no|off'
    (case-insensitive) deaktiviert ihn explizit. Jeder andere Wert loest
    PfadeError aus (fail-closed: kein Default, kein Silent-Fallback).
    """
    lower = (raw or "").strip().lower()
    if lower in _TRUTHY:
        return "1"
    if lower in _FALSY:
        return "0"
    raise PfadeError(
        "Ungueltiger F3_DRY_RUN-Wert: '%s'. Erlaubt: truthy=%s, falsy=%s"
        % (raw, sorted(_TRUTHY), sorted(_FALSY))
    )


def _looks_windows(raw: str) -> bool:
    """Heuristik: sieht der Pfad wie ein Windows-Pfad aus?

    Erlaubt die portable Behandlung von %USERPROFILE%-Stilen auf POSIX und
    umgekehrt, ohne maschinenspezifische Pfade fest zu verdrahten.
    """
    if not raw:
        return False
    if _WINDOWS_DRIVE_RE.match(raw):
        return True
    return "\\" in raw


def _home() -> Optional[str]:
    """HOME zuerst, danach USERPROFILE.

    Bewusst kein pwd-/os.path.expanduser-Lookup: die Aufloesung bleibt damit
    deterministisch und maschinenunabhaengig.
    """
    for name in ("HOME", "USERPROFILE"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def _expand(raw: str, home: Optional[str]) -> str:
    """Expandiert '~' und '~/...' gegen das uebergebene Home-Verzeichnis."""
    if raw == "~":
        if not home:
            raise PfadeError("HOME not set, cannot expand '~'")
        return home
    if raw.startswith("~/") or raw.startswith("~\\"):
        if not home:
            raise PfadeError("HOME not set, cannot expand '~/' path: %s" % raw)
        if _looks_windows(home):
            rest = raw[2:].replace("/", "\\")
            return str(PureWindowsPath(home).joinpath(rest))
        return home + raw[1:]
    return raw


def _expand_env(raw: str) -> str:
    """Tilde-Expansion mit dem aktuellen HOME/USERPROFILE."""
    return _expand(raw, _home())


def _join(base: str, *parts: str) -> Path:
    """Verbindet Komponenten portabel (Windows-Stil bleibt Windows-Stil)."""
    if _looks_windows(base):
        return Path(str(PureWindowsPath(base).joinpath(*parts)))
    return Path(base).joinpath(*parts)


def resolve_plugin_root() -> Path:
    """Bundle-Layout: Plugin-Wurzel = Verzeichnis dieser Datei.

    Relativ zum Bundle, nie zu einem festen Benutzerpfad.
    """
    return Path(__file__).resolve().parent


def resolve_bundle_path(*parts: str) -> Path:
    """Relativer Bundle-Pfad (Skript, Vertrag, Schema) unterhalb der Plugin-Wurzel."""
    return resolve_plugin_root().joinpath(*parts)


def _exists(path: Path) -> bool:
    """Existenzpruefung, die auf exotische Pfade nicht hart fehlschlaegt."""
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _is_dry_run() -> bool:
    """Prueft ob Dry-Run-Modus aktiv ist (normalisierter Wert '1').

    Raises:
        PfadeError: Wenn F3_DRY_RUN einen ungueltigen Wert hat (fail-closed).
    """
    return _normalize_dry_run(os.environ.get("F3_DRY_RUN")) == "1"


def _infer_kind(path: Path) -> PathKind:
    """Leitet Datei vs. Verzeichnis ab (einzige Quelle fuer diese Entscheidung).

    Evidenzreihenfolge:
      1. Dateisystem (exists + is_file/is_dir)
      2. Suffix: DB_FILE_SUFFIXES -> FILE, sonst DIRECTORY
    """
    if _exists(path):
        try:
            if path.is_file():
                return PathKind.FILE
        except (OSError, ValueError):
            pass
        return PathKind.DIRECTORY
    if path.suffix.lower() in DB_FILE_SUFFIXES:
        return PathKind.FILE
    return PathKind.DIRECTORY


def _data_root(path: Path) -> Path:
    """Data-Root zu einem Pfad: Elternverzeichnis bei Datei, Verzeichnis selbst bei Dir."""
    if _infer_kind(path) is PathKind.FILE:
        return path.parent
    return path


def _dry_run_db_path() -> Path:
    """F3_DB_PATH im Dry-Run (Pflicht, tilde-expandiert, sonst unveraendert)."""
    raw = os.environ.get("F3_DB_PATH")
    if not raw or not raw.strip():
        raise PfadeError(
            "F3_DRY_RUN=1 erfordert F3_DB_PATH (kein Fallback auf andere Pfad-Variablen)"
        )
    return Path(_expand_env(raw))


def _dry_run_data_dir() -> Path:
    """Data-Root im Dry-Run: Elternverzeichnis (Datei) bzw. Verzeichnis selbst (Dir)."""
    return _data_root(_dry_run_db_path())


def _resolve_data_dir() -> Path:
    """
    Loest das Datenverzeichnis auf (ohne unified.db).

    Praezedenz:
    1. FRANK3_DATA (hoechste Prioritaet, expliziter Nutzer-Override)
    2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root-Override)
    3. Ableitung aus F3_DB_PATH (gleiche Quelle wie der DB-Pfad)
    4. CLAUDE_PLUGIN_DATA
    5. XDG_DATA_HOME/frankenstein3
    6. ~/.local/share/frankenstein3 (HOME)
    7. %USERPROFILE%/AppData/Local/frankenstein3
    """
    if _is_dry_run():
        return _dry_run_data_dir()

    # 1. FRANK3_DATA (hoechste Prioritaet, expliziter Nutzer-Override)
    frank3_data = os.environ.get("FRANK3_DATA")
    if frank3_data:
        return Path(_expand_env(frank3_data))

    # 2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root-Override)
    frank3_root = os.environ.get("FRANKENSTEIN3_ROOT")
    if frank3_root:
        return Path(_expand_env(frank3_root))

    # 3. Ableitung aus F3_DB_PATH (gleiche Quelle wie der DB-Pfad)
    f3_db_path = os.environ.get("F3_DB_PATH")
    if f3_db_path:
        return _data_root(Path(_expand_env(f3_db_path)))

    # 4. CLAUDE_PLUGIN_DATA
    claude_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if claude_plugin_data:
        return Path(_expand_env(claude_plugin_data))

    # 5. XDG_DATA_HOME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return _join(_expand_env(xdg_data_home), "frankenstein3")

    # 6. HOME fallback (XDG-Default)
    home = os.environ.get("HOME")
    if home:
        return _join(_expand_env(home), ".local", "share", "frankenstein3")

    # 7. Windows USERPROFILE fallback
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return _join(_expand_env(userprofile), "AppData", "Local", "frankenstein3")

    raise PfadeError(
        "Cannot resolve data dir: no FRANK3_DATA, FRANKENSTEIN3_ROOT, F3_DB_PATH, "
        "CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, or USERPROFILE set"
    )


def resolve_db_path() -> Path:
    """Loest den vollstaendigen Pfad zur unified.db auf."""
    if _is_dry_run():
        return _dry_run_db_path()

    # 1. FRANK3_DATA (hoechste Prioritaet, expliziter Nutzer-Override)
    frank3_data = os.environ.get("FRANK3_DATA")
    if frank3_data:
        return _join(_expand_env(frank3_data), "unified.db")

    # 2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root-Override)
    frank3_root = os.environ.get("FRANKENSTEIN3_ROOT")
    if frank3_root:
        return _join(_expand_env(frank3_root), "unified.db")

    # 3. F3_DB_PATH (Datei oder Verzeichnis, gleiche Inferenz wie beim Data-Root)
    f3_db_path = os.environ.get("F3_DB_PATH")
    if f3_db_path:
        p = Path(_expand_env(f3_db_path))
        if _infer_kind(p) is PathKind.FILE:
            return p
        return _join(str(p), "unified.db")

    # 4. CLAUDE_PLUGIN_DATA
    claude_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if claude_plugin_data:
        return _join(_expand_env(claude_plugin_data), "unified.db")

    # 5. XDG_DATA_HOME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return _join(_expand_env(xdg_data_home), "frankenstein3", "unified.db")

    # 6. HOME fallback (XDG-Default)
    home = os.environ.get("HOME")
    if home:
        return _join(
            _expand_env(home), ".local", "share", "frankenstein3", "unified.db"
        )

    # 7. Windows USERPROFILE fallback
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return _join(
            _expand_env(userprofile),
            "AppData",
            "Local",
            "frankenstein3",
            "unified.db",
        )

    raise PfadeError(
        "Cannot resolve db path: no FRANK3_DATA, FRANKENSTEIN3_ROOT, F3_DB_PATH, "
        "CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, or USERPROFILE set"
    )


def resolve_data_dir() -> Path:
    """Oeffentlicher Zugriff auf den Data-Root (ohne unified.db)."""
    return _resolve_data_dir()


def resolve_manifest_paths() -> dict[str, str]:
    """Env-abgeleitete Manifest-Pfade (keine fest verdrahteten Pfade).

    Keys entsprechen dem Pfad-Block in zero-manifest.json:
      plugin_root, data_dir, db_path, resolver, contract

    'resolver' zeigt auf die autoritative Top-Level-Datei (f3_pfade.py);
    scripts/star/f3_pfade.py ist read-only und keine Quelle der Praezedenz.
    """
    return {
        "plugin_root": str(resolve_plugin_root()),
        "data_dir": str(resolve_data_dir()),
        "db_path": str(resolve_db_path()),
        "resolver": str(resolve_bundle_path("f3_pfade.py")),
        "contract": str(resolve_bundle_path("docs", "zero", "contract_env.json")),
    }


# Kompatibilitaets-Aliase: identisches Funktionsobjekt (kein Wrapper, kein zweiter Pfad).
get_db_path = resolve_db_path
get_data_root = resolve_data_dir


def ensure_db() -> Path:
    """Legt das Elternverzeichnis des DB-Pfads an und liefert den DB-Pfad.

    Im Dry-Run wird nichts geschrieben (Dry-Run = keine Seiteneffekte):
    kein mkdir, keine DB-Initialisierung, keine Fixture-Erstellung, kein
    Self-Check, keine Registrierung. Die SQLite-Datei selbst wird hier nicht
    angelegt; das Schema uebernimmt die DB-Schicht.
    """
    db_path = resolve_db_path()
    if _is_dry_run():
        return db_path
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PfadeError(
            "Cannot create parent directory for DB path %s: %s" % (parent, exc)
        ) from exc
    return db_path


# --- Test-Hilfsfunktionen: explizites Environment, replaybar ---


@contextlib.contextmanager
def _env_scope(env: Mapping[str, Optional[str]]) -> Iterator[None]:
    """Setzt os.environ exklusiv auf `env` und stellt danach den Zustand wieder her."""
    old_env = dict(os.environ)
    try:
        os.environ.clear()
        for key, value in env.items():
            if value is None:
                continue
            os.environ[str(key)] = str(value)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def resolve_db_path_with_env(env: dict[str, str]) -> Path:
    """Test-Hilfsfunktion: loest den DB-Pfad mit gegebenem Environment auf."""
    with _env_scope(env):
        return resolve_db_path()


def resolve_data_dir_with_env(env: dict[str, str]) -> Path:
    """Test-Hilfsfunktion: loest den Data-Root mit gegebenem Environment auf."""
    with _env_scope(env):
        return resolve_data_dir()


def ensure_db_with_env(env: Optional[dict[str, str]] = None) -> Path:
    """Test-/Contract-Hilfsfunktion: ensure_db mit explizitem Environment.

    env None  -> das aktuelle os.environ wird unveraendert verwendet.
    env gesetzt -> das Environment wird fuer die Aufloesung exklusiv gesetzt
    (replaybar) und danach vollstaendig wiederhergestellt.

    Dry-Run (F3_DRY_RUN truthy: 1|true|yes|on):
      - F3_DB_PATH ist Pflicht; ohne F3_DB_PATH -> PfadeError (kein Fallback).
      - Alle anderen Pfad-Variablen werden ignoriert.
      - Rueckgabewert ist F3_DB_PATH (tilde-expandiert) als Path.
      - Null Dateisystem-Schreibzugriffe: kein mkdir, keine DB-Init, keine
        Fixture-Erstellung, kein Self-Check, keine Registrierung.
    """
    if env is None:
        return ensure_db()
    with _env_scope(env):
        return ensure_db()


def main() -> int:
    """CLI: gibt die aufgeloesten Pfade als JSON aus (rein lesend)."""
    try:
        paths = resolve_manifest_paths()
    except PfadeError as exc:
        print("f3_pfade: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ClayCode block for GRF/Omega integration
"""
module f3_pfade {
  architecture PfadResolver {
    stateAuthority: resolve_db_path, resolve_data_dir, ensure_db
    path env -> _normalize_dry_run -> _is_dry_run -> resolve_db_path
    path env -> _normalize_dry_run -> _is_dry_run -> resolve_data_dir
    invariant dry_run_fail_closed: F3_DRY_RUN in _TRUTHY union _FALSY else PfadeError
    invariant dry_run_requires_f3_db_path: _is_dry_run() -> F3_DB_PATH != empty else PfadeError
    invariant dry_run_isolated: _is_dry_run() -> ignores(FRANK3_DATA, FRANKENSTEIN3_ROOT, CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, USERPROFILE)
    invariant ensure_db_no_write_in_dry_run: _is_dry_run() -> ensure_db() performs zero fs writes
  }
  invariant dry_run_normalization: _normalize_dry_run(raw) in {"1", "0"} else PfadeError
  fn _normalize_dry_run(raw: Optional[str]) -> str { ... }
  fn _is_dry_run() -> bool { ... }
  hypothesis H_DRY_RUN_FAIL_CLOSED: invalid F3_DRY_RUN raises PfadeError
  promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
}
"""
