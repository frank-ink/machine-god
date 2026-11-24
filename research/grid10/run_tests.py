#!/usr/bin/env python3
"""Runs every test_*.py of this folder as a script (they are self-running, not pytest style) and reports exit codes.
Usage: python3 run_tests.py   (exit 0 only if all files exit 0; data paths resolve to ./fixtures)"""
import pathlib
import subprocess
import sys

here = pathlib.Path(__file__).resolve().parent
bad = 0
for t in sorted(here.glob("test_*.py")):
    r = subprocess.run([sys.executable, str(t)], cwd=here, capture_output=True, text=True, timeout=300)
    last = (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or [""])[-1][:80]
    print(f"{t.name:32} rc={r.returncode}  {last}")
    bad += r.returncode != 0
print("ALLE GRUEN" if not bad else f"{bad} Datei(en) mit Fehlern")
sys.exit(1 if bad else 0)
