#!/usr/bin/env python3
"""Design benchmark: which FREE models design best for Machine God (ratatui TUI)? Same task for all; score = compiles (cargo check
in a scratch crate, ratatui 0.30) * 50 + judge score 0-50 (two judges, mean). Keys only via ~/last-resort/llm.py (vault), never printed.
Out: ~/entityos-kern/design/bench.json (ranked) + bench/<model>.rs"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path.home() / "last-resort"))
import llm  # noqa: E402
D = Path(__file__).parent; B = D / "bench"; B.mkdir(exist_ok=True); CR = D / "crate"
EP = {"nvidia": ("https://integrate.api.nvidia.com/v1/chat/completions", "NVIDIA"), "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ"),
      "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER"), "zai": ("https://api.z.ai/api/paas/v4/chat/completions", "GLM5_FLASH")}
CAND = [("nvidia", m) for m in ("z-ai/glm-5.3-flash", "nvidia/nemotron-3-ultra-550b-a55b", "minimaxai/minimax-m3.1-flash", "nvidia/nemotron-3.5-super-vl-120b-a12b",
         "mistralai/mistral-large-4-1t-a52b", "moonshotai/kimi-k3.1-pro", "google/gemma-4-31b-it", "stepfun-ai/step-5-preview",
         "nvidia/nemotron-3.5-lightning-30b-a3b", "poolside/laguna-xs-2.1", "meta/muse-glimmer-30b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")] \
     + [("groq", m) for m in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b")] \
     + [("openrouter", m) for m in ("google/gemma-4-26b-a4b-it:free", "baidu/ernie-5.5-flash-preview:free", "inclusionai/ling-3.2-flash:free",
         "dots-studio/dots-3-note-preview:free", "recursive/flint-v1.0:free", "particle-ai/particle-1:free", "google/gemma-4-31b-it:free",
         "nvidia/nemotron-3-ultra-550b-a55b:free")]
TASK = ("You design Machine God, a Rust terminal app (ratatui 0.30, crossterm). Style: ultra modern, polished, subtle, slightly sacral "
        "(turquoise #00CED1 to blue #2878FF, thin glyphs like ◈ ✠ only as accents), above all CONVENIENT.\nWrite ONE self-contained Rust module "
        "with `pub fn render_popup(frame: &mut ratatui::Frame, area: ratatui::layout::Rect, title: &str, lines: &[&str], tick: u64)`: a centered "
        "popup with ROUNDED borders, generous padding, a subtle fade-in/glow animation driven by `tick` (no sleeping, pure function of tick), "
        "a dim footer hint 'Esc to close'. Use only ratatui APIs. Then 3 short bullet points: why this is convenient and calm.\n"
        "Output: one ```rust block, then the bullets.")
KEYS = llm._keys()


STATS = {}
import random, threading
LOCK = threading.Lock(); CARGO = threading.Lock()
HARD = 300      # seconds per single HTTP call, whole call (urllib timeout alone is per socket op: 3 attempts x 10 keys x 420 s hung 5 h)
BUDGET = 1500   # seconds per model for the whole pipeline (generate, compile, repair, judge)


def call(prov, model, msgs, max_tokens=14000, timeout=HARD, dl=None):
    """Returns text ('' on failure). At most 3 key tries, each capped by min(timeout, time left until dl); 429 -> next key; reasons counted in STATS."""
    url, pre = EP[prov]; names = sorted(k for k in KEYS if k.startswith(pre)); random.shuffle(names)
    for name in names[:3]:
        left = (dl - time.time()) if dl else timeout
        if left < 20:
            STATS[(model, "budget")] = 1; return ""
        body = json.dumps({"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.4}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEYS[name],
                                                 "User-Agent": "machine-god-bench/1.0"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=min(timeout, left))); ch = d["choices"][0]
            txt = ch["message"].get("content") or ""
            if txt.strip():
                return txt
            STATS[(model, "empty:" + str(ch.get("finish_reason")))] = 1
        except urllib.error.HTTPError as e:
            STATS[(model, f"http{e.code}")] = 1
            if e.code in (401, 403, 404):
                return ""
            if e.code == 429:
                time.sleep(5)
        except Exception as e:
            STATS[(model, type(e).__name__)] = 1
    return ""


def compiles(code):
    """cargo check in the shared scratch crate: serialized (one lock), memory-guarded, lowprio (rule: heavy jobs only via lowprio after mem-guard)."""
    with CARGO:
        for _ in range(30):
            if subprocess.run(["mem-guard"], capture_output=True).returncode != 75:
                break
            time.sleep(60)
        (CR / "src/lib.rs").write_text(code)
        try:
            r = subprocess.run(["lowprio", "-m", "6G", "-c", "150", "--", "cargo", "check", "--offline", "-q"], cwd=CR, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return False, "cargo timeout"
        return r.returncode == 0, r.stderr[-400:]


def score_of(txt):
    t = txt[-400:]
    m = re.findall(r"(\d+(?:\.\d+)?)\s*/\s*50", t) or re.findall(r"\d+(?:\.\d+)?", t)
    return min(50.0, float(m[-1])) if m else None


def judge(code, notes, dl):
    p = ("Score this terminal UI design 0-50 for: subtle modern polish, convenience (clear hint, calm, no clutter), animation tastefulness, "
         "code clarity. Think briefly, then end your answer with the final score as the LAST number, nothing after it.\n\n" + code[:6000] + "\n\n" + notes[:800])
    vals = []
    for prov, m in (("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"), ("nvidia", "moonshotai/kimi-k3.1-pro")):
        v = score_of(call(prov, m, [{"role": "user", "content": p}], 8000, dl=dl))
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else 0.0, len(vals)


def repair(prov, model, code, err, dl):
    for _ in range(2):
        out = call(prov, model, [{"role": "user", "content": TASK}, {"role": "assistant", "content": "```rust\n" + code + "```"},
                                 {"role": "user", "content": "cargo check (ratatui 0.30.2) failed. Fix it, keep the design. Same output format. Errors:\n" + err[-1800:]}], dl=dl)
        m = re.search(r"```(?:rust|rs)?\s*\n(.*?)```", out, re.S)
        if not m:
            return code, False, err
        code = m.group(1); ok, err = compiles(code)
        if ok:
            return code, True, ""
    return code, False, err


RES = []


def record(r):
    """result of ONE model goes to bench.log + bench.json right now (ranked), not at the end"""
    with LOCK:
        RES.append(r); RES.sort(key=lambda x: -x["score"])
        (D / "bench.json").write_text(json.dumps(RES, indent=1))
        with open(D / "bench.log", "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {r['score']:5.1f} {'OK ' if r['compiles'] else 'BAD'} {r['sec']:6}s judges={r.get('judges', 0)} {r['provider']}/{r['model']} {r['err'][:80]!r}\n")


def run(c):
    prov, model = c; t = time.time(); dl = t + BUDGET
    try:
        out = call(prov, model, [{"role": "user", "content": TASK}], dl=dl)
        m = re.search(r"```(?:rust|rs)?\s*\n(.*?)```", out, re.S)
        code = m.group(1) if m else ""
        ok, err = compiles(code) if code else (False, "no code" if out else "no answer")
        if code and not ok:
            code, ok, err = repair(prov, model, code, err, dl)
        notes = out[m.end():] if m else out
        j, nj = judge(code, notes, time.time() + 600) if code else (0.0, 0)
        (B / (re.sub(r"[^a-z0-9]+", "_", f"{prov}_{model}".lower()) + ".rs")).write_text(code)
        record({"provider": prov, "model": model, "score": round((50 if ok else 0) + j, 1), "compiles": ok, "judges": nj,
                "sec": round(time.time() - t, 1), "err": "" if ok else err[-200:]})
    except Exception as e:  # one model must never take the run down
        record({"provider": prov, "model": model, "score": 0.0, "compiles": False, "judges": 0, "sec": round(time.time() - t, 1), "err": f"exc {type(e).__name__}: {e}"[:200]})


if __name__ == "__main__":
    (D / "bench.log").write_text(f"{time.strftime('%H:%M:%S')} start v3: {len(CAND)} candidates, call cap {HARD}s, model budget {BUDGET}s\n")
    ex = ThreadPoolExecutor(4)
    futs = [ex.submit(run, c) for c in CAND]
    t0 = time.time()
    for f in futs:
        try:
            f.result(timeout=max(1, 3 * 3600 - (time.time() - t0)))
        except Exception:
            pass
    done = {(r["provider"], r["model"]) for r in RES}
    for c in CAND:
        if c not in done:
            record({"provider": c[0], "model": c[1], "score": 0.0, "compiles": False, "judges": 0, "sec": 0, "err": "global timeout"})
    with open(D / "bench.log", "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} done. reasons: {sorted(STATS)}\n")
    ex.shutdown(wait=False, cancel_futures=True)
    os._exit(0)
