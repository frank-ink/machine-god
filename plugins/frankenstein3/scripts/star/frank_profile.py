"""frank_profile.py -- single reader of the user profile (data/user_profile.json). stdlib only, never raises.
Absent file: first_run.pending present -> generic (fresh install, name unknown yet); else legacy values (generic)."""
import json, os
from pathlib import Path

_STAR = Path(__file__).resolve().parent
_PROF = _STAR / "data" / "user_profile.json"
_PEND = _STAR / "data" / "first_run.pending"
_LEGACY = {"name": "friend", "user_id": os.environ.get("USER", "user"), "lang": "en", "mode": "fresh"}


def load():
    try:
        d = json.loads(_PROF.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("name") and d.get("user_id"):
            return d
    except Exception:
        pass
    if _PEND.exists():
        return {"name": "friend", "user_id": os.environ.get("USER", "user"), "lang": "en", "mode": "fresh"}
    return dict(_LEGACY)


def name():
    return load()["name"]


def user_id():
    return load()["user_id"]


def first_run_text():
    """Deterministic one-shot instruction for SessionStart on a fresh install; '' when not due. Marks itself done (once only)."""
    try:
        if not _PEND.exists() or _PROF.exists():
            return ""
        done = _STAR / "data" / "first_run.asked"
        if done.exists():
            return ""
        done.write_text("1")
        return ("FIRST RUN: this is a fresh Frankenstein install and the user's name is not known yet. In your first reply, greet in English, "
                "ask the user's name and preferred language (en/de), then run `frank-profile set --name <name> [--lang xx]` and continue normally.")
    except Exception:
        return ""
