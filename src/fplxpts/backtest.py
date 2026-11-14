"""Walk-forward backtest and calibration fit.

For each cutoff gameweek c the model is rebuilt using ONLY data up to c, then asked to predict the next
`horizon` gameweeks; predictions are compared with what happened. Calibration factors are the ratio of
mean actual to mean predicted points per (position, component), shrunk towards 1 with pseudo-points.
They are judged out of sample by refitting them at every cutoff on outcomes known by then
(`walk_forward_metrics`) and by a single time split (fit on early target rounds, test on later ones).

Bookmaker odds (`odds_rounds` {round: {(home, away): MatchOdds}}, from Football-Data.co.uk): at cutoff c only the
odds for round c + 1 are passed to the model (`odds.available_at`), as a forecaster would really have them.

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
from .odds import available_at
from .players import build_players
from .points import actual_components, components, total
from .teams import fixture_xg, team_state

Row = namedtuple("Row", "pid cut rnd pos comps actual points")
TeamRow = namedtuple("TeamRow", "cut rnd fixture team opp venue lam goals")


def at_club(p: dict, row: dict) -> dict:
    """Player rates `p` placed at the club he played for in match `row` (archive rows carry `team`; a player who
    moved clubs mid-season is projected with his new club's team terms). Live rows have no team: `p` unchanged."""
    t = row.get("team")
    return p if t is None or t == p["team"] else {**p, "team": t}


def played_rounds(season: Season) -> list:
    """Rounds with at least one finished fixture with team xG (a fully postponed round, e.g. 2022/23 GW7, is left
    out so that it does not repeat the previous cutoff)."""
    return sorted({x["ev"] for x in season.fin})


def evaluate(season: Season, cfg: Config, cuts=None, horizon: int = 5, last_gw: int | None = None,
             odds_rounds: dict | None = None) -> list:
    last_gw = last_gw or season.current_gw
    cuts = cuts or list(range(1, last_gw))
    rows = []
    for c in cuts:
        odds = available_at(odds_rounds, c) if odds_rounds else None
        players, st = build_players(season, c, cfg), team_state(season, c, cfg, odds)
        for pid, p in players.items():
            for r in season.hist[pid]:
                if c < r["round"] <= min(c + horizon, last_gw):
                    comps = components(at_club(p, r), "h" if r["was_home"] else "a", r["opponent_team"], st)
                    rows.append(Row(pid, c, r["round"], p["pos"], comps, actual_components(r, p["pos"]), r["total_points"]))
    return rows


def team_rows(season: Season, cfg: Config, cuts, horizon: int, last_gw: int, odds_rounds: dict | None = None) -> list:
    """One row per team per finished fixture in rounds c+1..c+horizon after each cutoff c, from the defending side:
    the goals the team is expected to concede as the model uses them (anchored if odds were available at c) and the
    goals it conceded (so P(clean sheet) = exp(-lam))."""
    out = []
    for c in cuts:
        st = team_state(season, c, cfg, available_at(odds_rounds, c) if odds_rounds else None)
        for f in season.fixtures:
            ev = f.get("event")
            if not ev or not c < ev <= min(c + horizon, last_gw) or not f.get("finished") or f.get("team_h_score") is None:
                continue
            h, a = f["team_h"], f["team_a"]
            out.append(TeamRow(c, ev, f["id"], h, a, "h", fixture_xg(st, h, a, "h")[1], f["team_a_score"]))
            out.append(TeamRow(c, ev, f["id"], a, h, "a", fixture_xg(st, a, h, "a")[1], f["team_h_score"]))
    return out


def poisson_logpmf(k: int, lam: float) -> float:
    return k * math.log(lam) - lam - math.lgamma(k + 1)


def team_errors(rows) -> dict:
    """Per-row squared goal error, clean-sheet Brier (P(conceding 0) = exp(-lam)) and Poisson log-loss, as arrays
    (for paired bootstraps)."""
    lam, g = np.array([r.lam for r in rows]), np.array([r.goals for r in rows])
    return {"goals_se": (lam - g) ** 2, "cs_brier": (np.exp(-lam) - (g == 0)) ** 2,
            "logloss": -np.array([poisson_logpmf(int(k), x) for k, x in zip(g, lam)])}


def team_metrics(rows) -> dict:
    e = team_errors(rows)
    return {"n": len(rows), "goals_rmse": math.sqrt(e["goals_se"].mean()), "cs_brier": float(e["cs_brier"].mean()),
            "logloss": float(e["logloss"].mean())}


def paired_bootstrap(diff, groups, reps: int = 2000, seed: int = 1) -> tuple:
    """Mean of per-row differences and a 95% interval, resampling whole groups (players, matches) with replacement."""
    diff, groups = np.asarray(diff, dtype=float), np.asarray(groups)
    keys, inv = np.unique(groups, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=diff), np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(reps, len(keys)))
    boot = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return float(diff.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


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


def shrunk_ratio(sum_actual: float, sum_pred: float, k: float, target: float = 1.0) -> float:
    """(sum_actual + k * target) / (sum_pred + k) with k pseudo-points of 'actual = target x predicted'
    (sign-matched for the negative components gc/yc). k = 0 is the raw ratio; as k grows the factor tends to
    `target` (1.0 by default, i.e. no calibration; a prior factor such as last season's otherwise). The pull is
    strong for cells with few expected points (e.g. forward assists) and negligible for large ones."""
    s = 1.0 if sum_pred > 0 else -1.0
    return (sum_actual + k * s * target) / (sum_pred + k * s)


def fit_calibration(rows, k: float = CAL_K, prior: dict | None = None) -> dict:
    """{(pos, component): factor} from backtest rows; k pseudo-points shrink each factor towards 1.0, or towards
    `prior[(pos, component)]` when a prior is given (1.0 for a cell missing from it, e.g. dc from a season without
    defensive-contribution points). A cell with nothing predicted gets its prior factor (no factor = 1.0 without one).

    k = 0 gives the raw mean(actual) / mean(predicted); k = 20 was the method before 2026-11."""
    prior = prior or {}
    cal = {}
    for pos in POS:
        sub = [r for r in rows if r.pos == pos]
        for comp in COMPONENTS:
            sp, sa = sum(r.comps[comp] for r in sub), sum(r.actual[comp] for r in sub)
            if abs(sp) < 1e-9:
                if (pos, comp) in prior:
                    cal[(pos, comp)] = prior[(pos, comp)]
                continue
            cal[(pos, comp)] = shrunk_ratio(sa, sp, k, prior.get((pos, comp), 1.0))
    return cal


def walk_forward_calibration(rows, k: float = CAL_K, min_rows: int = 1, prior: dict | None = None) -> dict:
    """{cutoff: factors} where the factors for cutoff c are fitted only on rows whose TARGET round is <= c,
    i.e. on outcomes already known at c (those rows were predicted at earlier cutoffs, c' < round <= c).
    A row predicted at c itself (target round > c) is never in its own training set. Fewer than `min_rows`
    training rows -> the prior's factors ({} = every factor 1.0 without a prior). `prior` (e.g. last season's
    full-season factors) must not use outcomes of the season being tested."""
    out = {}
    for c in sorted({r.cut for r in rows}):
        train = [r for r in rows if r.rnd <= c]
        out[c] = fit_calibration(train, k, prior) if len(train) >= max(min_rows, 1) else dict(prior or {})
    return out


def walk_forward_predicted(rows, k: float = CAL_K, min_rows: int = 1, prior: dict | None = None):
    """Out-of-sample calibrated predictions: each row uses the factors fitted at its own cutoff."""
    cals = walk_forward_calibration(rows, k, min_rows, prior)
    return np.array([total(r.comps, r.pos, cals[r.cut]) for r in rows])


def walk_forward_metrics(rows, k: float = CAL_K, min_rows: int = 1, prior: dict | None = None) -> dict:
    pr = walk_forward_predicted(rows, k, min_rows, prior)
    return score(rows, pr) | {"top12": top_k_actual(rows, pred=pr)}


def top_k_actual(rows, calibration=None, k: int = 12, pred=None) -> float:
    """Average actual points of the k highest-projected players in each (cutoff, round). A player with two matches
    in the round (double gameweek) counts once, with both matches' projected and actual points summed."""
    pp: dict = {}
    for r, p in zip(rows, predicted(rows, calibration) if pred is None else pred):
        q = pp.setdefault((r.cut, r.rnd, r.pid), [0.0, 0.0])
        q[0] += p
        q[1] += r.points
    by: dict = {}
    for (c, rnd, _), (p, a) in pp.items():
        by.setdefault((c, rnd), []).append((p, a))
    return float(np.mean([np.mean([a for _, a in sorted(v, reverse=True)[:k]]) for v in by.values()]))


def time_split(rows, split_round: int = 6, k: float = CAL_K, prior: dict | None = None) -> dict:
    train, test = [r for r in rows if r.rnd <= split_round], [r for r in rows if r.rnd > split_round]
    cal = fit_calibration(train, k, prior)
    return {"train_n": len(train), "test_n": len(test), "uncalibrated": metrics(test), "calibrated": metrics(test, cal)}


def calibration_toml(cal: dict) -> str:
    out = []
    for pos, name in POS.items():
        items = [(c, cal[(pos, c)]) for c in COMPONENTS if (pos, c) in cal]
        if items:
            out += [f"[calibration.{name}]"] + [f"{c} = {v:.3f}" for c, v in items] + [""]
    return "\n".join(out)
