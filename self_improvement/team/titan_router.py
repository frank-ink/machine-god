"""TITAN-MX model router for the ClayCode team: picks one model per role from the omnipool, from measured evidence.

route() consults, in order:
  1. served   live /v1/models of the NIM endpoint; non-chat models (embed, guard, safety, ...) are dropped.
  2. pool     PoolBrain (omegacv1 harness): models it would block (would_allow False, retired, quarantined) are dropped;
              its availability estimate becomes a weak prior. Fail-open: no pool brain -> prior 0.5 for every model.
  3. evidence every board.jsonl under runs/ (per role: clean ClayCode 1, repaired 0.5, salvaged 0.25, error 0;
              bauer code: oracle_rc 0 -> 1, else pytest_rc 0 -> 1 when no oracle, else 0.25) plus bench lines at half weight.
  4. prior    empirical Bayes: an untried model starts at the role's measured team average (strength PRIOR_K) nudged
              by the pool's availability, so a model with two easy bench lines cannot outrank a proven model on optimism.
  5. decide   exploit roles take the best lower bound (posterior mean - 0.5 sd - latency penalty), so an untried model
              never displaces a proven one by optimism; exactly ONE role per run explores by Thompson sampling, so a bad
              untried model can cost at most one seat. pruefer avoids bauer's model when an alternative is within MARGIN
              (independent checking).
Every decision is logged with the numbers behind it. feedback() reports a finished board into PoolBrain.report
(task_kind "code", src "clayteam"), so the pool learns from team work too. No key value is ever logged.
"""
from __future__ import annotations

import glob
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.request

from team import clay_core as C

ROLES = ("architekt", "forscher", "bauer", "pruefer", "waechter")
NON_CHAT = re.compile(r"embed|safety|guard|clip|detector|translate|retriev|calibration|gliner|starcoder|cosmos", re.I)
LAT_W = 0.05      # utility lost per minute of median latency (capped at 5 minutes)
MARGIN = 0.15     # pruefer may take the runner-up if it is at most this far behind bauer's model
BENCH_W = 0.25    # a bench line is one easy prompt, not a team turn with a board
N_MIN = 3.0       # an exploit seat needs at least this much evidence; less-tested models get the explore seat
PRIOR_K = 4.0     # empirical-Bayes prior strength: an untried model starts at the role's measured average
BENCH_TIMEOUT_MS = 600_000
UNKNOWN_LAT_S = 60.0
_BENCH = re.compile(r"^(\S+/\S+)\s+(?:ERROR\b.*|.*?\bok=(True|False).*?\bms=(\d+))")
_LINES = re.compile(r"\b(?:lines|salvage_lines)=(\d+)")


def served_models(key: str, _get=None) -> list[str]:
    def get():
        req = urllib.request.Request(C.NIM_URL.replace("/chat/completions", "/models"),
                                     headers={"Authorization": "Bearer " + key})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    return sorted(m["id"] for m in (_get or get)()["data"] if not NON_CHAT.search(m["id"]))


def reward(e: dict) -> float | None:
    if e.get("role") == "runner":
        return None
    if str(e.get("error", "")).startswith("chat:"):
        return 0.0
    if not e.get("parse_ok"):
        return 0.0
    if e.get("salvaged"):
        return 0.25
    return 0.5 if e.get("repaired") else 1.0


def code_reward(runner: dict) -> float:
    if runner.get("oracle_rc") is not None:
        return 1.0 if runner["oracle_rc"] == 0 else 0.25
    return 1.0 if runner.get("pytest_rc") == 0 else 0.25


