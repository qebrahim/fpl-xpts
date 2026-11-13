"""Lineup selection and single-transfer search on top of a Projection."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Projection


def best_xi_value(values: list, elements: dict) -> float:
    """Best 11 from a 15-man squad: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD. values = [(player id, points)]."""
    by = {pos: sorted((v for p, v in values if elements[p]["element_type"] == pos), reverse=True) for pos in (1, 2, 3, 4)}
    best = 0.0
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3 and d <= len(by[2]) and m <= len(by[3]) and f <= len(by[4]):
                best = max(best, sum(by[2][:d]) + sum(by[3][:m]) + sum(by[4][:f]))
    return by[1][0] + best


@dataclass
class Lineup:
    gw: int
    formation: str
    total: float
    xi: list           # player ids, GK first then DEF/MID/FWD by points
    bench: list        # outfield bench in order (the spare keeper is last)
    captain: int
    vice: int


def pick_lineup(squad: list, proj: Projection, gw: int) -> Lineup:
    els = proj.season.elements
    val = lambda p: proj.series.get(p, {}).get(gw, 0.0)
    by = {pos: sorted((p for p in squad if els[p]["element_type"] == pos), key=lambda p: -val(p)) for pos in (1, 2, 3, 4)}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if not (1 <= f <= 3):
                continue
            xi = by[1][:1] + by[2][:d] + by[3][:m] + by[4][:f]
            s = sum(val(p) for p in xi)
            if best is None or s > best[0]:
                best = (s, d, m, f, xi)
    s, d, m, f, xi = best
    outfield_xi = sorted(xi[1:], key=lambda p: -val(p))
    bench = sorted((p for p in squad if p not in xi and els[p]["element_type"] != 1), key=lambda p: -val(p)) + by[1][1:]
    return Lineup(gw, f"{d}-{m}-{f}", s, xi, bench, outfield_xi[0], outfield_xi[1])


@dataclass
class Move:
    out: int
    into: int
    gains: tuple       # points gained over each requested window
    cost: float        # change in squad value, GBP millions (negative = frees money)


def single_moves(squad: list, proj: Projection, windows=((11, 15), (11, 18)), max_cost: float = 1.5,
                 min_minutes: int = 270, min_mf: float = 0.7, club_limit: int = 3) -> list:
    """Every same-position single swap, scored by the change in best-XI points over each window."""
    els = proj.season.elements
    price = lambda p: els[p]["now_cost"] / 10
    xi_pts = lambda sq, lo, hi: sum(best_xi_value([(p, proj.series.get(p, {}).get(gw, 0.0)) for p in sq], els) for gw in range(lo, hi + 1))
    base = [xi_pts(squad, lo, hi) for lo, hi in windows]
    count: dict = {}
    for p in squad:
        count[els[p]["team"]] = count.get(els[p]["team"], 0) + 1
    pool = [p for p in proj.series if p not in squad and els[p]["minutes"] >= min_minutes
            and proj.players[p]["mf"] >= min_mf and proj.available(p)]
    moves = []
    for o in squad:
        for i in pool:
            if els[i]["element_type"] != els[o]["element_type"]:
                continue
            if els[i]["team"] != els[o]["team"] and count.get(els[i]["team"], 0) >= club_limit:
                continue
            cost = price(i) - price(o)
            if cost > max_cost:
                continue
            sq2 = [i if p == o else p for p in squad]
            moves.append(Move(o, i, tuple(xi_pts(sq2, lo, hi) - b for (lo, hi), b in zip(windows, base)), cost))
    return sorted(moves, key=lambda m: -sum(m.gains))
