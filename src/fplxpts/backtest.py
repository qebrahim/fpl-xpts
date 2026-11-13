"""Walk-forward backtest and calibration fit.

For each cutoff gameweek c the model is rebuilt using ONLY data up to c, then asked to predict the next
`horizon` gameweeks; predictions are compared with what happened. Calibration factors are the ratio of
mean actual to mean predicted points per (position, component), shrunk towards 1 with pseudo-points.
They are judged out of sample by refitting them at every cutoff on outcomes known by then
(`walk_forward_metrics`) and by a single time split (fit on early target rounds, test on later ones).

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


# pseudo-points shrinking each calibration factor towards 1.0 (chosen by walk-forward backtest, docs/BACKTEST.md)
CAL_K = 160.0


def predicted(rows, calibration=None):
    return np.array([total(r.comps, r.pos, calibration) for r in rows])


def score(rows, pred) -> dict:
    """Error metrics of predictions `pred` (one per row) against the points actually scored."""
    pr, ac = np.asarray(pred, dtype=float), np.array([r.points for r in rows], dtype=float)
    return {"n": len(rows), "rmse": math.sqrt(np.mean((pr - ac) ** 2)), "mae": float(np.mean(np.abs(pr - ac))),
            "bias": float(np.mean(pr - ac)), "corr": float(np.corrcoef(pr, ac)[0, 1])}


def metrics(rows, calibration=None) -> dict:
    return score(rows, predicted(rows, calibration))


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


def shrunk_ratio(sum_actual: float, sum_pred: float, k: float) -> float:
    """(sum_actual + k) / (sum_pred + k) with k pseudo-points of 'predicted = actual' (sign-matched for the
    negative components gc/yc). k = 0 is the raw ratio; as k grows the factor tends to 1.0. The pull towards 1
    is strong for cells with few expected points (e.g. forward assists) and negligible for large ones."""
    s = 1.0 if sum_pred > 0 else -1.0
    return (sum_actual + k * s) / (sum_pred + k * s)


def fit_calibration(rows, k: float = CAL_K) -> dict:
    """{(pos, component): factor} from backtest rows; k pseudo-points shrink each factor towards 1.0.

    k = 0 gives the raw mean(actual) / mean(predicted); k = 20 was the method before 2026-11."""
    cal = {}
    for pos in POS:
        sub = [r for r in rows if r.pos == pos]
        for comp in COMPONENTS:
            sp, sa = sum(r.comps[comp] for r in sub), sum(r.actual[comp] for r in sub)
            if abs(sp) < 1e-9:
                continue
            cal[(pos, comp)] = shrunk_ratio(sa, sp, k)
    return cal


def walk_forward_calibration(rows, k: float = CAL_K, min_rows: int = 1) -> dict:
    """{cutoff: factors} where the factors for cutoff c are fitted only on rows whose TARGET round is <= c,
    i.e. on outcomes already known at c (those rows were predicted at earlier cutoffs, c' < round <= c).
    A row predicted at c itself (target round > c) is never in its own training set. Fewer than `min_rows`
    training rows -> {} (every factor 1.0)."""
    out = {}
    for c in sorted({r.cut for r in rows}):
        train = [r for r in rows if r.rnd <= c]
        out[c] = fit_calibration(train, k) if len(train) >= max(min_rows, 1) else {}
    return out


def walk_forward_predicted(rows, k: float = CAL_K, min_rows: int = 1):
    """Out-of-sample calibrated predictions: each row uses the factors fitted at its own cutoff."""
    cals = walk_forward_calibration(rows, k, min_rows)
    return np.array([total(r.comps, r.pos, cals[r.cut]) for r in rows])


def walk_forward_metrics(rows, k: float = CAL_K, min_rows: int = 1) -> dict:
    pr = walk_forward_predicted(rows, k, min_rows)
    return score(rows, pr) | {"top12": top_k_actual(rows, pred=pr)}


def top_k_actual(rows, calibration=None, k: int = 12, pred=None) -> float:
    """Average actual points of the k highest-projected players in each (cutoff, round)."""
    by: dict = {}
    for r, p in zip(rows, predicted(rows, calibration) if pred is None else pred):
        by.setdefault((r.cut, r.rnd), []).append((p, r.points))
    return float(np.mean([np.mean([a for _, a in sorted(v, reverse=True)[:k]]) for v in by.values()]))


def time_split(rows, split_round: int = 6, k: float = CAL_K) -> dict:
    train, test = [r for r in rows if r.rnd <= split_round], [r for r in rows if r.rnd > split_round]
    cal = fit_calibration(train, k)
    return {"train_n": len(train), "test_n": len(test), "uncalibrated": metrics(test), "calibrated": metrics(test, cal)}


def calibration_toml(cal: dict) -> str:
    out = []
    for pos, name in POS.items():
        items = [(c, cal[(pos, c)]) for c in COMPONENTS if (pos, c) in cal]
        if items:
            out += [f"[calibration.{name}]"] + [f"{c} = {v:.3f}" for c, v in items] + [""]
    return "\n".join(out)
