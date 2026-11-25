#!/usr/bin/env python3
"""bau.py -- Team 4 (build): 20 agents implement Team 1's work packages as real code in claude-rs branches.
Per WP: coder (<=3 compile-fix loops) -> tester -> 4 integrators across WPs. Strongest NVIDIA models, GRF + ClayCode.
Worktrees ~/void-build/<wp> (branch gridv1/<wp>), shared target dir, ONE cargo at a time (flock + lowprio). NVIDIA free only."""
import concurrent.futures as cf, os, re, subprocess, sys, time
from pathlib import Path

B = Path(__file__).resolve().parent; K = B.parent; W = Path.home() / "void-build"; REPO = Path.home() / "claude-code-rust"
os.environ["TEAM_DIR"] = str(K / "team")
g = {"__file__": str(K / "team" / "team.py"), "__name__": "team_core"}
exec((K / "team" / "team.py").read_text().split("\nHEAD = ")[0], g)
call = g["call"]
STRONG = ["nvidia/nemotron-3-ultra-550b-a55b", "moonshotai/kimi-k3.1-pro", "mistralai/mistral-large-4-1t-a52b",
          "stepfun-ai/step-5-preview", "minimaxai/minimax-m3.1-flash", "nvidia/nemotron-3.5-super-vl-120b-a12b"]
FINAL = (K / "team" / "out" / "final" / "final.md").read_text()
WPS = re.findall(r"(### (WP-[\w.]+):.*?)(?=\n### |\n## |\Z)", FINAL, re.S)
ARCH = FINAL[:9000]
SEAM = (K / "team" / "chunks" / "c09.txt").read_text()[:20000]
_ct = (REPO / "Cargo.toml").read_text()
DEPS = _ct[_ct.index("[dependencies]"):][:2500]
log = lambda s: print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
FMT = ("Think inside GRF, speak ClayCode. Output: (1) a ClayCode block (module, stateAuthority, invariants with ON_VIOLATION, fn F); "
       "(2) every file in full as:\n=== FILE: relative/path ===\n```\n<content>\n```\nPaths relative to the claude-rs repo root. ONLY these paths are accepted: src/gridv1/ (Rust, crate::gridv1, wired automatically; "
       "never edit src/lib.rs or other host files), agent-sdk/src/gridv1/ (TS), docs/gridv1/. Each pass deliver the COMPLETE file set of your WP "
       "(files you omit are deleted). Code must compile with only the crate's existing dependencies (check Cargo.toml in HOST SEAM; no new crates). Mark UNKNOWN honestly.\n\nAVAILABLE CRATES (Cargo.toml, use nothing else; std only otherwise):\n" + DEPS)


RELIABLE = ["nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3.5-super-vl-120b-a12b", "minimaxai/minimax-m3.1-flash"]  # measured: answer under load


def ask(i, prompt):
    first = STRONG[i % len(STRONG)]
    for m in [first] + [x for x in RELIABLE if x != first]:
        txt, meta = call(i, m, prompt)
        log(meta if m == first else f"ERSATZ {m} fuer {first}: {meta}")
        if txt:
            return txt
    return ""


ALLOWED = ("src/gridv1/", "agent-sdk/src/gridv1/", "docs/gridv1/")  # host files stay untouched; wiring is done by check()


def apply(wt, txt, wipe=False):
    files = [(p.strip().strip("`*"), b) for p, b in re.findall(r"^[ \t*#]*=== ?FILE: ?([^\n=]+?) ?===[ \t*]*\n+```[^\n]*\n(.*?)\n```[ \t]*$", txt, re.S | re.M)]
    files = [(p, b) for p, b in files if p.startswith(ALLOWED) and ".." not in Path(p).parts]
    if files and wipe:  # coder delivers the full file set each pass -> no stale files from earlier passes
        for d in ALLOWED[:2]:
            subprocess.run(["rm", "-rf", str(wt / d)])
    for path, body in files:
        f = wt / path; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(body + "\n")
    return len(files)


def wire(d):  # recursive: every .rs file and every subdir under src/gridv1 must be declared, else cargo silently skips it
    for sub in sorted(x for x in d.iterdir() if x.is_dir()):
        if any(sub.rglob("*.rs")):
            wire(sub)
    mf = d / "mod.rs"; mod = mf.read_text() if mf.exists() else ""
    names = [f.stem for f in sorted(d.glob("*.rs")) if f.stem not in ("mod", "lib", "main")] + [x.name for x in sorted(d.iterdir()) if x.is_dir() and (x / "mod.rs").exists()]
    miss = [m for m in names if not re.search(rf"\bmod {m}\b", mod)]
    if miss or not mf.exists():
        mf.write_text(mod.rstrip("\n") + ("\n" if mod.strip() else "") + "".join(f"pub mod {m};\n" for m in miss))


