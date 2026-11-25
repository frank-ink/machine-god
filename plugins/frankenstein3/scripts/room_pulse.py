#!/usr/bin/env python3
"""PostToolUse: Room heartbeat via the bundled star/star_cli.py (room-pulse-global). Always exit 0."""
import os, runpy, sys
sys.argv = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "_delegate.py"), "room-pulse-global"]
runpy.run_path(sys.argv[0], run_name="__main__")
