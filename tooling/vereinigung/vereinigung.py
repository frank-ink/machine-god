#!/usr/bin/env python3
"""vereinigung.py PHASE -- Team 1 (GRID) + Team 2 (research) become one 20-voice team -> GRIDv1.
PHASE: v_entwurf | v_review | v_final. Reuses call()/run() of ../team/team.py (NVIDIA only)."""
import json, os, sys
from pathlib import Path

V = Path(__file__).resolve().parent
K = V.parent
os.environ["TEAM_DIR"] = str(V)
g = {"__file__": str(K / "team" / "team.py"), "__name__": "team_core"}
exec((K / "team" / "team.py").read_text().split("\nHEAD = ")[0], g)  # imports, call, run, read
run, read = g["run"], g["read"]

T1 = json.loads((K / "team" / "team.json").read_text())
T2 = json.loads((K / "team2" / "team.json").read_text())
C1 = next(m for m in T1 if m.get("chief"))
C2 = next(m for m in T2 if m.get("chief"))
F1 = (K / "team" / "out" / "final" / "final.md").read_text()
F2 = (K / "team2" / "out" / "final" / "final.md").read_text()
GOAL = (V / "ziel.md").read_text()
T3B = K / "team3" / "out" / "buendel_latest.md"
T3 = (f"=== EXTERNAL TEAM 3 BUNDLE (leader persona 'Gabriel', holds GRF as 99% correct; one strong voice, claims = HYPOTHESIS) ===\n{T3B.read_text()[:12000]}\n\n") if T3B.exists() else ""
BASE = f"GOAL:\n{GOAL}\n\n=== TEAM 1 (GRID/kernel) FINAL ===\n{F1}\n\n=== TEAM 2 (research) FINAL ===\n{F2}\n\n" + T3


def own_report(team_dir, m):
    f = K / team_dir / "out" / "zerlegen" / f"{m['chunk']}.md"
    return f.read_text() if f.exists() else "MISSING"


phase = sys.argv[1]
if phase == "v_entwurf":
    task = ("TASK: You are chief of the merged 20-voice team (Team 1 GRID/kernel + Team 2 research). Write GRIDv1: "
            "the ONE fused EntityOS+GRID10 kernel substrate of claude-rs that satisfies the research core. Required: ASCII architecture; "
            "ClayCode module GRIDv1 (stateAuthority, path, invariants with ON_VIOLATION, fn F, hypotheses, promotion ladder); exact claude-rs seams; "
            "fail-closed semantics (why no bypass, no feedback-only path); research requirements -> design element trace table; "
            "work packages WP1..n each with acceptance test + evidence form; what stays HYPOTHESIS; risks/UNKNOWNs.")
    run([("entwurf_" + C1["name"], C1["model"], BASE + task), ("entwurf_" + C2["name"], C2["model"], BASE + task)], "v_entwurf")
elif phase == "v_review":
    ds = read("v_entwurf")
    drafts = "\n\n".join(f"=== DRAFT {k} ===\n{v}" for k, v in ds.items())
    jobs = []
    for tdir, team, label in (("team", T1, "T1"), ("team2", T2, "T2")):
        for m in team:
            jobs.append((f"{label}_{m['name']}", m["model"],
                         f"You are '{m['name']}' ({label}) in the merged 20-voice GRIDv1 team. Every voice counts; dissent is recorded.\n\n"
                         f"GOAL:\n{GOAL}\n\n{T3}YOUR OWN EARLIER REPORT:\n{own_report(tdir, m)}\n\n{drafts}\n\n"
                         "TASK: Output exactly: PREFERRED_BASE: <draft name>; VOTE: APPROVE | APPROVE_WITH_CHANGES | OBJECT; "
                         "then numbered findings (problem, evidence from your report, amendment). Max 800 words. ClayCode for amendments."))
    run(jobs, "v_review")
elif phase == "v_final":
    ds = read("v_entwurf")
    rv = "\n\n".join(f"### {k}\n{v}" for k, v in read("v_review").items())
    drafts = "\n\n".join(f"=== DRAFT {k} ===\n{v}" for k, v in ds.items())
    run([("GRIDv1", C1["model"], BASE + drafts + "\n\n=== 20 REVIEWS ===\n" + rv +
          "\n\nTASK (chief): Produce GRIDv1 final. Base = the draft most voices preferred (count them, show the count). Integrate accepted amendments. "
          "Keep every required section. Add table 'Votes & dissent' for all 20 voices (voice, base, vote, key objection, accepted/rejected + reason).")], "v_final")
    fin = read("v_final")["GRIDv1"]
    run([("cosign_" + C2["name"], C2["model"], f"GOAL:\n{GOAL}\n\nGRIDv1 FINAL:\n{fin}\n\nTASK (co-chief): Output COSIGN: YES | YES_WITH_RESERVATIONS | NO, then numbered reservations. They will be appended verbatim.")], "v_final")
