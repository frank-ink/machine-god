import importlib.util, sys
sp = importlib.util.spec_from_file_location("a", sys.argv[1]); a = importlib.util.module_from_spec(sp); sp.loader.exec_module(a)
I = [dict(item_id="b", tokens=50, relevance=0.9), dict(item_id="a", tokens=50, relevance=0.9),
     dict(item_id="c", tokens=80, relevance=0.8), dict(item_id="d", tokens=20, relevance=0.1)]
c = {}
c["greedy"] = a.greedy_relevance(I, 120) == ["a", "b", "d"]   # c does not fit, skip and continue
c["greedy_zero"] = a.greedy_relevance(I, 0) == []
comps = [dict(id="x", items=I, gold=["a", "c"]), dict(id="y", items=I, gold=[]), dict(id="z", items=I, gold=["d"])]
r = a.evaluate(comps, a.greedy_relevance, 120)
c["n_eval"] = r["n_eval"] == 2
c["recall"] = abs(r["recall"] - (0.5 + 1.0) / 2) < 1e-9
c["precision"] = abs(r["precision"] - (1/3 + 1/3) / 2) < 1e-9
c["er"] = r["er_at_budget"] == 1.0
c["tokens"] = abs(r["mean_tokens_used"] - 120.0) < 1e-9
try: a.evaluate(comps, lambda it, b: ["c", "a"], 100); c["budget"] = False
except a.BudgetExceeded as e: c["budget"] = "x" in str(e)
try: a.evaluate(comps, lambda it, b: ["nope"], 100); c["unknown"] = False
except ValueError: c["unknown"] = True
except Exception: c["unknown"] = False
e = a.evaluate([dict(id="q", items=I, gold=[])], lambda it, b: [], 10)
c["zero_den"] = e["recall"] == 0.0 and e["precision"] == 0.0 and e["er_at_budget"] == 0.0 and e["n_eval"] == 0
print(c, "ALL" if all(c.values()) else "FAIL:" + ",".join(k for k, v in c.items() if not v))
