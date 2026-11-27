import json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team import clay_core as C

SECRET = "nvapi-TESTSECRET-0123456789"


def test_load_key_variants(tmp_path):
    p = tmp_path / "k.env"
    p.write_text(f'# c\nexport A_KEY="{SECRET}"\nB_KEY=\'x1\'\nC_KEY=plain\n')
    assert C.load_key("A_KEY", str(p)) == SECRET
    assert C.load_key("B_KEY", str(p)) == "x1" and C.load_key("C_KEY", str(p)) == "plain"
    with pytest.raises(KeyError) as e:
        C.load_key("MISSING", str(p))
    assert SECRET not in str(e.value)


def test_fingerprint():
    assert len(C.key_fingerprint(SECRET)) == 8 and C.key_fingerprint(SECRET) != SECRET[:8]


def test_split_reply_keeps_fenced_claycode():
    assert C.split_reply("```python\nrule a = 1\n```") == ("rule a = 1", [])
    clay, py = C.split_reply("rule a = 1\n```python\nimport os\nx = 1\n```")
    assert clay == "rule a = 1" and py == ["import os\nx = 1"]


def test_validate():
    assert C.validate("rule a = 1") == (True, "")
    assert C.validate("hello world")[0] is False
    assert C.validate("")[0] is False


def test_chat_retry_and_no_key_leak():
    calls = []
    ok = json.dumps({"choices": [{"message": {"content": "rule a = 1"}}], "usage": {"total_tokens": 3}}).encode()

    def post(url, body, headers, timeout):
        calls.append(1)
        return (429, b"slow") if len(calls) == 1 else (200, ok)
    text, usage, ms = C.chat(SECRET, [], _post=post, _sleep=lambda s: None)
    assert text == "rule a = 1" and usage["total_tokens"] == 3 and len(calls) == 2

    def bad(url, body, headers, timeout):
        return 401, ("bad key " + SECRET).encode()
    with pytest.raises(C.ChatError) as e:
        C.chat(SECRET, [], _post=bad, _sleep=lambda s: None)
    assert SECRET not in str(e.value)
