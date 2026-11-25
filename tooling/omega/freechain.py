"""Free-only chain for the Machine God generators: NVIDIA models zero40 measured as fast first, then free tiers.
The paid DeepSeek tier of ~/last-resort/llm.py is removed (Gabriel 2026-11-24: 'alles mit free tokens')."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "last-resort"))
import llm  # noqa: E402
_nv = next(t for t in llm.TIERS if t[0] == "nvidia")
llm.TIERS = [("nvidia", _nv[1], m, _nv[3]) for m in ("nvidia/nemotron-3-ultra-550b-a55b", "minimaxai/minimax-m3.1-flash",
             "nvidia/nemotron-3.5-super-vl-120b-a12b")] + [t for t in llm.TIERS if t[0] in ("groq", "mistral")]   # openrouter tier = deepseek-chat without :free -> not free, dropped
assert not any(t[0] in ("deepseek", "openrouter") for t in llm.TIERS)
chat = llm.chat
