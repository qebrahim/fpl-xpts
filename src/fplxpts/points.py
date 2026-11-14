"""Turn player rates + a fixture into expected FPL points, as additive components.

Components (see constants.COMPONENTS): appearance, goals, assists, clean sheet, goals-conceded penalty,
defensive contribution, bonus (driven by the expected goals/assists/clean sheet/saves, see bonus.py), GK saves, yellow cards. Each can be calibrated by a per-position factor.
"""
from __future__ import annotations

import math

from .bonus import expected_bonus
from .constants import COMPONENTS, CS_PTS, DC_THRESHOLD, GOAL_PTS
from .teams import TeamState, damped_opp_xg, opp_of


def expected_floor(lam: float, per: int, kmax: int = 15) -> float:
    """E[floor(k / per)] for k ~ Poisson(lam): points that are awarded per `per` whole events."""
    s, p = 0.0, math.exp(-lam)
    for k in range(kmax):
        s += (k // per) * p
        p *= lam / (k + 1)
    return s


def gc_penalty(lam: float) -> float:
    """Expected goals-conceded penalty points (-1 per 2 goals conceded)."""
    return expected_floor(lam, 2)


def save_points(lam: float) -> float:
    """Expected save points (+1 per 3 whole saves), not saves / 3: two saves earn nothing."""
    return expected_floor(lam, 3, kmax=40)


def dc_hit_vs(hit: float, opp_factor: float, faced_factor: float) -> float:
    """Player's DC hit probability against one opponent: own rate x opponent factor / factor of past opponents."""
    return min(1.0, hit * opp_factor / faced_factor)


def anchored(att_m: float, opp_m: float, opp_xg: float, model_for: float, fx: tuple, lg_opp: float,
             gamma: float = 1.0) -> tuple:
    """Matchup terms (att_m, opp_m, opp_xg, cs_xg) for a fixture whose team expected goals are fixed at
    fx = (xg_for, xg_against) instead of the rating products (model_for = lg_v * att_T * dfn_opp, opp_xg).

    The team's own goals enter only as a ratio to the ratings' value, so att_m (relative to the environment the
    player's rates were earned in) becomes att_m * xg_for / model_for = xg_for / (att_T * pn_att_T): the player-rate
    normalisation is unchanged. Saves scale by xg_against / opp_xg; goals conceded use xg_against; the clean-sheet
    xG keeps the opp_xg_gamma damping of its multiplier xg_against / lg_opp. fx equal to the model's values gives
    back the unanchored terms.
    """
    xg_for, xg_against = fx
    cs_xg = lg_opp * (xg_against / lg_opp) ** gamma
    return att_m * xg_for / model_for, opp_m * xg_against / opp_xg, xg_against, cs_xg


def components(p: dict, venue: str, opp: int, st: TeamState) -> dict:
    """Expected points by component for player rates `p` playing `opp` at `venue` ('h' or 'a')."""
    lg, T, pos, mf = st.lg, p["team"], p["pos"], p["mf"]
    att_m = lg[venue] * st.dfn[opp] / st.pn_att[T]          # attacking environment vs the one the rates were earned in
    opp_xg = lg[opp_of(venue)] * st.att[opp] * st.dfn[T]     # opponent's expected goals vs this team
    cs_xg = damped_opp_xg(lg[opp_of(venue)], st.att[opp], st.dfn[T], st.opp_xg_gamma)  # damped, for clean sheets
    opp_m = lg[opp_of(venue)] * st.att[opp] / st.pn_opp[T]
    fx = st.fixture_xg.get((T, opp, venue))
    if fx is not None:                                        # bookmaker-anchored fixture (teams.anchor_fixtures)
        att_m, opp_m, opp_xg, cs_xg = anchored(att_m, opp_m, opp_xg, lg[venue] * st.att[T] * st.dfn[opp], fx,
                                               lg[opp_of(venue)], st.opp_xg_gamma)
    goals, assists = p["xg90"] * mf * att_m, p["xa90"] * mf * att_m
    p_cs = math.exp(-cs_xg) * p["p60"]                        # P(clean sheet and 60+ minutes)
    saves = p["sav90"] * mf * opp_m if pos == 1 else 0.0
    return {
        "app": p["app"],
        "goal": goals * GOAL_PTS[pos],
        "assist": assists * 3,
        "cs": p_cs * CS_PTS[pos],
        "gc": -(gc_penalty(opp_xg * mf) if pos in (1, 2) else 0.0),
        "dc": 2 * dc_hit_vs(p["hit"], st.dc_opp.get(opp, 1.0), st.pn_dc.get(T, 1.0)) * p["p60"],
        "bonus": expected_bonus(p["bon_base90"], p["bon_k"], mf, {"goal": goals, "assist": assists, "cs": p_cs, "sav": saves}),
        "sav": save_points(saves),
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
