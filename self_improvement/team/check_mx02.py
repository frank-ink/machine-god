import importlib.util, sys
sp = importlib.util.spec_from_file_location("a", sys.argv[1]); a = importlib.util.module_from_spec(sp); sys.modules["a"] = a; sp.loader.exec_module(a)
def raises(f, *x):
    try: f(*x); return False
    except ValueError: return True
ok = {"t": 1.0}
base = dict(compile_id="c", item_id="i", signal="cited", weight=0.5, ts=1.0)
c = {}
c["parse_ok"] = a.parse_feedback(base).signal == "cited"
c["missing"] = raises(a.parse_feedback, {k: v for k, v in base.items() if k != "ts"})
c["empty_id"] = raises(a.parse_feedback, dict(base, item_id=""))
c["bad_signal"] = raises(a.parse_feedback, dict(base, signal="liked"))
c["weight_hi"] = raises(a.parse_feedback, dict(base, weight=1.01))
c["weight_edges"] = a.parse_feedback(dict(base, weight=0.0)).weight == 0.0 and a.parse_feedback(dict(base, weight=1.0)).weight == 1.0
try:
    fb = a.parse_feedback(base); fb.signal = "x"; c["frozen"] = False
except Exception: c["frozen"] = True
texts = {"i1": "alpha bravo charlie delta echo", "i2": "zulu yankee xray whiskey victor", "i3": "foxtrot golfs hotel"}
ans = "we used item i3 here; ALPHA bravo charlie appear. whiskey"
r = a.attribute(["i2", "i1", "i3", "i9"], ans, texts)
c["attr"] = r == {"i2": "ignored", "i1": "used", "i3": "cited", "i9": "ignored"}
c["order"] = list(r) == ["i2", "i1", "i3", "i9"]
c["below_overlap"] = a.attribute(["i1"], "alpha bravo", texts) == {"i1": "ignored"}
c["missing_text_cited"] = a.attribute(["i9"], "see i9", texts) == {"i9": "cited"}
c["credit"] = a.credit({"a": "cited", "b": "used", "c": "ignored", "d": "corrected", "e": "harmful"}) == {"a": 1.0, "b": 0.5, "c": 0.0, "d": -0.5, "e": -1.0}
c["credit_bad"] = raises(a.credit, {"a": "meh"})
print(c, "ALL" if all(c.values()) else "FAIL:" + ",".join(k for k, v in c.items() if not v))
