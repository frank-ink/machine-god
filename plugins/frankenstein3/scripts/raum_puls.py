#!/usr/bin/env python3
"""PostToolUse: Raum-Herzschlag ueber das gebuendelte star/stern.py (raum-puls-global). Immer exit 0."""
import os, runpy, sys
sys.argv = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "_delegat.py"), "raum-puls-global"]
runpy.run_path(sys.argv[0], run_name="__main__")
