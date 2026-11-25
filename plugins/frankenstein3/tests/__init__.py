"""FranKenstein 3 test package and owner of the shared ``sys.path`` bootstrap.

The bootstrap used to live in ``conftest.py``.  ``conftest.py`` is loaded by
pytest only, so the unittest runner saw a different ``sys.path`` and the two
same-named ``status`` modules (``tests/status.py`` and
``scripts/star/status.py``) could resolve differently.  Owning the bootstrap
here makes it part of the package import, which both runners perform.

Test *discovery* is still not identical between the runners: pytest imports
the test modules as ``tests.test_*`` while ``python -m unittest discover``
imports them as top-level ``test_*`` modules.  Only the import *setup* is
shared.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: Directory of this test package.
TESTS_DIR = Path(__file__).resolve().parent
#: Plugin root (parent of the test package).
PLUGIN_ROOT = TESTS_DIR.parent
#: Production scripts shipped with the plugin.
STAR_DIR = PLUGIN_ROOT / "scripts" / "star"

# Insertion order matters: the last entry ends up first in ``sys.path``.
# ``STAR_DIR`` therefore precedes ``TESTS_DIR``, exactly as the former
# ``conftest.py`` bootstrap did.
for _path in (PLUGIN_ROOT, TESTS_DIR, STAR_DIR):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
