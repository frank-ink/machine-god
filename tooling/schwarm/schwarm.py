#!/usr/bin/env python3
"""schwarm.py -- Team 5: 50 NVIDIA agents on GRIDv1. Planner splits GRIDv1 + cosign reservations + build state into 47 atomic tasks;
3 independent cosigners (models that did NOT write GRIDv1). Code tasks: own worktree ~/void-build/swarm/<id> (branch gridv1/swarm-<id>,
based on the WP branch if one exists), cargo-check loop from bau.py (one cargo at a time). Max 12 parallel: NVIDIA capacity is the
bottleneck, not tokens. GRF thinking, ClayCode speech. NVIDIA free only."""
import concurrent.futures as cf, json, re, subprocess
from pathlib import Path

S = Path(__file__).resolve().parent; K = S.parent; B = K / "bau"; O = S / "out"
g = {"__file__": str(B / "bau.py"), "__name__": "bau_core"}
exec((B / "bau.py").read_text().split('\nif __name__ == "__main__":')[0], g)
ask, call, check, apply, FMT, W, REPO, log = (g[k] for k in ("ask", "call", "check", "apply", "FMT", "W", "REPO", "log"))
V = K / "vereinigung" / "out" / "v_final"
GRIDV1 = (V / "GRIDv1.md").read_text(); COSIGN = (V / "cosign_chef-kimi-k3.1-pro.md").read_text()
BASE = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
COSIGNERS = ["mistralai/mistral-large-4-1t-a52b", "nvidia/nemotron-3.5-super-vl-120b-a12b", "minimaxai/minimax-m3.1-flash"]


def build_state():
    return "\n".join(f"{d.name}: {git('log', '-1', '--format=%s', f'gridv1/{d.name}').stdout.strip()}" for d in sorted(W.glob("wp-*")))


def plan():
    f = S / "tasks.json"
    if f.exists():
        return json.loads(f.read_text())
    for i in (0, 1, 2):
        txt = ask(i, "You are the PLANNER of swarm team 5 (50 NVIDIA agents). Think in GRF, speak ClayCode. Split the remaining GRIDv1 work into "
                  "exactly 47 atomic, independent tasks, each doable by ONE agent in ONE answer. Cover: every cosign reservation, every undefined "
                  "function/contract, the build errors, missing tests per WP, verifying GRIDv1 claims against the host seam, docs. Output ONLY a JSON "
                  'array: [{"id":"s01","kind":"code|spec|test|review","wp":"WP-x or none","title":"...","brief":"2-4 sentences"}]'
                  f"\n\nCOSIGN RESERVATIONS:\n{COSIGN}\n\nBUILD STATE (branch: last commit):\n{build_state()}\n\nGRIDv1:\n{GRIDV1[:40000]}")
        try:
            tasks = json.loads(re.search(r"\[.*\]", txt, re.S).group(0))[:47]
            break
        except (AttributeError, ValueError):
            log(f"planner {i}: no valid JSON, retry")
    for k, t in enumerate(tasks):
        t["id"] = f"s{k + 1:02d}"
    f.write_text(json.dumps(tasks, indent=1, ensure_ascii=False)); return tasks


def cosign(j, model):
    txt, meta = call(j, model, "You are an INDEPENDENT co-signer of GRIDv1 (you did not write it). Think in GRF, speak ClayCode. First line exactly "
                     "'COSIGN: YES|YES_WITH_RESERVATIONS|NO'. Then numbered findings: contradictions, undefined contracts, claims that are not "
                     f"MEASURED, kernel-level honesty. Be concrete, quote the text.\n\nGRIDv1:\n{GRIDV1}")
    log(f"cosign {model}: {meta}"); (O / f"cosign_{model.split('/')[1]}.md").write_text(f"<!-- {meta} -->\n{txt}")
    return f"cosign-{model.split('/')[1]}", "cosign", 0, 0 if txt else 1


def work(i, t):
    tid, wp = t["id"], str(t.get("wp", "none"))
    wt = W / "swarm" / tid
    if not wt.exists():
        base = f"gridv1/{wp.lower()}" if git("rev-parse", "--verify", "-q", f"refs/heads/gridv1/{wp.lower()}").returncode == 0 else BASE
        git("worktree", "add", "-q", str(wt), "-b", f"gridv1/swarm-{tid}", base)
    head = (f"You are agent {tid} of swarm team 5 (50 NVIDIA agents), kind={t.get('kind')}. {FMT}\nAdditive work: deliver the full content of every "
            f"file you add or change; never delete others' files. Specs/reviews go to docs/gridv1/swarm/{tid}-<name>.md.")
    out = ask(i, f"{head}\n\nTASK {tid}: {t['title']}\n{t['brief']}\n\nCOSIGN RESERVATIONS:\n{COSIGN[:5000]}\n\nGRIDv1 (excerpt):\n{GRIDV1[:24000]}")
    rep = [f"# {tid}: {t['title']}\nkind={t.get('kind')} wp={wp}\n"]
    for loop in range(3):
        n = apply(wt, out)
        errs, msg = (1, "NO FILES: deliver '=== FILE: path ===' blocks with fenced code.") if n == 0 else check(wt)
        rep.append(f"## pass {loop}: {n} files, {errs} errors\n```\n{msg[:2500]}\n```\n"); log(f"{tid} pass {loop}: {n} files, {errs} errors")
        if errs == 0 or loop == 2:
            break
        out = ask(i, f"{head}\nFix this. ERRORS:\n{msg}\n\nTASK {tid}: {t['title']}\n{t['brief']}\n\nYOUR PREVIOUS OUTPUT:\n{out[:30000]}")
    subprocess.run(f"git add -A && git -c user.name='VOID team5' -c user.email=team5@void.local commit -qm '{tid}: swarm (errors={errs})' || true", shell=True, cwd=wt)
    (O / f"{tid}.md").write_text("".join(rep) + f"\n## output\n{out}\n")
    return tid, t.get("kind"), n, errs


if __name__ == "__main__":
    O.mkdir(exist_ok=True); (W / "swarm").mkdir(exist_ok=True)
    tasks = plan(); log(f"{len(tasks)} tasks + {len(COSIGNERS)} cosigners = {len(tasks) + len(COSIGNERS)} agents")
    with cf.ThreadPoolExecutor(12) as ex:
        futs = [ex.submit(cosign, j, m) for j, m in enumerate(COSIGNERS)] + [ex.submit(work, i, t) for i, t in enumerate(tasks)]
        res = [f.result() for f in futs]
    (O / "INDEX.md").write_text("| id | kind | files | errors |\n|---|---|---|---|\n" + "".join(f"| {a} | {b} | {c} | {d} |\n" for a, b, c, d in res))
    log(f"swarm done: {sum(1 for r in res if r[3] == 0)}/{len(res)} without errors")
