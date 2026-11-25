import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team import clayteam as T

KEYS = {r: f"nvapi-SECRET-{r}" for r in T.ORDER}
ART = "```python\ndef add(a, b):\n    return a + b\n```\n"
GOOD_TEST = "```python\n# test\nfrom artifact import add\ndef test_add():\n    assert add(1, 2) == 3\n```"
BAD_TEST = "```python\n# test\nfrom artifact import add\ndef test_add():\n    assert add(1, 2) == 4\n```"


def fake(test_block, verdict="accept", bad_first=()):
    seen = set()

    def chat(key, msgs, model=None):
        role = next(r for r in T.ORDER if T.CARDS[r] in msgs[0]["content"])
        if role in bad_first and role not in seen:
            seen.add(role)
            return "hello world prose", {}, 1
        if role == "bauer":
            return "needle add(a, b) -> Number\n" + ART + test_block, {}, 1
        if role == "waechter":
            return f'rule verdict = "{verdict}"', {}, 1
        return f"rule {role}_note = 1", {}, 1
    return chat


def board(d):
    return [json.loads(l) for l in open(os.path.join(d, "board.jsonl"))]


def test_accept_path(tmp_path):
    r = T.run("add", str(tmp_path), rounds=2, chat=fake(GOOD_TEST), keys=KEYS)
    assert r["accepted"] and r["round"] == 1
    assert os.path.exists(os.path.join(r["path"], "artifact.py"))
    runner = [e for e in board(tmp_path) if e["role"] == "runner"][0]
    assert runner["pytest_rc"] == 0 and "rule tests_passed = 1" in runner["clay"]


def test_reject_when_pytest_fails(tmp_path):
    r = T.run("add", str(tmp_path), rounds=1, chat=fake(BAD_TEST), keys=KEYS)
    assert not r["accepted"]
    assert [e for e in board(tmp_path) if e["role"] == "runner"][0]["pytest_rc"] != 0


def test_reject_verdict(tmp_path):
    assert not T.run("add", str(tmp_path), rounds=1, chat=fake(GOOD_TEST, "reject"), keys=KEYS)["accepted"]


def test_repair_path(tmp_path):
    T.run("add", str(tmp_path), rounds=1, chat=fake(GOOD_TEST, bad_first=("forscher",)), keys=KEYS)
    e = [x for x in board(tmp_path) if x["role"] == "forscher"][0]
    assert e["repaired"] and e["parse_ok"]


def test_board_fields_and_no_key_leak(tmp_path):
    T.run("add", str(tmp_path), rounds=1, chat=fake(GOOD_TEST), keys=KEYS)
    raw = open(os.path.join(tmp_path, "board.jsonl")).read()
    assert all(k not in raw for k in KEYS.values())
    e = board(tmp_path)[0]
    for f in ("ts", "round", "role", "model", "key_name", "key_hash8", "parse_ok", "repaired", "clay",
              "has_artifact", "latency_ms", "usage"):
        assert f in e


def test_no_files_outside_workdir(tmp_path):
    wd = tmp_path / "wd"
    T.run("add", str(wd), rounds=1, chat=fake(GOOD_TEST), keys=KEYS)
    assert sorted(os.listdir(tmp_path)) == ["wd"]


def test_salvage_keeps_valid_lines(tmp_path):
    from team import clay_core as C
    assert C.salvage('prose here\nrule verdict = "accept"\nrule bad = x: y\n```\nrule a = 1\n```') == 'rule verdict = "accept"\nrule a = 1'
    assert C.salvage("only prose") == ""


def test_missing_verdict_is_asked_once(tmp_path):
    base = fake(GOOD_TEST)
    asked = []

    def chat(key, msgs, model=None):
        if T.CARDS["waechter"] in msgs[0]["content"]:
            if "verdict missing" in msgs[-1]["content"]:
                asked.append(1)
                return 'rule verdict = "accept"', {}, 1
            return "rule spec_ok = 1", {}, 1
        return base(key, msgs, model)
    r = T.run("add", str(tmp_path), rounds=1, chat=chat, keys=KEYS)
    assert r["accepted"] and asked == [1]


