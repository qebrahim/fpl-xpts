import pytest

from fplxpts.config import load_config
from fplxpts.data import Season
from fplxpts.points import components, dc_hit_vs
from fplxpts.teams import TeamState, dc_obs_exp, dc_opp_factors, shrink_ratio, team_state


def _row(rnd, opp, dc, minutes=90):
    return {"round": rnd, "opponent_team": opp, "minutes": minutes, "defensive_contribution": dc}


def _season(extra=()):
    """Two DEFs (teams 10, 11) and one MID (team 10); team 11 opponents hit DC twice as often as team 12's."""
    el = lambda i, team, typ: {"id": i, "team": team, "element_type": typ}
    elements = {1: el(1, 10, 2), 2: el(2, 12, 2), 3: el(3, 10, 3), 4: el(4, 10, 1)}
    hist = {
        1: [_row(1, 11, 12), _row(2, 12, 0), _row(3, 11, 11), _row(4, 12, 0)],   # DEF: 2/2 vs 11, 0/2 vs 12
        2: [_row(1, 11, 10), _row(2, 10, 3), _row(3, 11, 2), _row(4, 10, 1)],    # DEF: 1/2 vs 11, 0/2 vs 10
        3: [_row(1, 11, 13), _row(2, 12, 2), _row(3, 11, 0), _row(4, 12, 0), *extra],
        4: [_row(1, 11, 50)],                                                    # GK: never counts
    }
    fin = [{"ev": r, "h": 10, "a": 11 if r % 2 else 12, "xg_h": 1.4, "xg_a": 1.1} for r in (1, 2, 3, 4)]
    return Season(elements, {10: "AAA", 11: "BBB", 12: "CCC"}, [], hist, {}, fin, 4)


def test_shrink_ratio():
    assert shrink_ratio(0, 0, 10) == pytest.approx(1.0)            # no data -> 1.0
    assert shrink_ratio(8, 4, 0.0) == pytest.approx(2.0)
    assert 1.0 < shrink_ratio(8, 4, 10) < shrink_ratio(8, 4, 1) < 2.0   # more k -> closer to 1


def test_dc_factors_no_data_and_feature_off():
    assert dc_opp_factors({}, 10) == {}
    assert dc_opp_factors({11: (8.0, 4.0)}, 0) == {}                # k = 0 switches it off
    assert dc_opp_factors({11: (8.0, 4.0)}, 4)[11] == pytest.approx(12 / 8)


def test_dc_obs_exp_counts_hits_vs_position_expectation():
    oe = dc_obs_exp(_season(), cut=4, min_live_minutes=90)
    # league rates: DEF 3/8, MID 1/4; GK rows are ignored
    assert oe[11] == (pytest.approx(4), pytest.approx(4 * 3 / 8 + 2 * 1 / 4))
    assert oe[12] == (pytest.approx(0), pytest.approx(2 * 3 / 8 + 2 * 1 / 4))
    f = dc_opp_factors(oe, 2)
    assert f[11] > 1 > f[12]


def test_dc_obs_exp_ignores_rows_after_cut_and_short_appearances():
    s = _season()
    trimmed = Season(s.elements, s.teams, [], {p: [r for r in rows if r["round"] <= 2] for p, rows in s.hist.items()}, {}, s.fin, 4)
    assert dc_obs_exp(s, cut=2, min_live_minutes=90) == dc_obs_exp(trimmed, cut=2, min_live_minutes=90)
    assert dc_obs_exp(s, cut=2, min_live_minutes=90) != dc_obs_exp(s, cut=4, min_live_minutes=90)
    assert dc_obs_exp(_season(extra=[_row(5, 12, 40)]), cut=4, min_live_minutes=90) == dc_obs_exp(_season(), 4, 90)
    assert dc_obs_exp(_season(extra=[_row(4, 12, 40, minutes=59)]), 4, 90)[12][0] == 0


def test_team_state_dc_fields():
    cfg = load_config()
    off = team_state(_season(), 4, cfg.with_model(dc_opp_k=0.0))
    assert off.dc_opp == {} and off.pn_dc == {}
    on = team_state(_season(), 4, cfg.with_model(dc_opp_k=2.0))
    assert on.dc_opp[11] > 1 > on.dc_opp[12]
    assert on.pn_dc[10] == pytest.approx(sum(on.dc_opp.get(o, 1.0) for o in (11, 12, 11, 12)) / 4)


def _state(**kw):
    return TeamState(lg={"h": 1.5, "a": 1.2}, att={1: 1.0, 2: 1.0}, dfn={1: 1.0, 2: 1.0},
                     pn_att={1: 1.35, 2: 1.35}, pn_opp={1: 1.35, 2: 1.35}, **kw)


def _player(hit=0.3):
    return {"pos": 2, "team": 1, "xg90": 0.1, "xa90": 0.1, "bon_base90": 0.1, "bon_k": {"base": 0.1, "goal": 0.8, "assist": 0.5, "cs": 0.4, "sav": 0.1},
            "sav90": 0.0, "yc90": 0.1, "hit": hit, "mf": 1.0, "app": 2.0, "p60": 0.9}


def test_dc_component_moves_with_opponent_and_is_capped():
    old = 2 * 0.3 * 0.9
    assert components(_player(), "h", 2, _state())["dc"] == pytest.approx(old)          # feature off: unchanged
    assert components(_player(), "h", 2, _state(dc_opp={2: 1.0}, pn_dc={1: 1.0}))["dc"] == pytest.approx(old)
    assert components(_player(), "h", 2, _state(dc_opp={2: 1.5}, pn_dc={1: 1.0}))["dc"] > old
    assert components(_player(), "h", 2, _state(dc_opp={2: 1.0}, pn_dc={1: 1.2}))["dc"] < old  # rate earned vs generous opponents
    assert components(_player(0.8), "h", 2, _state(dc_opp={2: 3.0}, pn_dc={1: 1.0}))["dc"] == pytest.approx(2 * 0.9)
    assert dc_hit_vs(0.8, 3.0, 1.0) == 1.0
