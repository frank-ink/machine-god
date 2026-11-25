"""5-dev ClayCode team inside the GRF prefix. Each role has its own NVIDIA key; all talk on a ClayCode-only board.

python -m team.clayteam run --task TEXT --workdir DIR [--rounds 3] [--model M] [--oracle FILE]
Accept only if waechter says rule verdict = "accept" AND the team's pytest exits 0 AND, with --oracle,
the preregistered oracle tests (written apart from the team) exit 0. Oracle failures are reported by test name only.
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

from team import clay_core as C

ORDER = ["architekt", "forscher", "bauer", "pruefer", "waechter"]
CARDS = {
    "architekt": "role architekt: decompose the task into needles (interfaces) and invariants.",
    "forscher": "role forscher: add facts, constraints and edge cases the others missed, as rules and invariants.",
    "bauer": "role bauer: implement. If the runner reports failed_N, decide from the spec whether the code or the test "
             "is wrong and fix that one. If the runner reports team_tests_wrong, the code is right: fix only your test file. "
             "must_fix_N: a judge ruled that team test required by the spec: fix the CODE. quarantined_N: that test was "
             "ruled outside the spec and removed: do not write it again. After your ClayCode, append exactly one ```python block (module artifact.py) "
             "and one ```python block whose first line is # test (pytest file importing from artifact).",
    "pruefer": "role pruefer: check the runner's test facts and the spec; state defects as rules.",
    "waechter": "role waechter: reply with at most 4 lines. The LAST line must be exactly rule verdict = \"accept\" "
                "or rule verdict = \"reject\". accept only if the runner reports pytest_rc = 0, oracle_rc = 0 when oracle_rc is reported, and the spec is met.",
}
VERDICT = re.compile(r'rule\s+verdict\s*=\s*"(accept|reject)"')
RULING = re.compile(r'rule\s+ruling\s*=\s*"(valid|invalid)"')
RICHTER_CARD = ("role richter (judge): decide whether ONE unit test is required by the task spec. The code under test "
                "already passes an independent oracle. Reply with exactly one line: rule ruling = \"valid\" if the spec "
                "requires the tested behavior, or rule ruling = \"invalid\" if the test asserts behavior the spec "
                "contradicts or does not state (for example exact error messages, extra input types, impossible data).")


DEFAULT_FALLBACKS = ("nvidia/nemotron-3.5-super-vl-120b-a12b", "minimaxai/minimax-m3.1-flash")  # bench: valid ClayCode


def chat_chain(chat, key, msgs, models):
    """Route hierarchy: try each model in order; a ChatError (timeout, 429, 5xx) moves to the next one.
    Returns (text, usage, ms, model_used, tried). Raises the last ChatError when every path fails."""
    tried, last, total = [], None, 0
    for m in dict.fromkeys(models):  # ordered, no duplicates
        tried.append(m)
        try:
            text, usage, ms = chat(key, msgs, model=m)
            return text, usage, (ms or 0) + total, m, tried
        except C.ChatError as e:
            last = e
    raise last or C.ChatError("no model in route")


def _test_name(fail: str) -> str:
    return fail.split(" - ")[0].split("::")[-1].strip()


def _remove_tests(src: str, names: set) -> str:
    """Drop test functions (module level or inside classes) by name; everything else stays."""
    tree = ast.parse(src)

    def keep(n):
        return not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names)
    tree.body = [n for n in tree.body if keep(n)]
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            n.body = [m for m in n.body if keep(m)] or [ast.Pass()]
    return ast.unparse(tree) + "\n"


def _test_source(src: str, name: str) -> str:
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(src, n) or ""
    return ""


def system_prompt(role: str) -> str:
    if C.HARNESS not in sys.path:
        sys.path.insert(0, C.HARNESS)
    from understanding import grf_prefix
    return (f"{grf_prefix.PREFIX}\n{CARDS[role]}\n{C.GRAMMAR_HINT}\n"
            "Add only NEW statements; never repeat statements already on the board. "
            "Only role bauer may write python.")


def board_tail(board: list[dict], n: int = 12) -> str:
    return "\n".join(f"# {e['role']} r{e['round']}\n{e['clay']}" for e in board[-n:] if e.get("parse_ok"))


def run_pytest(cand: str, files: list[str] | None = None) -> tuple[int, int, int, list[str]]:
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", *(files or [])], cwd=cand,
                           capture_output=True, text=True, timeout=120)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        return 0, 0, 124, ["pytest timeout after 120 s"]
    num = lambda w: int(m.group(1)) if (m := re.search(r"(\d+) " + w, out)) else 0
    fails = [ln[7:].strip() for ln in out.splitlines() if ln.startswith("FAILED ")][:3]
    return num("passed"), num("failed") + num("error"), rc, fails


def _clay_str(x: str) -> str:
    return '"' + re.sub(r'["\\\n]', "'", x)[:220] + '"'


def _adjudicate(cand, test_src, fails, task, chat, key, model, rnd, post, roles):
    """Judge each failing team test against the spec. Invalid -> removed from the team file (kept in quarantine.py);
    valid or no ruling -> stays and is reported to bauer as must_fix. Returns (rc, n_failed, fails, facts)."""
    invalid, facts = set(), []
    for i, f in enumerate(fails):
        name = _test_name(f)
        msgs = [{"role": "system", "content": f"{_prefix()}\n{RICHTER_CARD}\n{C.GRAMMAR_HINT}"},
                {"role": "user", "content": f"task spec: {task}\n\ntest:\n{_test_source(test_src, name)[:2500]}\n\n"
                                            f"failure: {f[:300]}"}]
        try:
            text, usage, ms = chat(key, msgs, model=model)
        except C.ChatError as e:
            text, usage, ms = "", {}, None
        m = RULING.search(text or "")
        ruling = m.group(1) if m else "none"
        post({"ts": time.time(), "round": rnd, "role": "richter", "model": model, "key_name": roles["pruefer"],
              "key_hash8": C.key_fingerprint(key), "parse_ok": bool(m), "repaired": False, "salvaged": False,
              "clay": m.group(0) if m else "", "error": "" if m else "no ruling", "raw_head": "" if m else (text or "")[:300],
              "has_artifact": False, "latency_ms": ms, "usage": usage, "test": name, "ruling": ruling})
        if ruling == "invalid":
            invalid.add(name)
            facts.append(f"rule quarantined_{i + 1} = {_clay_str(name)}")
        else:
            facts.append(f"rule must_fix_{i + 1} = {_clay_str(name)}")
    if invalid:
        with open(os.path.join(cand, "quarantine.py"), "w") as q:
            q.write("\n\n".join(_test_source(test_src, n) for n in sorted(invalid)) + "\n")
        open(os.path.join(cand, "test_artifact.py"), "w").write(_remove_tests(test_src, invalid))
    _, nf, rc, left = run_pytest(cand, ["test_artifact.py"])
    facts += [f"rule failed_{i + 1} = {_clay_str(f)}" for i, f in enumerate(left)]
    return rc, nf, left, [x for x in facts if C.validate(x)[0]]


def _prefix() -> str:
    if C.HARNESS not in sys.path:
        sys.path.insert(0, C.HARNESS)
    from understanding import grf_prefix
    return grf_prefix.PREFIX


def run(task: str, workdir: str, rounds: int = 3, model: str = C.DEFAULT_MODEL, chat=None, keys=None,
        oracle: str | None = None, keyset: str = "A", role_models: dict | None = None, adjudicate: bool = False,
        fallbacks: dict | None = None) -> dict:
    chat = chat or C.chat
    roles = C.KEYSETS[keyset]
    role_models = role_models or {}
    base_model = model
    oracle_src = open(oracle, encoding="utf-8").read() if oracle else None
    workdir = os.path.realpath(workdir)
    os.makedirs(workdir, exist_ok=True)
    keys = keys or {r: C.load_key(n) for r, n in roles.items()}
    bpath = os.path.join(workdir, "board.jsonl")
    board: list[dict] = []

    def post(entry: dict) -> None:
        board.append(entry)
        with open(bpath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    for rnd in range(1, rounds + 1):
        for role in ORDER:
            model = role_models.get(role, base_model)
            route = [model, *((fallbacks or {}).get(role) or DEFAULT_FALLBACKS)]
            msgs = [{"role": "system", "content": system_prompt(role)},
                    {"role": "user", "content": f"task: {task}\nboard (ClayCode only):\n{board_tail(board)}"}]
            try:
                text, usage, ms, model, tried = chat_chain(chat, keys[role], msgs, route)
            except C.ChatError as e:  # every path failed; one role must not kill the run
                post({"ts": time.time(), "round": rnd, "role": role, "model": route[-1], "key_name": roles[role],
                      "key_hash8": C.key_fingerprint(keys[role]), "parse_ok": False, "repaired": False,
                      "salvaged": False, "clay": "", "error": "chat: " + str(e)[:160], "raw_head": "",
                      "has_artifact": False, "latency_ms": None, "usage": {}})
                continue
            clay, py = C.split_reply(text)
            ok, err = C.validate(clay)
            repaired = False
            if not ok:
                msgs += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"parser error: {err}\nresend as valid ClayCode only."}]
                try:
                    text, usage2, ms2, _, _ = chat_chain(chat, keys[role], msgs, [model] + route)
                except C.ChatError:
                    usage2, ms2 = {}, 0
                clay, py2 = C.split_reply(text)
                ok, err = C.validate(clay)
                py, ms, repaired = (py2 or py), ms + ms2, True
            salvaged = False
            if not ok:
                sal = C.salvage(text)
                if sal:
                    clay, ok, salvaged = sal, True, True
            post({"ts": time.time(), "round": rnd, "role": role, "model": model, "key_name": roles[role],
                  "key_hash8": C.key_fingerprint(keys[role]), "parse_ok": ok, "repaired": repaired, "salvaged": salvaged,
                  "clay": clay if ok else "", "error": "" if ok else err[:200], "raw_head": "" if ok else text[:300],
                  "has_artifact": role == "bauer" and len(py) >= 2, "latency_ms": ms, "usage": usage,
                  "fallback_from": tried[:-1]})
            if role == "bauer" and len(py) >= 2:
                test = next((b for b in py if b.lstrip().startswith("# test")), py[-1])
                mod = next(b for b in py if b is not test)
                cand = os.path.join(workdir, "candidate")
                shutil.rmtree(cand, ignore_errors=True)
                os.makedirs(cand)
                open(os.path.join(cand, "artifact.py"), "w").write(mod)
                open(os.path.join(cand, "test_artifact.py"), "w").write(test)
                np_, nf, rc, fails = run_pytest(cand, ["test_artifact.py"])
                facts = [f"rule tests_passed = {np_}", f"rule tests_failed = {nf}", f"rule pytest_rc = {rc}"]
                facts += [f"rule failed_{i + 1} = {_clay_str(f)}" for i, f in enumerate(fails)]
                orc = None
                if oracle_src is not None:  # oracle: names only, so the team cannot copy its assertions
                    open(os.path.join(cand, "test_oracle.py"), "w").write(oracle_src)
                    op, of, orc, ofails = run_pytest(cand, ["test_oracle.py"])
                    facts += [f"rule oracle_passed = {op}", f"rule oracle_failed = {of}", f"rule oracle_rc = {orc}"]
                    facts += [f"rule oracle_fail_{i + 1} = {_clay_str(f.split(' - ')[0])}" for i, f in enumerate(ofails)]
                    if orc == 0 and rc != 0 and adjudicate and fails:
                        rc, nf, fails, rfacts = _adjudicate(cand, test, fails, task, chat, keys["pruefer"],
                                                            role_models.get("richter", base_model), rnd, post, roles)
                        np_, _, _, _ = run_pytest(cand, ["test_artifact.py"])
                        facts = [f"rule tests_passed = {np_}", f"rule tests_failed = {nf}", f"rule pytest_rc = {rc}"]
                        facts += [f"rule oracle_passed = {op}", f"rule oracle_failed = {of}", f"rule oracle_rc = {orc}"]
                        facts += rfacts
                    elif orc == 0 and rc != 0:
                        facts.append('rule team_tests_wrong = "oracle passes: fix the failing team tests, not the code"')
                facts = [x for x in facts if C.validate(x)[0]]
                post({"ts": time.time(), "round": rnd, "role": "runner", "parse_ok": True,
                      "clay": "\n".join(facts),
                      "pytest_rc": rc, "oracle_rc": orc})
            if role == "waechter" and not VERDICT.search(clay if ok else ""):
                try:
                    t3, _, ms3, _, _ = chat_chain(chat, keys[role], msgs + [{"role": "assistant", "content": text}, {"role": "user", "content":
                                  'verdict missing. Reply with exactly one line: rule verdict = "accept" or rule verdict = "reject"'}],
                                      [model] + route)
                except C.ChatError:
                    t3, ms3 = "", 0
                v = C.salvage(t3)
                if VERDICT.search(v):
                    post({"ts": time.time(), "round": rnd, "role": "waechter", "model": model,
                          "key_name": roles[role], "key_hash8": C.key_fingerprint(keys[role]), "parse_ok": True,
                          "repaired": True, "salvaged": True, "clay": VERDICT.search(v).group(0), "error": "",
                          "raw_head": "", "has_artifact": False, "latency_ms": ms3, "usage": {}})
                    clay, ok = VERDICT.search(v).group(0), True
            if role == "waechter":
                m = VERDICT.search(clay if ok else "")
                last = next((e for e in reversed(board) if e["role"] == "runner"), None)
                if (m and m.group(1) == "accept" and last and last["pytest_rc"] == 0
                        and (oracle_src is None or last.get("oracle_rc") == 0)):
                    dst = os.path.join(workdir, "accepted", f"round_{rnd}")
                    shutil.copytree(os.path.join(workdir, "candidate"), dst, dirs_exist_ok=True)
                    return {"accepted": True, "round": rnd, "path": dst, "entries": len(board), "oracle": oracle_src is not None}
    return {"accepted": False, "round": rounds, "path": None, "entries": len(board), "oracle": oracle_src is not None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--task", required=True)
    r.add_argument("--workdir", required=True)
    r.add_argument("--rounds", type=int, default=3)
    r.add_argument("--model", default=C.DEFAULT_MODEL)
    r.add_argument("--oracle", default=None, help="preregistered pytest file, written apart from the team")
    r.add_argument("--keyset", default="A", choices=sorted(C.KEYSETS))
    r.add_argument("--role-model", action="append", default=[], help="role=model, repeatable")
    r.add_argument("--route", choices=["fixed", "titan"], default="fixed",
                   help="titan: TITAN-MX picks a model per role from the omnipool and measured evidence")
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--adjudicate", action="store_true",
                   help="with --oracle: a richter model rules failing team tests valid (bauer must fix) or invalid (quarantined)")
    a = ap.parse_args(argv)
    rm = dict(x.split("=", 1) for x in a.role_model)
    if set(rm) - set(ORDER) - {"richter"}:
        ap.error(f"unknown role in --role-model: {sorted(set(rm) - set(ORDER) - {'richter'})}")
    fb = None
    if a.route == "titan":
        from team import titan_router as R
        runs_dir = os.path.dirname(os.path.realpath(a.workdir))
        os.makedirs(a.workdir, exist_ok=True)
        auto, dec = R.route(runs_dir, C.load_key(C.KEYSETS[a.keyset]["architekt"]), seed=a.seed,
                            bench_files=sorted(glob.glob(os.path.join(runs_dir, "..", "logs", "bench*.out"))),
                            log_path=os.path.join(a.workdir, "titan_route.jsonl"))
        rm = {**auto, **rm}  # explicit --role-model wins
        fb = R.fallbacks(dec)  # route hierarchy: next-ranked models per role from the same decision table
        print(json.dumps({"titan_pick": rm, "explore_role": dec["explore_role"], "pool": dec["pool"]}), flush=True)
    res = run(a.task, a.workdir, a.rounds, a.model, oracle=a.oracle, keyset=a.keyset, role_models=rm,
              adjudicate=a.adjudicate, fallbacks=fb)
    if a.route == "titan":
        res["pool_reports"] = R.feedback(os.path.join(os.path.realpath(a.workdir), "board.jsonl"))
    print(json.dumps(res))
    return 0 if res["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