def test_chat_error_does_not_kill_run(tmp_path):
    from team import clay_core as C
    base = fake(GOOD_TEST)

    def chat(key, msgs, model=None):
        if T.CARDS["forscher"] in msgs[0]["content"]:
            raise C.ChatError("HTTP -1: TimeoutError")
        return base(key, msgs, model)
    r = T.run("add", str(tmp_path), rounds=1, chat=chat, keys=KEYS)
    assert r["accepted"]
    e = [x for x in board(tmp_path) if x["role"] == "forscher"][0]
    assert not e["parse_ok"] and e["error"].startswith("chat:")


def test_runner_reports_failed_test_names(tmp_path):
    T.run("add", str(tmp_path), rounds=1, chat=fake(BAD_TEST), keys=KEYS)
    runner = [e for e in board(tmp_path) if e["role"] == "runner"][0]
    assert "rule failed_1 = " in runner["clay"] and "test_add" in runner["clay"]


def _oracle(tmp_path, body):
    p = tmp_path / "oracle_src.py"
    p.write_text("from artifact import add\n" + body)
    return str(p)


def test_oracle_pass_accepts(tmp_path):
    o = _oracle(tmp_path, "def test_o():\n    assert add(2, 2) == 4\n")
    r = T.run("add", str(tmp_path / "w"), rounds=1, chat=fake(GOOD_TEST), keys=KEYS, oracle=o)
    assert r["accepted"] and r["oracle"]
    assert os.path.exists(os.path.join(r["path"], "test_oracle.py"))
    runner = [e for e in board(tmp_path / "w") if e["role"] == "runner"][0]
    assert runner["oracle_rc"] == 0 and "rule oracle_passed = 1" in runner["clay"]


def test_oracle_fail_blocks_accept_and_hides_assertion(tmp_path):
    o = _oracle(tmp_path, "def test_secret_rule():\n    assert add(1, 2) == 99\n")
    r = T.run("add", str(tmp_path / "w"), rounds=2, chat=fake(GOOD_TEST), keys=KEYS, oracle=o)
    assert not r["accepted"]
    runner = [e for e in board(tmp_path / "w") if e["role"] == "runner"][0]
    assert runner["oracle_rc"] != 0 and "test_secret_rule" in runner["clay"]
    assert "99" not in runner["clay"]


def test_team_tests_wrong_hint(tmp_path):
    o = _oracle(tmp_path, "def test_o():\n    assert add(1, 2) == 3\n")
    r = T.run("add", str(tmp_path / "w"), rounds=1, chat=fake(BAD_TEST), keys=KEYS, oracle=o)
    assert not r["accepted"]
    runner = [e for e in board(tmp_path / "w") if e["role"] == "runner"][0]
    assert "rule team_tests_wrong" in runner["clay"]


def test_no_oracle_keeps_old_contract(tmp_path):
    r = T.run("add", str(tmp_path), rounds=1, chat=fake(GOOD_TEST), keys=KEYS)
    assert r["accepted"] and not r["oracle"]
    assert [e for e in board(tmp_path) if e["role"] == "runner"][0]["oracle_rc"] is None


def test_keyset_b_and_role_models(tmp_path):
    seen = []
    base = fake(GOOD_TEST)

    def chat(key, msgs, model=None):
        seen.append(model)
        return base(key, msgs, model)
    r = T.run("add", str(tmp_path), rounds=1, chat=chat, keys=KEYS, keyset="B",
              role_models={"pruefer": "m-pruefer"}, model="m-base")
    assert r["accepted"]
    b = [e for e in board(tmp_path) if e["role"] != "runner"]
    assert {e["key_name"] for e in b} == {f"NVIDIA{i}_API_KEY" for i in range(6, 11)}
    assert [e["model"] for e in b if e["role"] == "pruefer"] == ["m-pruefer"]
    assert "m-base" in seen and "m-pruefer" in seen


