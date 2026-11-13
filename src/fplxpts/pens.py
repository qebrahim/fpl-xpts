"""Penalty handling.

FPL exposes penalties MISSED but not penalties scored, so penalty goals are supplied by the user (config)
or an external source. A penalty is worth ~0.76 xG, so a taker's raw xG is inflated by however many they
have won so far. We (1) strip taken penalties out of the history and (2) hand each club's primary taker a
normal forward-looking penalty share, instead of extrapolating a lucky run of penalties.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .config import Config
from .data import Season


@dataclass
class PenModel:
    taken: dict      # player id -> penalties taken this season (scored + missed)
    scored: dict     # player id -> penalty goals
    primary: dict    # team id -> primary taker's player id


def build_pen_model(season: Season, pen_goals: list) -> PenModel:
    """pen_goals: [(name, team_short, n)] penalty goals scored this season."""
    scored = {season.find(name, team): n for name, team, n in pen_goals}
    taken = {}
    for e in season.elements.values():
        n = scored.get(e["id"], 0) + e["penalties_missed"]
        if n:
            taken[e["id"]] = n
    primary = {}
    for tm in season.teams:
        c = [e for e in season.elements.values() if e["team"] == tm and e["element_type"] != 1 and taken.get(e["id"], 0) > 0]
        if c:
            primary[tm] = max(c, key=lambda e: (taken[e["id"]], -(e["penalties_order"] or 9)))["id"]
        else:
            o1 = [e for e in season.elements.values() if e["team"] == tm and e["penalties_order"] == 1 and e["element_type"] != 1]
            if o1:
                primary[tm] = o1[0]["id"]
    return PenModel(taken, scored, primary)


def strip_penalties(season: Season, pm: PenModel, cfg: Config) -> dict:
    """Copy of the match history with each taken penalty's xG (and goal) removed.

    Scored penalties are removed from the highest-xG games with a goal; misses from the highest-xG games
    without one (a heuristic: FPL does not say which match each penalty was in).
    """
    pen_xg = cfg.model.pen_xg
    adj = copy.deepcopy(season.hist)
    for pid in pm.taken:
        if pid not in adj:
            continue
        sc, ms, used = pm.scored.get(pid, 0), season.elements[pid]["penalties_missed"], set()
        for r in sorted([r for r in adj[pid] if r["goals_scored"] >= 1], key=lambda r: -float(r["expected_goals"]))[:sc]:
            r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - pen_xg))
            r["goals_scored"] -= 1
            used.add(r["round"])
        for r in sorted([r for r in adj[pid] if r["round"] not in used and r["goals_scored"] == 0], key=lambda r: -float(r["expected_goals"]))[:ms]:
            r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - pen_xg))
    return adj
