#!/usr/bin/env python3
"""SessionEnd: Raum-Zeile auf frei ueber das gebuendelte star/stern.py (raum-verlassen-global). Immer exit 0."""
import os, runpy, sys
sys.argv = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "_delegat.py"), "raum-verlassen-global"]
runpy.run_path(sys.argv[0], run_name="__main__")
