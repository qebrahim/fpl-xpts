"""Per-player rates (xG, xA, bonus baseline, saves, cards, minutes) shrunk towards a prior.

prior = position-average rate (prior_min pseudo-minutes) blended with the player's own last-season rate
(weight prior_lambda x last-season minutes, capped). Recent games count more (form_halflife).
"""
from __future__ import annotations

from .bonus import fit_bonus_coefs, residual
from .config import Config
from .constants import DC_THRESHOLD
from .data import Season

posgrp = lambda p: min(p, 3)


def _shrink(stat, prior_pm, last_pm, mins, wl, m):
    """Posterior rate per 90: observed stat blended with the position prior and the last-season prior."""
    return (stat + prior_pm * m.prior_min + last_pm * wl) / (mins + m.prior_min + wl) * 90


def last_season_prior(past_rows: list, cfg: Config):
    """(xG per minute, xA per minute, weighted minutes) over the configured past seasons."""
    wsum = xg = xa = 0.0
    for r in past_rows:
        w = cfg.model.prior_seasons.get(r["season_name"])
        if not w or r["minutes"] < cfg.model.prior_min_season_minutes:
            continue
        wsum += w * r["minutes"]
        xg += w * float(r["expected_goals"])
        xa += w * float(r["expected_assists"])
    return (0.0, 0.0, 0.0) if wsum == 0 else (xg / wsum, xa / wsum, wsum)


def weigh(rows: list, halflife: float | None) -> list:
    """Down-weight old games by scaling their minutes and counting stats."""
    if not halflife:
        return rows
    n, out = len(rows), []
    for i, r in enumerate(rows):
        w = 0.5 ** ((n - 1 - i) / halflife)
        q = dict(r)
        q["minutes"] = r["minutes"] * w
        for k in ("expected_goals", "expected_assists"):
            q[k] = float(r[k]) * w
        for k in ("bonus", "bonus_resid", "saves", "yellow_cards"):
            q[k] = r.get(k, 0.0) * w
        out.append(q)
    return out


def build_players(season: Season, cut: int, cfg: Config, hist: dict | None = None) -> dict:
    """Rates for every player with enough minutes, using only matches up to gameweek `cut`.

    `hist` lets callers pass an adjusted history (e.g. with penalties stripped out).
    """
    m = cfg.model
    src = hist if hist is not None else season.hist
    H = {p: [r for r in rows if r["round"] <= cut] for p, rows in src.items()}
    live = [p for p in H if sum(r["minutes"] for r in H[p]) >= m.min_live_minutes]
    els = season.elements

    pool = {}
    for pos in (1, 2, 3, 4):
        es = [p for p in live if els[p]["element_type"] == pos]
        mins = sum(r["minutes"] for p in es for r in H[p])
        pool[pos] = {k: sum(float(r[col]) for p in es for r in H[p]) / mins
                     for k, col in (("xg", "expected_goals"), ("xa", "expected_assists"), ("sav", "saves"))}
    # bonus by how it is earned: per-position marginal bonus per event, and each match's unexplained remainder
    bcoef = {pos: fit_bonus_coefs([r for p in live if els[p]["element_type"] == pos for r in H[p]], pos) for pos in (1, 2, 3, 4)}
    for p in live:
        pos = els[p]["element_type"]
        H[p] = [{**r, "bonus_resid": residual(r, pos, bcoef[pos])} for r in H[p]]
    hits = {1: [], 2: [], 3: []}
    for p in live:
        pos = els[p]["element_type"]
        for r in H[p]:
            if r["minutes"] >= 60:
                hits[posgrp(pos)].append(1 if r["defensive_contribution"] >= DC_THRESHOLD.get(pos, 99) else 0)
    pool_hit = {g: (sum(v) / len(v) if v else 0.0) for g, v in hits.items()}

    out = {}
    for pid in live:
        pos, team = els[pid]["element_type"], els[pid]["team"]
        hr = H[pid]
        hrw = weigh(hr, m.form_halflife)
        mins = sum(r["minutes"] for r in hrw)
        lxg, lxa, lw = last_season_prior(season.past.get(pid, []), cfg)
        wl = m.prior_lambda * min(lw, m.prior_cap_minutes)

        hrs = [1 if r["defensive_contribution"] >= DC_THRESHOLD.get(pos, 99) else 0 for r in hr if r["minutes"] >= 60]
        hit = 0.0 if pos == 1 else (sum(hrs) + pool_hit[posgrp(pos)] * m.prior_apps) / (len(hrs) + m.prior_apps)
        last = hr[-5:]
        out[pid] = {
            "pos": pos, "team": team,
            "xg90": 0.0 if pos == 1 else _shrink(sum(float(r["expected_goals"]) for r in hrw), pool[pos]["xg"], lxg, mins, wl, m),
            "xa90": 0.0 if pos == 1 else _shrink(sum(float(r["expected_assists"]) for r in hrw), pool[pos]["xa"], lxa, mins, wl, m),
            "bon_k": bcoef[pos],
            "bon_base90": bcoef[pos]["base"] + sum(r["bonus_resid"] for r in hrw) / (mins + m.prior_min) * 90,
            "sav90": (sum(r["saves"] for r in hrw) + pool[pos]["sav"] * m.prior_min) / (mins + m.prior_min) * 90 if pos == 1 else 0.0,
            "yc90": sum(r["yellow_cards"] for r in hrw) / max(mins, 1) * 90,
            "hit": hit,
            "mf": sum(r["minutes"] for r in last) / len(last) / 90,
            "app": sum((2 if r["minutes"] >= 60 else 1 if r["minutes"] > 0 else 0) for r in last) / len(last),
            "p60": sum(1 for r in last if r["minutes"] >= 60) / len(last),
        }
    return out
