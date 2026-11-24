"""grid_v2.py -- GRID10 v2 engine, pure python port of omega_grid_v2.go (branch omega-B-deeptest / omega-B-gridj, OE-01).
Self-leveling core: divisive normalisation (change vs own slowly adapting baseline / own learned noise), fatigue on repeated winners
(Score_eff = score*(1-alpha*recency)), explicit ABSTAIN when no cell changed beyond noise, G7 = STATE (bias on the abstain threshold).
No clock, no I/O. step(None) = autonomous tick (decay only, abstain). Parity: modules/grid10/test_grid_v2_parity.py vs recorded vectors."""
import math

CELLS = ["G%d" % i for i in range(1, 11)]
CLAMP_MIN, CLAMP_MAX = -1.0, 4.0
G7 = "G7"

DEFAULT = dict(alpha_base=0.10, alpha_burst=0.60, burst_k=3.0, alpha_sigma=0.02, z_floor=0.03, offset_weight=0.4, zabs=4.0,
               goal_bias=0.15, lam=0.7, gain=1.0, fatigue_alpha=0.5, recency_rate=0.1, no_fatigue=False, no_abstain=False, no_norm=False,
               fixed_sigma=0.05)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class GridV2Engine:
    def __init__(self, **cfg):
        self.c = dict(DEFAULT, **cfg)
        self.reset()

    def reset(self):
        self.init = False
        self.base = {i: 0.0 for i in CELLS}
        self.sigma = {i: 0.0 for i in CELLS}
        self.cells = {i: 0.0 for i in CELLS}
        self.recency = {i: 0.0 for i in CELLS}
        self.steps = 0

    def to_json(self):
        return {"init": self.init, "base": self.base, "sigma": self.sigma, "cells": self.cells, "recency": self.recency, "steps": self.steps}

    @classmethod
    def from_json(cls, d, **cfg):
        e = cls(**cfg)
        e.init, e.base, e.sigma, e.cells, e.recency, e.steps = d["init"], d["base"], d["sigma"], d["cells"], d["recency"], d["steps"]
        return e

    def step(self, signals):
        """-> dict(winner, abstain, observed, max_score, thresh, score)"""
        c = self.c
        self.steps += 1
        out = {"winner": "", "max_score": 0.0, "thresh": 0.0, "score": {}, "abstain": False, "observed": False}
        if signals is None:
            for i in CELLS:
                self.cells[i] = _clamp(c["lam"] * self.cells[i], CLAMP_MIN, CLAMP_MAX)
                self.recency[i] *= 1 - c["recency_rate"]
            out["abstain"] = True
            return out
        out["observed"] = True
        if not self.init:
            for i in CELLS:
                self.base[i] = _clamp(signals.get(i, 0.0), 0.0, 1.0)
            self.init = True
            out["abstain"] = True
            return out
        x = {i: _clamp(signals.get(i, 0.0), 0.0, 1.0) for i in CELLS}
        best, best_score = "", 0.0
        drive = {}
        for i in CELLS:  # Go iterates GridCellIDs() order; ties: first max wins (strict >)
            d = x[i] - self.base[i]
            ad = abs(d)
            w = c["offset_weight"] if d < 0 else 1.0
            sg = self.sigma[i] + c["z_floor"]
            if c["no_norm"]:
                sg = c["fixed_sigma"]
            z = w * ad / sg
            fat = 1.0 if c["no_fatigue"] else 1 - c["fatigue_alpha"] * self.recency[i]
            sc = z * fat
            out["score"][i] = sc
            drive[i] = w * ad
            if best == "" or sc > best_score:
                best, best_score = i, sc
            a = c["alpha_base"]
            if ad > c["burst_k"] * (self.sigma[i] + c["z_floor"]):
                a = c["alpha_burst"]
            self.base[i] += a * d
            capped = min(ad, c["burst_k"] * (self.sigma[i] + c["z_floor"]))
            self.sigma[i] += c["alpha_sigma"] * (capped - self.sigma[i])
        thresh = c["zabs"] * (1 - c["goal_bias"] * x[G7])
        out["max_score"], out["thresh"] = best_score, thresh
        if c["no_abstain"] or best_score >= thresh:
            out["winner"] = best
        else:
            out["abstain"] = True
        for i in CELLS:
            self.cells[i] = _clamp(c["lam"] * self.cells[i] + c["gain"] * drive[i], CLAMP_MIN, CLAMP_MAX)
            win = 1.0 if i == out["winner"] else 0.0
            self.recency[i] += c["recency_rate"] * (win - self.recency[i])
        return out