def test_keysets_are_disjoint():
    from team import clay_core as C
    assert not set(C.KEYSETS["A"].values()) & set(C.KEYSETS["B"].values())
    assert C.ROLES == C.KEYSETS["A"]


MIXED_TEST = ("```python\n# test\nfrom artifact import add\n\ndef test_ok():\n    assert add(1, 2) == 3\n\n"
              "class TestX:\n    def test_bad(self):\n        assert add(1, 2) == 4\n```")


def judge_fake(ruling):
    base = fake(MIXED_TEST)
    calls = []

    def chat(key, msgs, model=None):
        if T.RICHTER_CARD in msgs[0]["content"]:
            calls.append(msgs[1]["content"])
            return f'rule ruling = "{ruling}"', {}, 1
        return base(key, msgs, model)
    return chat, calls


def test_richter_invalid_quarantines_and_accepts(tmp_path):
    o = _oracle(tmp_path, "def test_o():\n    assert add(1, 2) == 3\n")
    chat, calls = judge_fake("invalid")
    r = T.run("add", str(tmp_path / "w"), rounds=1, chat=chat, keys=KEYS, oracle=o, adjudicate=True)
    assert r["accepted"]
    assert "def test_bad" in calls[0] and "add(1, 2) == 4" in calls[0]
    assert "test_bad" in open(os.path.join(r["path"], "quarantine.py")).read()
    assert "test_bad" not in open(os.path.join(r["path"], "test_artifact.py")).read()
    b = board(tmp_path / "w")
    assert [e["ruling"] for e in b if e["role"] == "richter"] == ["invalid"]
    runner = [e for e in b if e["role"] == "runner"][0]
    assert runner["pytest_rc"] == 0 and "rule quarantined_1" in runner["clay"]


def test_richter_valid_keeps_test_and_blocks(tmp_path):
    o = _oracle(tmp_path, "def test_o():\n    assert add(1, 2) == 3\n")
    chat, _ = judge_fake("valid")
    r = T.run("add", str(tmp_path / "w"), rounds=1, chat=chat, keys=KEYS, oracle=o, adjudicate=True)
    assert not r["accepted"]
    runner = [e for e in board(tmp_path / "w") if e["role"] == "runner"][0]
    assert runner["pytest_rc"] != 0 and "rule must_fix_1" in runner["clay"]


def test_richter_not_called_when_oracle_fails(tmp_path):
    o = _oracle(tmp_path, "def test_o():\n    assert add(1, 2) == 99\n")
    chat, calls = judge_fake("invalid")
    T.run("add", str(tmp_path / "w"), rounds=1, chat=chat, keys=KEYS, oracle=o, adjudicate=True)
    assert calls == []


def test_remove_tests_keeps_others():
    src = "def test_a():\n    pass\n\nclass TestB:\n    def test_b(self):\n        pass\n"
    out = T._remove_tests(src, {"test_b"})
    assert "test_a" in out and "test_b" not in out and "class TestB" in out


def test_route_hierarchy_falls_back_to_next_model(tmp_path):
    from team import clay_core as C
    base, seen = fake(GOOD_TEST), []

    def chat(key, msgs, model=None):
        seen.append(model)
        if model == "dead/model":
            raise C.ChatError("HTTP 429")
        return base(key, msgs, model)
    r = T.run("add", str(tmp_path), rounds=1, chat=chat, keys=KEYS, model="dead/model",
              fallbacks={x: ["alive/model"] for x in T.ORDER})
    assert r["accepted"]
    e = [x for x in board(tmp_path) if x["role"] == "bauer"][0]
    assert e["model"] == "alive/model" and e["fallback_from"] == ["dead/model"] and e["parse_ok"]


def test_chat_chain_order_dedup_and_exhaustion():
    from team import clay_core as C
    tried = []

    def chat(key, msgs, model=None):
        tried.append(model)
        raise C.ChatError("down " + model)
    try:
        T.chat_chain(chat, "k", [], ["a/1", "b/2", "a/1"])
        assert False
    except C.ChatError as e:
        assert "b/2" in str(e)
    assert tried == ["a/1", "b/2"]
