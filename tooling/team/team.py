#!/usr/bin/env python3
"""team.py PHASE -- 10-model NVIDIA-free team (chief + 9 voices), GRF/ClayCode frame.
PHASE: zerlegen | entwurf | review | final. NVIDIA NIM only, no other/paid tier. Keys never printed.
Files: team.json (members), chunks/cNN.txt, out/<phase>/*.md"""
import json, os, sys, time, urllib.request, concurrent.futures as cf
from pathlib import Path

sys.path.insert(0, "~/last-resort")
import llm  # noqa: E402

D = Path(os.environ.get("TEAM_DIR") or Path(__file__).resolve().parent)
TASKS = json.loads((D / "tasks.json").read_text()) if (D / "tasks.json").exists() else {}
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
KEYS = next(k for label, _u, _m, k in llm._tiers() if label == "nvidia")
CFG = json.loads((D / "team.json").read_text())
PRE = Path("~/omega-agent-preamble-grf-claycode.md").read_text()
GOAL = (D / "ziel.md").read_text()
DIST = (D / "entityos_destillat.md").read_text()


def call(i, model, prompt, max_tokens=16000):
    # streamed: long generations keep the socket alive; timeout applies per read, total capped
    for attempt in range(2):
        # attempt 2: larger budget + explicit short-reasoning instruction (reasoning models ate the budget)
        sysmsg = PRE if attempt == 0 else PRE + "\n\nKeep your internal reasoning SHORT (max ~2500 tokens), then write the complete answer."
        body = json.dumps({"model": model, "max_tokens": max_tokens if attempt == 0 else 32000, "temperature": 0.25, "stream": True,
                           "messages": [{"role": "system", "content": sysmsg},
                                        {"role": "user", "content": prompt}]}).encode()
        key = KEYS[(i + attempt) % len(KEYS)]
        t = time.time()
        try:
            req = urllib.request.Request(URL, body, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            parts, n, fin = [], 0, None
            with urllib.request.urlopen(req, timeout=600) as r:
                for line in r:
                    if time.time() - t > 2400:
                        raise TimeoutError("total cap 2400s")
                    line = line.strip()
                    if not line.startswith(b"data:") or line == b"data: [DONE]":
                        continue
                    ch = json.loads(line[5:]).get("choices") or [{}]
                    c = (ch[0].get("delta") or {}).get("content")
                    fin = ch[0].get("finish_reason") or fin
                    if c:
                        parts.append(c)
                    n += 1
            txt = "".join(parts)
            if txt.strip():
                return txt, f"{model} {time.time()-t:.0f}s chunks={n}"
            err = f"empty content after {n} chunks finish={fin}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__} {str(e)[:100]}"
        print(f"[team] {model} attempt {attempt}: {err}", file=sys.stderr)
    return None, f"{model} FAILED {err}"


def run(jobs, phase):
    out = D / "out" / phase
    out.mkdir(parents=True, exist_ok=True)
    def one(j):
        name, model, prompt = j
        f = out / f"{name}.md"
        if f.exists() and f.stat().st_size > 200:
            return name, "cached"
        txt, meta = call(hash(name) % 7, model, prompt)
        if not txt:  # substitute voice, visibly marked
            for fb in [x for x in ("nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3.5-super-vl-120b-a12b") if x != model]:
                txt, meta2 = call(3, fb, prompt)
                meta = f"ERSATZ {fb} fuer {model} ({meta}) -> {meta2}"
                if txt:
                    break
        if txt:
            f.write_text(f"<!-- {meta} -->\n{txt}")
        return name, meta
    with cf.ThreadPoolExecutor(5) as ex:
        for name, meta in ex.map(one, jobs):
            print(f"[{phase}] {name}: {meta}", flush=True)
    return {p.stem: p.read_text() for p in sorted(out.glob("*.md"))}


def read(phase):
    return {p.stem: p.read_text() for p in sorted((D / "out" / phase).glob("*.md"))}


HEAD = "You are member '{n}' of a 10-model engineering team (chief: {c}). Every member has a voice; dissent is recorded, never hidden.\n\nGOAL (Gabriel, verbatim + context):\n{g}\n\nENTITYOS DISTILLATE (verified extract of the source docs):\n{d}\n\n"
chief = next(m for m in CFG if m.get("chief"))
T3B = Path("~/entityos-kern/team3/out/buendel_latest.md")
ext = lambda: ("\n\nEXTERNAL TEAM 3 BUNDLE (leader persona 'Gabriel', mathematician; holds GRF as 99% correct). Weigh it as one strong voice; its claims enter as HYPOTHESIS, your evidence rules stay:\n" + T3B.read_text()[:12000] + "\n\n") if T3B.exists() else ""
head = lambda m: HEAD.format(n=m["name"], c=chief["name"], g=GOAL, d=DIST) + ext()
phase = sys.argv[1]

if phase == "zerlegen":
    jobs = [(m["chunk"], m["model"], head(m) + TASKS.get("zerlegen", "TASK: Dissect the code below. Output a ClayCode surface block + compound records: (1) state R_t it owns/reads (tables, files, in-memory), (2) transition F with exact function names, (3) invariants actually enforced in code (cite function/line), (4) inputs E_t and side effects (DB writes, sockets, subprocesses, network), (5) what is coupling/feedback vs. what is load-bearing core, (6) what must change so this becomes a non-bypassable kernel-level substrate inside the claude-rs host (no optional feedback path). Mark UNKNOWN where the code does not show it. No invention.") + "\n\n" + (D / "chunks" / f"{m['chunk']}.txt").read_text()) for m in CFG]
    run(jobs, "zerlegen")
elif phase == "entwurf":
    rep = "\n\n".join(f"### REPORT {k}\n{v}" for k, v in read("zerlegen").items())
    run([("entwurf", chief["model"], head(chief) + TASKS.get("entwurf", "TASK (chief): From the 10 dissection reports below, write the architecture of ONE fused unit EntityOS+GRID10 as the kernel-level substrate of claude-rs (Rust TUI -> Bun bridge -> Agent SDK). Required: ASCII diagram; ClayCode module with stateAuthority, path, invariants, fn F; the exact seam(s) in claude-rs (file/function); why there is no bypass/feedback-only path (fail-closed semantics); what is ported (Rust/TS) vs. reused (Python) and why; numbered work packages each with acceptance test + evidence form; risks and UNKNOWNs. Be concrete, cite report findings.") + "\n\n" + rep, )], "entwurf")
elif phase == "review":
    ent = read("entwurf")["entwurf"]
    jobs = [(m["name"], m["model"], head(m) + f"Your own dissection report:\n{read('zerlegen').get(m['chunk'], 'MISSING')}\n\nCHIEF'S DRAFT:\n{ent}\n\nTASK: Review the draft from your code knowledge. Output exactly: VOTE: APPROVE | APPROVE_WITH_CHANGES | OBJECT; then numbered concrete findings (what is wrong/missing, evidence from your chunk, proposed amendment). Max 900 words.") for m in CFG]
    run(jobs, "review")
elif phase == "final":
    ent = read("entwurf")["entwurf"]
    rv = "\n\n".join(f"### REVIEW {k}\n{v}" for k, v in read("review").items())
    run([("final", chief["model"], head(chief) + f"YOUR DRAFT:\n{ent}\n\nTEAM REVIEWS:\n{rv}\n\nTASK (chief): Produce the final architecture + work-package plan. Integrate accepted amendments. Add a table 'Votes & dissent' (member, vote, key objection, accepted/rejected + reason). Rejected objections stay visible. Keep all required sections of the draft.")], "final")
