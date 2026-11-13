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


def counts_for_dc(row: dict) -> bool:
    """Only 60+ minute appearances count towards defensive-contribution hit rates."""
    return row["minutes"] >= 60


def dc_hit(row: dict, pos: int) -> int:
    """1 if the match row reached the position's defensive-contribution threshold (never for GKs)."""
    return 1 if row["defensive_contribution"] >= DC_THRESHOLD.get(pos, 99) else 0


def pool_hit_rates(H: dict, live: list, els: dict) -> dict:
    """League DC hit rate per position group (1 GK, 2 DEF, 3 MID+FWD) over 60+ minute appearances in `H`."""
    hits: dict = {1: [], 2: [], 3: []}
    for p in live:
        pos = els[p]["element_type"]
        hits[posgrp(pos)] += [dc_hit(r, pos) for r in H[p] if counts_for_dc(r)]
    return {g: (sum(v) / len(v) if v else 0.0) for g, v in hits.items()}


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


def zero_runs(rows: list) -> list[tuple[int, int]]:
    """Maximal runs of consecutive 0-minute rows, as (start, end) index pairs: rows[start:end]."""
    out, i, n = [], 0, len(rows)
    while i < n:
        if rows[i]["minutes"] > 0:
            i += 1
            continue
        j = i
        while j < n and rows[j]["minutes"] == 0:
            j += 1
        out.append((i, j))
        i = j
    return out


def absence_rows(rows: list, starts_before: int, starts_after: int = 1) -> set[int]:
    """Indices of 0-minute rows that look like an injury/suspension absence rather than non-selection.

    A run of 0-minute matches counts as an absence when the player started each of his last
    `starts_before` played matches before it and each of his first `starts_after` played matches after it
    (an established starter who has come back into the side). A run is never dropped before the player
    has played again, so runs he has not yet returned from keep counting (with `starts_after >= 1` so do
    runs he returned from only as a substitute). `starts_before = 0` turns this off.
    FPL match rows have no injury flag, so this is inferred from starts alone.
    """
    if starts_before <= 0:
        return set()
    played = [k for k, r in enumerate(rows) if r["minutes"] > 0]
    out: set[int] = set()
    for i, j in zero_runs(rows):
        before = [k for k in played if k < i][-starts_before:]
        after = [k for k in played if k >= j]
        if (len(before) == starts_before and after and len(after) >= starts_after
                and all(rows[k]["starts"] for k in before + after[:starts_after])):
            out.update(range(i, j))
    return out


def minutes_window(rows: list, n: int = 5, starts_before: int = 0, starts_after: int = 1) -> list:
    """The last `n` match rows used for the minutes model, skipping inferred injury/suspension absences."""
    skip = absence_rows(rows, starts_before, starts_after)
    return [r for k, r in enumerate(rows) if k not in skip][-n:]


def minutes_inputs(last: list) -> dict:
    """Minutes share `mf`, expected appearance points `app` and P(60+ minutes) `p60` from match rows."""
    return {
        "mf": sum(r["minutes"] for r in last) / len(last) / 90,
        "app": sum((2 if r["minutes"] >= 60 else 1 if r["minutes"] > 0 else 0) for r in last) / len(last),
        "p60": sum(1 for r in last if r["minutes"] >= 60) / len(last),
    }


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
    pool_hit = pool_hit_rates(H, live, els)

    out = {}
    for pid in live:
        pos, team = els[pid]["element_type"], els[pid]["team"]
        hr = H[pid]
        hrw = weigh(hr, m.form_halflife)
        mins = sum(r["minutes"] for r in hrw)
        lxg, lxa, lw = last_season_prior(season.past.get(pid, []), cfg)
        wl = m.prior_lambda * min(lw, m.prior_cap_minutes)

        hrs = [dc_hit(r, pos) for r in hr if counts_for_dc(r)]
        hit = 0.0 if pos == 1 else (sum(hrs) + pool_hit[posgrp(pos)] * m.prior_apps) / (len(hrs) + m.prior_apps)
        last = minutes_window(hr, 5, m.absence_starts_before, m.absence_starts_after)
        out[pid] = {
            "pos": pos, "team": team,
            "xg90": 0.0 if pos == 1 else _shrink(sum(float(r["expected_goals"]) for r in hrw), pool[pos]["xg"], lxg, mins, wl, m),
            "xa90": 0.0 if pos == 1 else _shrink(sum(float(r["expected_assists"]) for r in hrw), pool[pos]["xa"], lxa, mins, wl, m),
            "bon_k": bcoef[pos],
            "bon_base90": bcoef[pos]["base"] + sum(r["bonus_resid"] for r in hrw) / (mins + m.prior_min) * 90,
            "sav90": (sum(r["saves"] for r in hrw) + pool[pos]["sav"] * m.prior_min) / (mins + m.prior_min) * 90 if pos == 1 else 0.0,
            "yc90": sum(r["yellow_cards"] for r in hrw) / max(mins, 1) * 90,
            "hit": hit,
            **minutes_inputs(last),
        }
    return out
