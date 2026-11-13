import math

import pytest

from fplxpts.points import actual_components, components, gc_penalty, total
from fplxpts.teams import TeamState


def state(att_opp=1.0, dfn_own=1.0):
    return TeamState(lg={"h": 1.5, "a": 1.2}, att={1: 1.0, 2: att_opp}, dfn={1: dfn_own, 2: 1.0},
                     pn_att={1: 1.35, 2: 1.35}, pn_opp={1: 1.35, 2: 1.35})


def player(pos=3, xg90=0.4, xa90=0.2):
    return {"pos": pos, "team": 1, "xg90": xg90, "xa90": xa90, "bon_base90": 0.15, "bon_k": {"base": 0.1, "goal": 0.8, "assist": 0.5, "cs": 0.4, "sav": 0.1}, "sav90": 3.0 if pos == 1 else 0.0,
            "yc90": 0.1, "hit": 0.2, "mf": 0.9, "app": 1.9, "p60": 0.9}


def test_gc_penalty_basics():
    assert gc_penalty(0.0) == pytest.approx(0.0)
    vals = [gc_penalty(x) for x in (0.5, 1.0, 1.5, 2.0, 3.0)]
    assert vals == sorted(vals)                      # more expected goals conceded -> bigger penalty
    assert all(0 <= v <= x / 2 for v, x in zip(vals, (0.5, 1.0, 1.5, 2.0, 3.0)))


def test_clean_sheet_probability_falls_with_opponent_attack():
    weak = components(player(2), "h", 2, state(att_opp=0.7))["cs"]
    strong = components(player(2), "h", 2, state(att_opp=1.5))["cs"]
    assert weak > strong > 0


def test_attackers_do_not_get_clean_sheet_or_gc_points_beyond_position_rules():
    fwd = components(player(4), "h", 2, state())
    assert fwd["cs"] == 0 and fwd["gc"] == 0
    mid = components(player(3), "h", 2, state())
    assert mid["cs"] > 0 and mid["gc"] == 0          # mids get 1 pt for a clean sheet but no conceded penalty


def test_goal_component_scales_with_xg():
    lo = components(player(4, xg90=0.3), "h", 2, state())["goal"]
    hi = components(player(4, xg90=0.6), "h", 2, state())["goal"]
    assert hi == pytest.approx(2 * lo)


def test_calibration_scales_components():
    c = components(player(2), "h", 2, state())
    base = total(c, 2)
    cal = {(2, "goal"): 0.5}
    assert total(c, 2, cal) == pytest.approx(base - 0.5 * c["goal"])


def test_actual_components_sum_to_points_for_a_simple_match():
    row = {"minutes": 90, "goals_scored": 1, "assists": 1, "clean_sheets": 0, "goals_conceded": 2, "defensive_contribution": 10,
           "bonus": 2, "saves": 0, "yellow_cards": 1}
    a = actual_components(row, 2)
    assert a["app"] == 2 and a["goal"] == 6 and a["assist"] == 3 and a["gc"] == -1 and a["dc"] == 2 and a["yc"] == -1
    assert math.isclose(sum(a.values()), 2 + 6 + 3 - 1 + 2 + 2 - 1)
