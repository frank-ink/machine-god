"""router_shadow.py -- Router Shadow (Part 3, Step 4): WHICH model the router WOULD choose for the selected classes; no provider call, no response effect.
Source is a snapshot of the router information (pool_offer: Klasse -> bestes Modell + Score), file kalibrierung-stueck3/router_offer.json. The router decides the
model; no model name appears in the code here. Older than MAX_AGE_S -> 'stale' (decision still logged, marked as outdated). The actual HTTP call
(omnipool-<klasse>) is omitted until the user releases the application in Omni-Brain (#connect; status 'pending')."""
import json
import os
import time

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kalibrierung-stueck3/router_offer.json")
MAX_AGE_S = 86400


def decide(selected, path=None, now=None):
    """-> (router_version, {klasse: {"model","score"}}) ; kein Schnappschuss -> ('none-shadow', {})."""
    try:
        d = json.load(open(path or PATH))
        age = (time.time() if now is None else now) - float(d["fetched"])
        cls = d["classes"]
    except Exception:
        return "none-shadow", {}
    pick = {c: {"model": cls[c]["best_model"], "score": cls[c]["score"]} for c in selected if c in cls}
    return "offer-snapshot%s:%d" % ("-stale" if age > MAX_AGE_S else "", int(d["fetched"])), pick
