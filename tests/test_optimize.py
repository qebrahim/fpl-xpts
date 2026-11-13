from types import SimpleNamespace

from fplxpts.model import Projection
from fplxpts.optimize import best_xi_value, pick_lineup


def make():
    # 2 GK, 5 DEF, 5 MID, 3 FWD  -> ids 1..15
    types = [1, 1] + [2] * 5 + [3] * 5 + [4] * 3
    elements = {i + 1: {"element_type": t, "team": 1, "now_cost": 50, "web_name": f"P{i + 1}",
                        "chance_of_playing_next_round": None, "minutes": 900} for i, t in enumerate(types)}
    return elements


def test_best_xi_respects_formation_limits():
    els = make()
    # forwards are by far the best, but at most 3 can start; keeper 1 beats keeper 2
    pts = {1: 4, 2: 1}
    pts.update({i: 3 for i in range(3, 8)})        # DEF
    pts.update({i: 3 for i in range(8, 13)})       # MID
    pts.update({i: 9 for i in range(13, 16)})      # FWD
    best = best_xi_value(list(pts.items()), els)
    assert best == 4 + 27 + 7 * 3


def test_best_xi_needs_a_keeper_and_minimum_defenders():
    els = make()
    pts = {i: 1.0 for i in els}
    for i in range(3, 8):
        pts[i] = 0.1                                 # defenders are terrible but 3 must still start
    best = best_xi_value(list(pts.items()), els)
    assert abs(best - (1.0 + 3 * 0.1 + 7 * 1.0)) < 1e-9


def test_pick_lineup_captain_and_bench():
    els = make()
    series = {i: {11: float(i)} for i in els}        # higher id = more points
    season = SimpleNamespace(elements=els, teams={1: "TST"})
    proj = Projection(season, {i: {} for i in els}, series, 11, 11)
    lu = pick_lineup(list(els), proj, 11)
    assert lu.captain == 15 and lu.vice == 14
    assert len(lu.xi) == 11 and len(set(lu.xi)) == 11
    assert lu.xi[0] == 2                              # the better of the two keepers
    assert lu.bench[-1] == 1                          # spare keeper last
    assert lu.formation in {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-2-3", "5-3-2", "5-4-1"}
