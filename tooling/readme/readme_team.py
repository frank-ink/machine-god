#!/usr/bin/env python3
"""readme_team.py [loop] -- 2 agents own ~/VOID/README.md: writer (mistral-large-4) + editor (nemotron-3.5-super-vl).
Writer drafts from repo facts -> editor scores (checklist) + fixes -> writer revises; until score >= 9.5 or 4 iterations.
Link/path check is done by this script, not by the models. loop: re-run when the repo changed (every 30 min). NVIDIA free only."""
import json, os, re, subprocess, sys, time
from pathlib import Path

H = Path(__file__).resolve().parent
K, R = H.parent, Path.home() / "VOID"
os.environ["TEAM_DIR"] = str(K / "team")
g = {"__file__": str(K / "team" / "team.py"), "__name__": "team_core"}
exec((K / "team" / "team.py").read_text().split("\nHEAD = ")[0], g)
call = g["call"]
WRITER, EDITOR = "mistralai/mistral-large-4-1t-a52b", "nvidia/nemotron-3.5-super-vl-120b-a12b"
log = lambda s: print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
CHECK = ("1 one-sentence what-is-this at top; 2 honest status table (only facts from STATUS); 3 architecture ASCII diagram of the 3 teams + merge -> GRIDv1; "
         "4 what GRIDv1 is (EntityOS+GRID10 fused kernel substrate of the claude-rs fork, not a feedback add-on) and what 'kernel level' honestly means; "
         "5 repo map where every path exists; 6 how the teams work (GRF thinking, ClayCode, chief+voices, dissent visible, NVIDIA free models only); "
         "7 how to reproduce (tools/ commands); 8 evidence policy (MEASURED/HYPOTHESIS/UNKNOWN, persona output = HYPOTHESIS); 9 no hype, no consciousness claims, no secrets/host names; "
         "10 polished English, scannable, no filler")


def facts():
    tree = subprocess.run(["git", "-C", str(R), "ls-files"], capture_output=True, text=True).stdout
    st = {d: {p: len(list((K / d / "out" / p).glob("*.md"))) for p in ("zerlegen", "entwurf", "review", "final", "v_entwurf", "v_review", "v_final")
              if (K / d / "out" / p).exists()} for d in ("team", "team2", "vereinigung")}
    st["team3_rounds"] = len(list((K / "team3" / "out").glob("r*_buendel.md")))
    pick = lambda p, n: (p.read_text()[:n] if p.exists() else "not yet")
    return (f"STATUS (measured {time.strftime('%Y-%m-%d %H:%M')}): {json.dumps(st)}\n\nREPO FILES:\n{tree}\n\n"
            f"TEAM 1 GOAL:\n{pick(K/'team'/'ziel.md', 4000)}\n\nTEAM 1 FINAL (excerpt):\n{pick(K/'team'/'out'/'final'/'final.md', 9000)}\n\n"
            f"TEAM 2 GOAL:\n{pick(K/'team2'/'ziel.md', 2500)}\n\nTEAM 2 newest (excerpt):\n{pick(K/'team2'/'out'/'final'/'final.md', 6000) if (K/'team2'/'out'/'final'/'final.md').exists() else pick(K/'team2'/'out'/'entwurf'/'entwurf.md', 6000)}\n\n"
            f"TEAM 3 PERSONA HEAD:\n{pick(K/'team3'/'persona_kopf.md', 3000)}\n\nTEAM 3 latest bundle (excerpt):\n{pick(K/'team3'/'out'/'buendel_latest.md', 5000)}\n\n"
            f"GRIDv1 (merge) final:\n{pick(K/'vereinigung'/'out'/'v_final'/'GRIDv1.md', 8000)}")


def bad_links(md):
    out = []
    for link in re.findall(r"\]\(([^)#\s]+)", md) + re.findall(r"`((?:teams|tools|sources|vereinigung)/[^`\s]*)`", md):
        if not link.startswith("http") and not (R / link).exists():
            out.append(link)
    return sorted(set(out))


def once():
    F = facts()
    prev = (R / "README.md").read_text() if (R / "README.md").exists() else "none"
    draft, meta = call(1, WRITER, f"You are README AGENT 1 (writer) for the private repo frank-ink/VOID. Write the complete README.md.\nCHECKLIST:\n{CHECK}\n\nPREVIOUS README:\n{prev[:12000]}\n\nFACTS (only source of truth):\n{F}\n\nOutput only the Markdown.")
    log(f"draft: {meta}")
    for it in range(1, 5):
        if not draft:
            return
        bl = bad_links(draft)
        rev, meta = call(2, EDITOR, f"You are README AGENT 2 (editor). Score this README 0-10 against the checklist and the facts. First line exactly 'SCORE: <n>'. Then numbered concrete fixes (quote the wrong text, give the replacement).\nCHECKLIST:\n{CHECK}\n\nLINKS/PATHS THAT DO NOT EXIST (measured): {bl or 'none'}\n\nFACTS:\n{F}\n\nREADME:\n{draft}")
        log(f"edit {it}: {meta}")
        m = re.search(r"SCORE:\s*([\d.]+)", rev or "")
        score = float(m.group(1)) if m else 0.0
        log(f"iteration {it}: score {score}, bad links {len(bl)}")
        if score >= 9.5 and not bl:
            break
        new, meta = call(1, WRITER, f"Revise the README applying every fix. Output only the full Markdown.\n\nEDITOR REVIEW:\n{rev}\n\nNONEXISTENT PATHS: {bl}\n\nFACTS:\n{F}\n\nREADME:\n{draft}")
        log(f"revise {it}: {meta}")
        draft = new or draft
    draft = re.sub(r"^```(?:markdown|md)?\n|\n```\s*$", "", draft.strip())
    (H / "README.md").write_text(draft + "\n")
    (H / "last_review.md").write_text(rev or "")
    log(f"README written ({len(draft)} chars, last score {score}, bad links {bad_links(draft)})")


if __name__ == "__main__":
    once()
    while len(sys.argv) > 1 and sys.argv[1] == "loop" and subprocess.run(["pgrep", "-f", "entityos-kern/pipeline.sh|team3.py"]).returncode == 0:
        head = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        time.sleep(1800)
        if subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout != head:
            once()
