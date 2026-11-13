"""Walk-forward backtest and calibration fit.

For each cutoff gameweek c the model is rebuilt using ONLY data up to c, then asked to predict the next
`horizon` gameweeks; predictions are compared with what happened. Calibration factors are the ratio of
mean actual to mean predicted points per (position, component), and are checked with a time split
(fit on early target rounds, test on later ones) so they are not simply fitted to the evaluation window.

Note: the backtest uses the raw history (penalties are not stripped) because per-match penalty data is
not available for past gameweeks; the live Projector strips them.
"""
from __future__ import annotations

import math
from collections import namedtuple

import numpy as np

from .config import Config
from .constants import COMPONENTS, POS
from .data import Season
from .players import build_players
from .points import actual_components, components, total
from .teams import team_state

Row = namedtuple("Row", "pid cut rnd pos comps actual points")


def evaluate(season: Season, cfg: Config, cuts=None, horizon: int = 5, last_gw: int | None = None) -> list:
    last_gw = last_gw or season.current_gw
    cuts = cuts or list(range(1, last_gw))
    rows = []
    for c in cuts:
        players, st = build_players(season, c, cfg), team_state(season, c, cfg)
        for pid, p in players.items():
            for r in season.hist[pid]:
                if c < r["round"] <= min(c + horizon, last_gw):
                    comps = components(p, "h" if r["was_home"] else "a", r["opponent_team"], st)
                    rows.append(Row(pid, c, r["round"], p["pos"], comps, actual_components(r, p["pos"]), r["total_points"]))
    return rows


def predicted(rows, calibration=None):
    return np.array([total(r.comps, r.pos, calibration) for r in rows])


def metrics(rows, calibration=None) -> dict:
    pr, ac = predicted(rows, calibration), np.array([r.points for r in rows])
    return {"n": len(rows), "rmse": math.sqrt(np.mean((pr - ac) ** 2)), "mae": float(np.mean(np.abs(pr - ac))),
            "bias": float(np.mean(pr - ac)), "corr": float(np.corrcoef(pr, ac)[0, 1])}


def baseline_rmse(season: Season, kind: str, cuts, horizon: int, last_gw: int, min_minutes: int = 90) -> float:
    """Naive predictors: 'ppg' = season points per game so far, 'form4' = last four games."""
    errs = []
    for c in cuts:
        for rows in season.hist.values():
            h = [r for r in rows if r["round"] <= c]
            if sum(r["minutes"] for r in h) < min_minutes:
                continue
            pts = [r["total_points"] for r in h]
            guess = float(np.mean(pts if kind == "ppg" else pts[-4:]))
            errs += [(guess - r["total_points"]) ** 2 for r in rows if c < r["round"] <= min(c + horizon, last_gw)]
    return math.sqrt(float(np.mean(errs)))


def fit_calibration(rows, k: float = 20.0) -> dict:
    """{(pos, component): factor}; k pseudo-points shrink thinly-populated cells towards 1.0."""
    cal = {}
    for pos in POS:
        sub = [r for r in rows if r.pos == pos]
        for comp in COMPONENTS:
            sp, sa = sum(r.comps[comp] for r in sub), sum(r.actual[comp] for r in sub)
            if abs(sp) < 1e-9:
                continue
            s = 1.0 if sp > 0 else -1.0
            cal[(pos, comp)] = (sa + k * s) / (sp + k * s)
    return cal


def top_k_actual(rows, calibration=None, k: int = 12) -> float:
    """Average actual points of the k highest-projected players in each (cutoff, round)."""
    by: dict = {}
    for r, p in zip(rows, predicted(rows, calibration)):
        by.setdefault((r.cut, r.rnd), []).append((p, r.points))
    return float(np.mean([np.mean([a for _, a in sorted(v, reverse=True)[:k]]) for v in by.values()]))


def time_split(rows, split_round: int = 6) -> dict:
    train, test = [r for r in rows if r.rnd <= split_round], [r for r in rows if r.rnd > split_round]
    cal = fit_calibration(train)
    return {"train_n": len(train), "test_n": len(test), "uncalibrated": metrics(test), "calibrated": metrics(test, cal)}


def calibration_toml(cal: dict) -> str:
    out = []
    for pos, name in POS.items():
        items = [(c, cal[(pos, c)]) for c in COMPONENTS if (pos, c) in cal]
        if items:
            out += [f"[calibration.{name}]"] + [f"{c} = {v:.3f}" for c, v in items] + [""]
    return "\n".join(out)
