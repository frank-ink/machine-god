#!/usr/bin/env python3
"""Tool-use data for the Machine God 0.8B (web scraping), free pool only. Each item -> 2 training rows:
(1) user -> assistant emits exactly one tool line, (2) ... + result -> assistant answers ONLY from the result.
Out: daten/ok_tools.jsonl (same messages format as daten_gen.py, appended to ok.jsonl by pod_nach_daten.sh)."""
import json, random, re, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "last-resort"))
from freechain import chat  # noqa: E402  free-only chain (no paid tier)

D = Path(__file__).parent / "daten"
SYSTEM = "Du bist Machine God, die lokale Stimme dieser Anwendung. / You are Machine God, the local voice of this app."
CALL = re.compile(r"^⟦tool: (fetch https://\S+|links https://\S+|table https://\S+|search .{3,120}|wiki)⟧$")
ARTEN = ["fetch (read a page and summarise)", "links (list links of a page)", "table (extract a table, e.g. prices)",
         "search (find something on the web)", "wiki (show the free-token wiki)"]


def batch(lang, art):
    p = (f"Write 5 training items for a small assistant 'Machine God' that uses ONE web tool per request. Tool kind: {art}.\n"
         f"Language of user and answer: {'German' if lang == 'de' else 'English'}.\n"
         "Tool line syntax, exactly one line: ⟦tool: fetch https://...⟧ | ⟦tool: links https://...⟧ | ⟦tool: table https://...⟧ "
         "| ⟦tool: search QUERY⟧ | ⟦tool: wiki⟧\n"
         'Output ONLY JSON lines: {"user": "...", "call": "<tool line>", "result": "<short realistic tool output, max 80 words>", '
         '"answer": "<reply using ONLY facts from result, max 70 words>"}. Use example.com-style or well-known public URLs.')
    out = chat([{"role": "user", "content": p}], max_tokens=2500, temperature=0.8)
    if isinstance(out, tuple):
        out = next((x for x in out if isinstance(x, str) and "{" in x), "")
    return out if isinstance(out, str) else ""


def gut(d):
    if not all(isinstance(d.get(k), str) and d[k].strip() for k in ("user", "call", "result", "answer")):
        return False
    if not CALL.match(d["call"].strip()):
        return False
    src = d["result"] + d["user"] + d["call"]
    return all(u in src for u in re.findall(r"https?://\S+", d["answer"]))   # no URL the result did not contain


def main(n=int(sys.argv[1]) if len(sys.argv) > 1 else 60):
    ok = 0
    with open(D / "ok_tools.jsonl", "a") as good:
        for i in range(n):
            lang, art = random.choice(["de", "en"]), random.choice(ARTEN)
            try:
                txt = batch(lang, art)
            except Exception as e:
                print(f"[{i}] {type(e).__name__}", flush=True); continue
            for line in txt.splitlines():
                try:
                    d = json.loads(line.strip().strip(","))
                except ValueError:
                    continue
                if not (isinstance(d, dict) and gut(d)):
                    continue
                base = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": d["user"]}]
                call = {"role": "assistant", "content": d["call"].strip()}
                good.write(json.dumps({"lang": lang, "thema": "tool-call", "messages": base + [call]}, ensure_ascii=False) + "\n")
                good.write(json.dumps({"lang": lang, "thema": "tool-answer", "messages": base + [call,
                    {"role": "user", "content": "⟦result⟧ " + d["result"]}, {"role": "assistant", "content": d["answer"]}]},
                    ensure_ascii=False) + "\n")
                ok += 1
            print(f"[{i}] ok={ok}", flush=True)


if __name__ == "__main__":
    main()
