#!/usr/bin/env python3
"""Common starter: calls the bundled star/star_cli.py with a subcommand (stdin passed through). Always exit 0."""
import os, subprocess, sys
try:
    data = sys.stdin.read()
    st = os.path.join(os.path.dirname(os.path.abspath(__file__)), "star", "star_cli.py")
    if os.path.isfile(st) and len(sys.argv) > 1:
        r = subprocess.run([sys.executable, st] + sys.argv[1:], input=data, text=True, capture_output=True, timeout=4)
        if r.stdout.strip():
            sys.stdout.write(r.stdout)
except Exception:
    pass
sys.exit(0)