def check(wt):
    gm = wt / "src" / "gridv1"  # wire new Rust files into the crate, else cargo check silently ignores them
    if gm.exists():
        wire(gm)
        lib = wt / "src" / "lib.rs"
        if "mod gridv1" not in lib.read_text():
            lib.write_text(lib.read_text() + "\npub mod gridv1;\n")
    rs = subprocess.run(["git", "-C", str(wt), "status", "--porcelain", "-uall"], capture_output=True, text=True).stdout
    if ".rs" not in rs:
        return 0, "no Rust changes (docs/TS only; TS not type-checked here)"
    cmd = f"flock {W}/cargo.lock lowprio -m 6G -c 400 -- cargo check --message-format short 2>&1 | grep -E 'error|warning: unused' | head -60"
    out = subprocess.run(cmd, shell=True, cwd=wt, capture_output=True, text=True, env={**os.environ, "CARGO_TARGET_DIR": str(W / "target")}).stdout
    n = len(re.findall(r": error(\[E\d+\])?:", out)) or len(re.findall(r"^error", out, re.M))
    return n, out or "cargo check: clean"


def wp_pipeline(i, wp_text, wp):
    wt = W / wp.lower()
    if not wt.exists():
        subprocess.run(["git", "-C", str(REPO), "worktree", "add", "-q", str(wt), "-b", f"gridv1/{wp.lower()}"], check=True)
    rep = [f"# {wp}\n"]
    code = ask(i, f"You are CODER for {wp} in build team 4 (20 agents). {FMT}\n\nARCHITECTURE (Team 1 final, excerpt):\n{ARCH}\n\nHOST SEAM:\n{SEAM}\n\nYOUR WORK PACKAGE:\n{wp_text}")
    for loop in range(4):
        n = apply(wt, code, wipe=True)
        (B / "out").mkdir(exist_ok=True); (B / "out" / f"{wp}_pass{loop}.raw.md").write_text(code)
        errs, out = (1, "NO FILES: your output contained no '=== FILE: path ===' block followed by a fenced code block. Deliver the files.") if n == 0 else check(wt)
        rep.append(f"## coder pass {loop}: {n} files, {errs} errors\n```\n{out[:3000]}\n```\n")
        log(f"{wp} pass {loop}: {n} files, {errs} errors")
        if errs == 0 or loop == 3:
            break
        code = ask(i, f"You are CODER for {wp}. Fix the compile errors. {FMT}\n\nERRORS:\n{out}\n\nYOUR PREVIOUS OUTPUT:\n{code[:30000]}")
    test = ask(i + 7, f"You are TESTER for {wp} in build team 4. Write tests (Rust #[cfg(test)] or docs/gridv1/{wp}-acceptance.md for non-code WPs) for the acceptance criteria. {FMT}\n\nWORK PACKAGE:\n{wp_text}\n\nCODER OUTPUT:\n{code[:30000]}")
    apply(wt, test); errs, out = check(wt)
    rep.append(f"## tester: {errs} errors\n```\n{out[:3000]}\n```\n")
    subprocess.run(f"git add -A && git -c user.name='VOID team4' -c user.email=team4@void.local commit -qm '{wp}: team4 build (errors={errs})' || true", shell=True, cwd=wt)
    (B / "out").mkdir(exist_ok=True); (B / "out" / f"{wp}.md").write_text("".join(rep) + f"\n## coder output\n{code}\n\n## tester output\n{test}\n")
    return wp, errs


if __name__ == "__main__":
    sel = set(sys.argv[1:]) or {w for _, w in WPS}  # bau.py [WP ...]: rebuild only these, keep finished WPs
    log(f"{len(WPS)} work packages, building {sorted(sel)}")
    todo = [(i, wt) for i, wt in enumerate(WPS) if wt[1] in sel]
    with cf.ThreadPoolExecutor(8) as ex:
        log(f"build results: {list(ex.map(lambda a: wp_pipeline(a[0], *a[1]), todo))}")
    res = [(w, None) for _, w in WPS if (B / "out" / f"{w}.md").exists()]
    allout = "\n\n".join((B / "out" / f"{wp}.md").read_text()[:6000] for wp, _ in res)
    for j in range(4):  # 4 integrators, each on 2 WPs + the whole picture
        mine = [w for k, (w, _) in enumerate(res) if k % 4 == j]
        rv = ask(j + 3, f"You are INTEGRATOR {j+1}/4 of build team 4, responsible for {mine}. Check interface consistency against the architecture and the other WPs, list contract breaks (ClayCode invariants), and give concrete fixes. Results per WP:\n{allout}\n\nARCHITECTURE:\n{ARCH}")
        (B / "out" / f"integrator_{j+1}.md").write_text(rv)
    log("team 4 done")
