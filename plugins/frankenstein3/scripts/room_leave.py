#!/usr/bin/env python3
"""SessionEnd: Room line set to free via the bundled star/star_cli.py (room-leave-global). Always exit 0."""
import os, runpy, sys
sys.argv = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "_delegate.py"), "room-leave-global"]
runpy.run_path(sys.argv[0], run_name="__main__")
