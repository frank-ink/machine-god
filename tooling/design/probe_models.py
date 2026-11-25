#!/usr/bin/env python3
"""Lists model ids per provider (GET /models, first key of each provider, keys never printed) -> /tmp/models_<prov>.json"""
import json, sys, urllib.request
sys.path.insert(0, "~/last-resort")
import llm  # noqa: E402
K = llm._keys()
for nm, url, pre in (("nvidia", "https://integrate.api.nvidia.com/v1/models", "NVIDIA"), ("groq", "https://api.groq.com/openai/v1/models", "GROQ"),
                     ("openrouter", "https://openrouter.ai/api/v1/models", "OPENROUTER")):
    n = sorted(k for k in K if k.startswith(pre))[0]
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + K[n], "User-Agent": "mg-bench/1.0"}), timeout=30))
        ids = [m["id"] for m in d["data"]]
        open(f"/tmp/models_{nm}.json", "w").write(json.dumps(ids)); print(nm, len(ids))
    except Exception as e:
        print(nm, "ERR", type(e).__name__)
