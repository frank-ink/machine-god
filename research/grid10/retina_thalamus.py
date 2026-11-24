"""retina_thalamus.py -- Thalamus-Gating der Retina-Kanaele, Stueck 2 (reiner Kern, deterministisch, Zeit wird uebergeben).

Formel wie im Original (Project-Frankenstein services/thalamus.py), je Kanal und Fenster:
  gain = base * (1 - 0.8*H) * attention * vigilanz(1+0.3*v) * novelty(2.0 bei Burst sonst 1+0.5*n) * (1+feedback) * (1+min(0.5*fehler, 0.4))
  Relais nur wenn Kanal Inhalt hat UND gain >= RELAY_THRESHOLD (0.25).
Abweichung A (der Nutzer 2026-11-24): Habituierung ERHOLT sich. Ein Fenster ohne Inhalt habituiert nicht, sondern H *= exp(-dt/tau)
  (im Original blieb H im Fixpunkt 1.0, gemessen). Gleicher Inhalt wie zuletzt weitergereicht: H waechst wie im Original.
Abweichung B: Burst nur aus echten Signalen (real = Menge aus {"amygdala","reality_flag"}) oder Rueckkehr nach Abwesenheit
  (person_kommt nach >= RETURN_ABSENCE_S ohne Personen-Ereignis); nie aus Dauerstatus / Zahlenspruengen.
Kanalwerte (base, tau) sind UNKALIBRIERTE Startwerte; Taus sind auf das 300-s-Fenster skaliert (Original: 30-300 s je Gate)."""
import math

RELAY_THRESHOLD = 0.25
RETURN_ABSENCE_S = 900.0
CHANNELS = {  # art im Ereignisstrom -> base, tau (s)
    "person_kommt": {"base": 0.9, "tau": 900.0}, "person_geht": {"base": 0.9, "tau": 900.0},
    "fokus_app": {"base": 0.6, "tau": 1500.0}, "objekt_neu": {"base": 0.6, "tau": 900.0}, "objekt_weg": {"base": 0.5, "tau": 900.0},
}
ATTENTION = {  # kognitiver Modus -> Gewicht je Kanal
    "chat_active": {"person_kommt": 1.2, "person_geht": 1.2, "fokus_app": 0.8, "objekt_neu": 0.6, "objekt_weg": 0.5},
    "idle_focus": {"person_kommt": 1.0, "person_geht": 1.0, "fokus_app": 1.0, "objekt_neu": 0.8, "objekt_weg": 0.6},
}
FB_DECAY, FB_BOOST, FB_SUPPRESS = 0.87, 0.15, -0.05  # wie im Original


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def final_gain(base, hab, attn, vig, novelty, burst, fb, pred_err):
    """Reine Originalformel (Referenz fuer das Test-Tor a)."""
    return _clamp(base * (1.0 - hab * 0.8) * attn * (1.0 + _clamp(vig, -1.0, 1.0) * 0.3)
                  * (2.0 if burst else 1.0 + novelty * 0.5) * (1.0 + fb) * (1.0 + min(pred_err * 0.5, 0.4)))


class RetinaThalamus:
    def __init__(self, channels=None):
        self.ch = channels or CHANNELS
        self.s = {n: {"h": 0.0, "last_val": None, "pred": 0.0, "last_ts": None, "fb": 0.0, "last_relay_val": None} for n in self.ch}
        self.last_person_ts = None

    def to_json(self):
        return {"s": self.s, "last_person_ts": self.last_person_ts}

    @classmethod
    def from_json(cls, d, channels=None):
        t = cls(channels)
        t.s.update(d.get("s", {}))
        t.last_person_ts = d.get("last_person_ts")
        return t

    def gate(self, counts, ts, mode="idle_focus", vig=0.0, real=()):
        """counts: {kanal: Anzahl Ereignisse im Fenster}, ts: Fensterende (s). -> {"gains","relay","burst","hab"}."""
        att = ATTENTION.get(mode, ATTENTION["idle_focus"])
        person = counts.get("person_kommt", 0) + counts.get("person_geht", 0) > 0
        back = (counts.get("person_kommt", 0) > 0 and self.last_person_ts is not None and ts - self.last_person_ts >= RETURN_ABSENCE_S)
        real_burst = bool(set(real) & {"amygdala", "reality_flag"})
        gains, relay, burst = {}, [], []
        for n, c in self.ch.items():
            st, cnt = self.s[n], counts.get(n, 0)
            val = _clamp(cnt / 10.0)
            dt = 0.0 if st["last_ts"] is None else max(0.0, ts - st["last_ts"])
            st["last_ts"] = ts
            if cnt == 0:  # A: kein Inhalt -> Erholung, nichts zu relayen
                st["h"] *= math.exp(-dt / c["tau"]) if c["tau"] > 0 else 0.0
                st["pred"] += 0.3 * (0.0 - st["pred"])
                gains[n] = 0.0
                continue
            if st["last_relay_val"] is None:
                nov = 1.0
            elif val == st["last_relay_val"]:
                nov = 0.0
                st["h"] = 1.0 - (1.0 - st["h"]) * math.exp(-dt / c["tau"])
            else:
                nov = min(1.0, abs(val - st["last_relay_val"]) * 2.0 + 0.3 * min(1.0, dt / 300.0))
                st["h"] *= 0.5
            perr = abs(val - st["pred"])
            st["pred"] += 0.3 * (val - st["pred"])
            is_burst = real_burst or (n == "person_kommt" and back)  # B
            g = final_gain(c["base"], st["h"], att.get(n, 0.5), vig, nov, is_burst, st["fb"], perr)
            gains[n] = g
            if is_burst:
                burst.append(n)
            if g >= RELAY_THRESHOLD:
                relay.append(n)
                st["last_relay_val"] = val
        if person:
            self.last_person_ts = ts
        for st in self.s.values():  # Rueckkanal klingt je Gate ab
            st["fb"] *= FB_DECAY
        return {"gains": gains, "relay": relay, "burst": burst, "hab": {n: s["h"] for n, s in self.s.items()}}

    def receive_feedback(self, referenced):
        """Wie im Original: genannte Kanaele +0.15, die uebrigen mild -0.05 (nur wenn nicht schon im Plus)."""
        for n, st in self.s.items():
            if n in referenced:
                st["fb"] = FB_BOOST
            elif st["fb"] <= 0:
                st["fb"] = FB_SUPPRESS
