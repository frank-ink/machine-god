#!/usr/bin/env python3
"""Machine God free-tier wiki: seed list + Omnipool radar (read-only) -> ~/.local/share/machine-god/wiki/{anbieter.json,WIKI.md,neu.json}.
The web search itself is Omnipool's radar (feeds, index, daily discovery); this script only merges and marks what is new.
Never reads or writes key values: only which providers already have a working slot (Omnipool `key.status`)."""
import json, os, sqlite3, time
from pathlib import Path

DB = Path(os.environ.get("OMNIPOOL_HOME", Path.home() / ".local/share/omnipool")) / "omnipool.db"
OUT = Path.home() / ".local/share/machine-god/wiki"
# seed: model knowledge (mid-2026), status "ungeprueft" until the radar or a live probe confirms it
SEED = [
    ("nvidia", "NVIDIA NIM (build.nvidia.com)", "https://build.nvidia.com", "Chat Code Vision", "Gratis-Credits, viele offene Modelle (Nemotron, Llama, DeepSeek, Qwen)"),
    ("groq", "Groq", "https://console.groq.com", "Chat Audio", "Gratis-Stufe mit Minuten-/Tageslimits, sehr schnell"),
    ("openrouter", "OpenRouter (:free-Modelle)", "https://openrouter.ai", "Chat Code", "Modelle mit Endung :free, Tageslimit"),
    ("zai", "Z.ai (GLM Flash)", "https://z.ai", "Chat Code", "GLM-Flash-Modelle gratis"),
    ("gemini", "Google AI Studio (Gemini API)", "https://aistudio.google.com", "Chat Vision Audio", "Gratis-Stufe mit Tageslimit"),
    ("mistral", "Mistral La Plateforme (Experiment)", "https://console.mistral.ai", "Chat Code", "Experiment-Plan gratis, Rate-Limit"),
    ("cerebras", "Cerebras Inference", "https://cloud.cerebras.ai", "Chat", "Gratis-Stufe, sehr schnell"),
    ("sambanova", "SambaNova Cloud", "https://cloud.sambanova.ai", "Chat", "Gratis-Stufe mit Limits"),
    ("github", "GitHub Models", "https://github.com/marketplace/models", "Chat Code", "Gratis zum Ausprobieren mit GitHub-Konto"),
    ("cloudflare", "Cloudflare Workers AI", "https://developers.cloudflare.com/workers-ai", "Chat Bild Audio", "Taegliches Gratis-Kontingent"),
    ("huggingface", "Hugging Face Inference Providers", "https://huggingface.co/docs/inference-providers", "Chat Bild Audio", "Freies Monatskontingent"),
    ("cohere", "Cohere Trial", "https://dashboard.cohere.com", "Chat Embedding", "Trial-Schluessel gratis, nicht fuer Produktion"),
    ("chutes", "Chutes", "https://chutes.ai", "Chat", "Offene Modelle, Gratis-Kontingent wechselt"),
    ("tavily", "Tavily (Websuche)", "https://tavily.com", "Suche", "Gratis-Monatskontingent fuer Websuche"),
]


def main():
    alt = {}
    if (OUT / "anbieter.json").is_file():
        alt = {a["id"]: a for a in json.loads((OUT / "anbieter.json").read_text())["anbieter"]}
    rows = {s[0]: dict(id=s[0], name=s[1], url=s[2], kategorie=s[3], gratis=s[4], quelle="seed", status="ungeprueft") for s in SEED}
    aktiv = set()
    if DB.is_file():
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        aktiv = {p for (p,) in c.execute("select distinct provider from key where status='ok'")}
        for (p, n) in c.execute("select provider, count(*) from modell where coalesce(gone,0)=0 group by provider"):
            if p in rows:
                rows[p].update(status="live", modelle=n)
        for (i, name, url, beschr, kat) in c.execute("select id,name,url,beschr,kategorie from api_index where quelle='kuratiert'"):
            if not any(r["url"].rstrip("/") == (url or "").rstrip("/") for r in rows.values()):
                rows["idx-" + i[:8]] = dict(id="idx-" + i[:8], name=name, url=url, kategorie=kat, gratis=beschr, quelle="radar", status="ungeprueft")
    now = time.strftime("%Y-%m-%d %H:%M")
    for r in rows.values():
        r["eingerichtet"] = r["id"] in aktiv
        r["seit"] = alt.get(r["id"], {}).get("seit", now)
    neu = [r for k, r in rows.items() if k not in alt] if alt else []
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "anbieter.json").write_text(json.dumps({"stand": now, "anbieter": list(rows.values())}, ensure_ascii=False, indent=1))
    (OUT / "neu.json").write_text(json.dumps(neu, ensure_ascii=False, indent=1))
    md = [f"# Machine God: Free-Token-Wiki (Stand {now})", "", "| Anbieter | Was gratis | Art | Status | Bei dir |", "|---|---|---|---|---|"]
    for r in sorted(rows.values(), key=lambda r: (r["status"] != "live", r["name"].lower())):
        md.append(f"| [{r['name']}]({r['url']}) | {r['gratis']} | {r['kategorie']} | {r['status']} | {'eingerichtet' if r['eingerichtet'] else 'fehlt noch'} |")
    md += ["", "Status: live = Omnipool misst Modelle; ungeprueft = noch keine Messung, Bedingungen selbst pruefen.", "Neue Funde kommen vom Omnipool-Radar (Feeds, Index, taegliche Suche)."]
    (OUT / "WIKI.md").write_text("\n".join(md) + "\n")
    print(f"wiki: {len(rows)} anbieter, live {sum(r['status'] == 'live' for r in rows.values())}, eingerichtet {len(aktiv)}, neu {len(neu)}")


if __name__ == "__main__":
    main()
