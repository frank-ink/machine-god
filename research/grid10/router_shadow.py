"""router_shadow.py -- Router-Shadow (Stueck 3, Schritt 4): WELCHES Modell der Router fuer die gewaehlten Klassen waehlen WUERDE; kein Provider-Aufruf, keine Antwortwirkung.
Quelle ist ein Schnappschuss der Router-Auskunft (pool_offer: Klasse -> bestes Modell + Score), Datei kalibrierung-stueck3/router_offer.json. Der Router entscheidet das
Modell; hier steht kein Modellname im Code. Aelter als MAX_AGE_S -> 'stale' (Entscheidung trotzdem protokolliert, als veraltet markiert). Der echte HTTP-Aufruf
(omnipool-<klasse>) bleibt aus, bis der Nutzer die Anwendung in Omni-Brain freigibt (#connect; Status 'pending')."""
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
