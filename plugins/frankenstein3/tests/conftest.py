"""pytest configuration for FranKenstein 3 tests.

The ``sys.path`` bootstrap lives in ``tests/__init__.py`` so that pytest and
unittest share the same import setup.  Test *discovery* is not identical
between the two runners: pytest imports the modules as ``tests.test_*``,
``python -m unittest discover`` imports them as top-level ``test_*``.
"""