def parse_bench(text: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        m = _BENCH.match(ln.strip())
        if not m:
            continue
        if m.group(2) is None:  # ERROR line: timeout or HTTP failure
            out.append({"model": m.group(1), "reward": 0.0, "latency_ms": BENCH_TIMEOUT_MS})
            continue
        lines = _LINES.search(ln)
        r = 1.0 if m.group(2) == "True" else (0.25 if lines and int(lines.group(1)) > 0 else 0.0)
        out.append({"model": m.group(1), "reward": r, "latency_ms": int(m.group(3))})
    return out


def evidence(board_paths, bench=()) -> dict:
    """(dim, model) -> [successes, failures, latencies_ms]; dim = role, 'bauer_code', or '*' (bench, all roles)."""
    ev: dict = {}

    def add(dim, model, r, w=1.0, lat=None):
        s = ev.setdefault((dim, model), [0.0, 0.0, []])
        s[0] += w * r
        s[1] += w * (1 - r)
        if lat:
            s[2].append(lat)
    for p in board_paths:
        last_bauer = None
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("role") == "runner":
                    if last_bauer:
                        add("bauer_code", last_bauer, code_reward(e))
                    continue
                r, m = reward(e), e.get("model")
                if r is None or not m:
                    continue
                if e.get("role") == "bauer":
                    last_bauer = m
                add(e.get("role"), m, r, lat=e.get("latency_ms"))
    for b in bench:
        add("*", b["model"], b["reward"], BENCH_W, b.get("latency_ms"))
    return ev


def role_mean(ev, dim) -> float:
    s = sum(v[0] for (d, _), v in ev.items() if d == dim)
    n = s + sum(v[1] for (d, _), v in ev.items() if d == dim)
    return s / n if n else 0.5


def _beta(ev, dims, model, avail, rm=0.5):
    rm = min(max(rm, 0.05), 0.95)  # keep both Beta parameters > 0
    a, b, lats = PRIOR_K * rm + 0.5 * avail + 0.25, PRIOR_K * (1 - rm) + 0.5 * (1 - avail) + 0.25, []
    for d in dims:
        s = ev.get((d, model))
        if s:
            a, b, lats = a + s[0], b + s[1], lats + s[2]
    lat = statistics.median(lats) / 1000 if lats else UNKNOWN_LAT_S
    return a, b, lat


def _lcb(a, b):
    n = a + b
    return a / n - 0.5 * (a * b / (n * n * (n + 1))) ** 0.5


def choose(ev: dict, cands: dict, seed=None, explore_role=None):
    """cands: model -> availability prior in [0, 1]. Returns (pick, explore_role, table)."""
    if not cands:
        raise ValueError("no candidate models")
    rng = random.Random(seed)
    explore_role = explore_role or rng.choice(ROLES)
    pick, table = {}, {}
    rms = {d: role_mean(ev, d) for d in ROLES + ("bauer_code",)}
    for role in ROLES:
        rows = []
        for m, avail in sorted(cands.items()):
            a, b, lat = _beta(ev, (role, "*"), m, avail, rms[role])
            lo, smp = _lcb(a, b), rng.betavariate(a, b)
            n = a + b - PRIOR_K - 1.0
            if role == "bauer":
                ca, cb, _ = _beta(ev, ("bauer_code",), m, avail, rms["bauer_code"])
                lo, smp = 0.3 * lo + 0.7 * _lcb(ca, cb), 0.3 * smp + 0.7 * rng.betavariate(ca, cb)
                n += ca + cb - PRIOR_K - 1.0
            pen = LAT_W * min(lat / 60, 5)
            rows.append({"model": m, "lcb": round(lo, 4), "sample": round(smp, 4), "lat_s": round(lat, 1),
                         "n": round(n, 2), "u": round((smp if role == explore_role else lo) - pen, 4)})
        rows.sort(key=lambda r: (-r["u"], r["model"]))
        if role != explore_role and any(r["n"] >= N_MIN for r in rows):
            rows = [r for r in rows if r["n"] >= N_MIN] + [r for r in rows if r["n"] < N_MIN]
        if role == "pruefer" and rows[0]["model"] == pick.get("bauer"):
            alt = next((r for r in rows[1:] if rows[0]["u"] - r["u"] <= MARGIN), None)
            if alt:  # an independent checker is worth a small expected loss
                rows.remove(alt)
                rows.insert(0, alt)
        pick[role] = rows[0]["model"]
        table[role] = rows[:5]
    return pick, explore_role, table


def _poolbrain():
    if C.HARNESS not in sys.path:
        sys.path.insert(0, C.HARNESS)
    from poolbrain.brain import PoolBrain
    return PoolBrain()


def pool_gate(models, factory=_poolbrain) -> tuple[dict, str]:
    try:
        pb = factory()
    except Exception as ex:  # fail-open: the team still runs on board evidence alone
        return {m: 0.5 for m in models}, f"poolbrain unavailable ({type(ex).__name__})"
    try:
        rank = {x["model"]: float(x.get("avail", 0.5)) for x in
                pb.ranking("code", ["nvidia"], include_blocked=True, include_uncertified=True)}
    except Exception:
        rank = {}
    out = {}
    for m in models:
        try:
            d = pb.can_call("nvidia", m, "code")
        except Exception:
            d = {}
        if d.get("would_allow", d.get("allow", True)) is False or d.get("health") in ("retired", "quarantined"):
            continue
        out[m] = min(max(rank.get(m, 0.5), 0.0), 1.0)
    return out, "poolbrain"


def route(runs_dir: str, key: str, seed=None, bench_files=(), log_path=None, _served=None, _pool=None) -> tuple[dict, dict]:
    models = _served if _served is not None else served_models(key)
    cands, src = (_pool(models) if _pool else pool_gate(models))
    bench = [b for f in bench_files if os.path.exists(f) for b in parse_bench(open(f, encoding="utf-8").read())]
    boards = sorted(glob.glob(os.path.join(runs_dir, "*", "board.jsonl")))
    pick, explore, table = choose(evidence(boards, bench), cands, seed)
    dec = {"ts": time.time(), "pick": pick, "explore_role": explore, "pool": src, "n_served": len(models),
           "n_candidates": len(cands), "n_boards": len(boards), "n_bench": len(bench), "seed": seed, "table": table}
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dec) + "\n")
    return pick, dec


def fallbacks(dec: dict, k: int = 2) -> dict:
    """Route hierarchy: per role the next k models of the decision table, proven ones first (same order as choose)."""
    return {role: [r["model"] for r in rows if r["model"] != dec["pick"].get(role)][:k]
            for role, rows in dec.get("table", {}).items()}


def feedback(board_path: str, factory=_poolbrain) -> int:
    try:
        pb = factory()
    except Exception:
        return 0
    n = 0
    with open(board_path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            for fm in e.get("fallback_from") or ():  # a model the chain skipped after a ChatError
                try:
                    pb.report("nvidia", fm, e.get("key_name", ""), "code", ok=False, err_class="chat_error",
                              latency_ms=0.0, src="clayteam")
                    n += 1
                except Exception:
                    pass
            r = reward(e)
            if r is None or not e.get("model"):
                continue
            err = "" if r >= 0.5 else ("timeout" if "Timeout" in str(e.get("error", "")) else "bad_output")
            try:
                pb.report("nvidia", e["model"], e.get("key_name", ""), "code", ok=r >= 0.5, err_class=err,
                          latency_ms=float(e.get("latency_ms") or 0), src="clayteam")
                n += 1
            except Exception:
                pass
    return n
