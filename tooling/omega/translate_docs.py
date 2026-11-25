#!/usr/bin/env python3
"""translate_docs.py <file>... : German markdown -> English via the free pool (chunked at headings). Code, identifiers, paths, URLs untouched.
Refuses output that lost >15 % of the code spans or changed the line count by >25 %. Writes in place only if the gate passes."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "last-resort"))
from freechain import chat
SYS = ("Translate this German technical markdown into natural English. Keep ALL markdown structure, code blocks, `inline code`, file names, "
       "identifiers, env vars, URLs and numbers exactly as they are (do not translate or rename identifiers). Output ONLY the translation.")
def chunks(t, n=1800):
    out, cur = [], ""
    for part in re.split(r"(?m)^(?=#{1,3} )", t):
        if len(cur) + len(part) > n and cur: out.append(cur); cur = ""
        cur += part
    return out + ([cur] if cur else [])
def tr(c):
    for _ in range(3):
        r = chat([{"role": "system", "content": SYS}, {"role": "user", "content": c}], max_tokens=6000, temperature=0.2)
        if isinstance(r, tuple): r = next((x for x in r if isinstance(x, str) and x.strip()), "")
        if isinstance(r, str) and r.strip():
            r = re.sub(r"^```(?:markdown|md)?\n|\n```\s*$", "", r.strip()) + "\n"
            if abs(r.count("\n") - c.count("\n")) <= 0.25 * c.count("\n") + 3 and len(re.findall(r"`[^`\n]+`", r)) >= 0.85 * len(re.findall(r"`[^`\n]+`", c)):
                return r
    return None
for f in sys.argv[1:]:
    p = Path(f); src = p.read_text(); outp = []
    for i, c in enumerate(chunks(src)):
        r = tr(c)
        if r is None: print(f"{f}: chunk {i} failed gate, file left unchanged"); break
        outp.append(r)
    else:
        p.write_text("".join(outp)); print(f"{f}: ok {len(outp)} chunks")
