import math

import pytest

from fplxpts.config import load_config
from fplxpts.points import components
from fplxpts.teams import TeamState, damped_opp_xg


def test_gamma_one_reproduces_plain_product():
    for lg_v, att, dfn in ((1.5, 1.3, 0.8), (1.2, 0.7, 1.4), (1.35, 1.0, 1.0)):
        assert damped_opp_xg(lg_v, att, dfn, 1.0) == pytest.approx(lg_v * att * dfn, rel=1e-15)
        assert damped_opp_xg(lg_v, att, dfn) == pytest.approx(lg_v * att * dfn, rel=1e-15)


def test_gamma_below_one_pulls_towards_venue_average():
    lg_v = 1.4
    hard, easy = damped_opp_xg(lg_v, 1.5, 1.2, 1.0), damped_opp_xg(lg_v, 0.7, 0.8, 1.0)
    hard_d, easy_d = damped_opp_xg(lg_v, 1.5, 1.2, 0.5), damped_opp_xg(lg_v, 0.7, 0.8, 0.5)
    assert lg_v < hard_d < hard and easy < easy_d < lg_v
    assert damped_opp_xg(lg_v, 1.25, 0.8, 0.5) == pytest.approx(lg_v)   # exactly-average matchup (1.25 * 0.8 = 1)
    assert damped_opp_xg(lg_v, 1.5, 1.2, 0.0) == pytest.approx(lg_v)    # gamma 0 = venue average for everyone


def _state(att_opp, gamma):
    return TeamState(lg={"h": 1.5, "a": 1.2}, att={1: 1.0, 2: att_opp}, dfn={1: 1.0, 2: 1.0},
                     pn_att={1: 1.35, 2: 1.35}, pn_opp={1: 1.35, 2: 1.35}, opp_xg_gamma=gamma)


def _defender():
    return {"pos": 2, "team": 1, "xg90": 0.05, "xa90": 0.05, "bon_base90": 0.1, "bon_k": {"base": 0.1, "goal": 0.8, "assist": 0.5, "cs": 0.4, "sav": 0.1},
            "sav90": 0.0, "yc90": 0.1, "hit": 0.3, "mf": 0.95, "app": 1.95, "p60": 0.9}


def test_components_clean_sheet_moves_towards_average_and_gc_is_unchanged():
    # player at home -> opponent plays away, league away xG 1.2
    hard1, hard_d = (components(_defender(), "h", 2, _state(1.6, g)) for g in (1.0, 0.5))
    easy1, easy_d = (components(_defender(), "h", 2, _state(0.6, g)) for g in (1.0, 0.5))
    assert hard1["cs"] == pytest.approx(math.exp(-1.2 * 1.6) * 0.9 * 4)
    assert hard_d["cs"] > hard1["cs"] and easy_d["cs"] < easy1["cs"]
    assert hard_d["gc"] == hard1["gc"] and easy_d["gc"] == easy1["gc"]   # damping feeds the clean sheet only
    assert hard_d["sav"] == hard1["sav"] and hard_d["goal"] == hard1["goal"]


def test_config_loads_gamma():
    cfg = load_config()
    assert cfg.model.opp_xg_gamma == 1.0
    assert cfg.with_model(opp_xg_gamma=0.7).model.opp_xg_gamma == 0.7
