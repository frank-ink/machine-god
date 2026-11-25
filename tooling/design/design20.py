#!/usr/bin/env python3
"""design20.py -- Machine God DESIGN TEAM: 20 free designer models (ranked by bench.py) improve src/ui/ on branch gridv1/design.
Reuses zero40's machinery (plan -> parallel coders in worktrees -> quick gate -> serial merge -> full gate + ratchet -> reviewer) by
patching its source, so gates stay identical. Team rotates: each round PAR designers, next round the next PAR. Stop: touch STOP here."""
import json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE.parent / "zero" / "zero40.py").read_text()
os.environ.setdefault("ZERO40_PAR", "10"); os.environ.setdefault("ZERO40_HOURS", "24")
SUBS = [
    ('WT = W / "zero"; SW = W / "zero-swarm"', 'WT = W / "design"; SW = W / "design-swarm"'),
    ('ALLOWED = ("src/zero/", "agent-sdk/src/zero/", "zero/", "plugins/frankenstein3/", "docs/zero/")', 'ALLOWED = ("src/ui/",)'),
    ('br = f"zero/{tid}"', 'br = f"design/{tid}"'),
    ('"zero/r*"', '"design/r*"'),
    ("a 40 h autonomous loop fusing Agent Zero and FranKenstein 3.0 into claude-rs",
     "the Machine God DESIGN TEAM (20 free designer models) making the ratatui TUI ultra modern, polished, subtle, slightly sacral and "
     "above all convenient; animations are pure functions of a tick"),
    ("Priorities: fix reviewer findings; then raise measured ", "Priorities: fix reviewer findings; then the next design rule not yet visible in the code; keep measured "),
    ("make the bundled plugin portable; implement the next missing piece of the goal list.", "polish first what users see most (input, messages, popups)."),
    ('"--sid", "zero40",', '"--sid", "design20",'),
    ("zero40 round", "design20 round"), ("# zero40 status", "# design20 status"),
]
for a, b in SUBS:
    assert a in SRC, f"zero40 changed, patch missing: {a[:60]}"
    SRC = SRC.replace(a, b)
head, main = SRC.split('\nif __name__ == "__main__":')
g = {"__file__": str(HERE / "design20.py"), "__name__": "design20"}
exec(compile(head, "zero40-head", "exec"), g)

sys.path.insert(0, str(HERE)); import bench  # noqa: E402  (call() with vault keys, provider endpoints)
TEAM = [(r["provider"], r["model"]) for r in json.loads((HERE / "bench.json").read_text()) if r["compiles"]][:20]
assert len(TEAM) >= 5, f"too few designers compiled in bench: {len(TEAM)}"
OFF = [0]; _plan = g["plan"]


def ask(i, prompt):  # designer i of this round; fallback: zero40's FAST NVIDIA models
    prov, model = TEAM[(i + OFF[0]) % len(TEAM)]
    txt = bench.call(prov, model, [{"role": "user", "content": prompt}], 12000)
    g["log"](f"designer {prov}/{model}: {len(txt)} chars")
    if txt:
        return txt
    for m in g["FAST"]:
        txt, meta = g["call"](i, m, prompt); g["log"](f"ERSATZ {m}: {meta}")
        if txt:
            return txt
    return ""


def plan(rnd, *a):
    OFF[0] = (rnd - 1) * g["PAR"]
    return _plan(rnd, *a)


g["ask"], g["plan"] = ask, plan
g["log"](f"design20 team ({len(TEAM)}): " + ", ".join(m for _, m in TEAM))
exec(compile("if True:" + main, "zero40-main", "exec"), g)
