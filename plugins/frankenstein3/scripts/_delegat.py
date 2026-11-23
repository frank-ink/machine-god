#!/usr/bin/env python3
"""Gemeinsamer Starter: ruft das gebuendelte star/stern.py mit einem Unterbefehl auf (stdin durchgereicht). Immer exit 0."""
import os, subprocess, sys
try:
    data = sys.stdin.read()
    st = os.path.join(os.path.dirname(os.path.abspath(__file__)), "star", "stern.py")
    if os.path.isfile(st) and len(sys.argv) > 1:
        r = subprocess.run([sys.executable, st] + sys.argv[1:], input=data, text=True, capture_output=True, timeout=4)
        if r.stdout.strip():
            sys.stdout.write(r.stdout)
except Exception:
    pass
sys.exit(0)
