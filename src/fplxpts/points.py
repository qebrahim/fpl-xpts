"""Turn player rates + a fixture into expected FPL points, as additive components.

Components (see constants.COMPONENTS): appearance, goals, assists, clean sheet, goals-conceded penalty,
defensive contribution, bonus (driven by the expected goals/assists/clean sheet/saves, see bonus.py), GK saves, yellow cards. Each can be calibrated by a per-position factor.
"""
from __future__ import annotations

import math

from .bonus import expected_bonus
from .constants import COMPONENTS, CS_PTS, DC_THRESHOLD, GOAL_PTS
from .teams import TeamState, opp_of


def gc_penalty(lam: float) -> float:
    """E[floor(k/2)] for k ~ Poisson(lam): expected goals-conceded penalty points (-1 per 2 goals)."""
    s, p = 0.0, math.exp(-lam)
    for k in range(15):
        s += (k // 2) * p
        p *= lam / (k + 1)
    return s


def components(p: dict, venue: str, opp: int, st: TeamState) -> dict:
    """Expected points by component for player rates `p` playing `opp` at `venue` ('h' or 'a')."""
    lg, T, pos, mf = st.lg, p["team"], p["pos"], p["mf"]
    att_m = lg[venue] * st.dfn[opp] / st.pn_att[T]          # attacking environment vs the one the rates were earned in
    opp_xg = lg[opp_of(venue)] * st.att[opp] * st.dfn[T]     # opponent's expected goals vs this team
    opp_m = lg[opp_of(venue)] * st.att[opp] / st.pn_opp[T]
    goals, assists = p["xg90"] * mf * att_m, p["xa90"] * mf * att_m
    p_cs = math.exp(-opp_xg) * p["p60"]                      # P(clean sheet and 60+ minutes)
    saves = p["sav90"] * mf * opp_m if pos == 1 else 0.0
    return {
        "app": p["app"],
        "goal": goals * GOAL_PTS[pos],
        "assist": assists * 3,
        "cs": p_cs * CS_PTS[pos],
        "gc": -(gc_penalty(opp_xg * mf) if pos in (1, 2) else 0.0),
        "dc": 2 * p["hit"] * p["p60"],
        "bonus": expected_bonus(p["bon_base90"], p["bon_k"], mf, {"goal": goals, "assist": assists, "cs": p_cs, "sav": saves}),
        "sav": saves / 3,
        "yc": -p["yc90"] * mf,
    }


def actual_components(row: dict, pos: int) -> dict:
    """The same components computed from what really happened in a match row (for backtests)."""
    m = row["minutes"]
    return {
        "app": 2 if m >= 60 else 1 if m > 0 else 0,
        "goal": row["goals_scored"] * GOAL_PTS[pos],
        "assist": row["assists"] * 3,
        "cs": row["clean_sheets"] * CS_PTS[pos] if m >= 60 else 0,
        "gc": -(row["goals_conceded"] // 2) if pos in (1, 2) else 0,
        "dc": 2 if pos != 1 and row["defensive_contribution"] >= DC_THRESHOLD[pos] else 0,
        "bonus": row["bonus"],
        "sav": row["saves"] // 3 if pos == 1 else 0,
        "yc": -row["yellow_cards"],
    }


def total(comps: dict, pos: int, calibration: dict | None = None) -> float:
    cal = calibration or {}
    return sum(comps[k] * cal.get((pos, k), 1.0) for k in COMPONENTS)
