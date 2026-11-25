#!/usr/bin/env python3
"""arxiv_feed.py -- pulls newest arXiv abstracts for team 3 (read-only, export.arxiv.org API, 3 s between calls).
Writes arxiv/<date>.md and arxiv/latest.md. No account, no key, nothing sent except search queries."""
import re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

D = Path(__file__).resolve().parent / "arxiv"
Q = {
    "global workspace / machine consciousness theory": 'abs:"global workspace" AND (cat:cs.AI OR cat:q-bio.NC)',
    "emergence measurement & steering": 'abs:"emergence" AND abs:"measure" AND cat:cs.AI',
    "hyperdimensional / vector-symbolic computing": 'abs:"hyperdimensional" OR abs:"vector symbolic"',
    "unified theories / theory of everything": 'abs:"theory of everything" OR abs:"unified field theory"',
    "structural realism / process ontology / information ontology": 'abs:"structural realism" OR abs:"process ontology" OR abs:"it from bit"',
    "resonance, frequency and the origin of life/cosmos": '(abs:"resonance" OR abs:"oscillation") AND (abs:"origin of life" OR abs:"cosmogenesis")',
    "Perelman / Ricci flow & entropy (geometrization)": 'au:Perelman_G OR (abs:"Ricci flow" AND abs:"entropy")',
    "Haramein / vacuum structure & unified field": 'au:Haramein OR (abs:"vacuum fluctuations" AND abs:"unified field")',
    "multi-agent LLM reasoning & self-improvement": 'abs:"multi-agent" AND abs:"large language model" AND abs:"reasoning"',
    "OS-level agent substrates (eBPF, sandboxing, kernel)": 'abs:"agent" AND (abs:"eBPF" OR abs:"operating system kernel")',
}
NS = {"a": "http://www.w3.org/2005/Atom"}


def fetch(q, n=6):
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": n})
    root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
    for e in root.findall("a:entry", NS):
        yield (e.findtext("a:id", "", NS).strip(), e.findtext("a:published", "", NS)[:10],
               " ".join(e.findtext("a:title", "", NS).split()), " ".join(e.findtext("a:summary", "", NS).split())[:900])


def main():
    D.mkdir(exist_ok=True)
    out = [f"# arXiv digest {datetime.now():%Y-%m-%d %H:%M} (newest first, abstracts truncated)\n"]
    for topic, q in Q.items():
        out.append(f"\n## {topic}\n")
        try:
            for aid, pub, title, abs_ in fetch(q):
                out.append(f"- [{pub}] {title} ({aid})\n  {abs_}\n")
        except Exception as e:  # noqa: BLE001
            out.append(f"- FETCH FAILED: {type(e).__name__} {str(e)[:80]}\n")
        time.sleep(3)
    txt = "".join(out)
    (D / f"{datetime.now():%Y-%m-%d_%H%M}.md").write_text(txt)
    (D / "latest.md").write_text(txt)
    print(f"{len(re.findall(r'^- \[', txt, re.M))} papers")


if __name__ == "__main__":
    main()
