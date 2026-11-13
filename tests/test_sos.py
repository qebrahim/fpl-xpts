"""Strength-of-schedule (opponent-adjusted) team ratings."""
import math
from itertools import permutations

import pytest

from fplxpts.config import load_config
from fplxpts.data import Season
from fplxpts.teams import game_log, opp_of, ratings, recency_weights, rescale_mean, team_state

LG = {"h": 1.0, "a": 1.0}


def _fx(ev, h, a, xg_h, xg_a):
    return {"ev": ev, "h": h, "a": a, "xg_h": xg_h, "xg_a": xg_a}


def _true_league(att, dfn, pairs):
    """Noise-free fixtures: xG = attack of the scorer x defence of the conceder (league average 1.0)."""
    return [_fx(i + 1, h, a, att[h] * dfn[a], att[a] * dfn[h]) for i, (h, a) in enumerate(pairs)]


def _plain_ratings(log, lg, teams, hl, k):
    """The pre-SoS formula, written out independently: venue-normalised, recency-weighted, shrunk."""
    att, dfn = {}, {}
    for t in teams:
        lt = log.get(t, [])
        n = len(lt)
        if n == 0:
            att[t] = dfn[t] = 1.0
            continue
        ws = [1.0 if hl is None else 0.5 ** ((n - 1 - i) / hl) for i in range(n)]
        f_ = sum(w * (r[3] / lg[r[2]]) for w, r in zip(ws, lt)) / sum(ws)
        a_ = sum(w * (r[4] / lg[opp_of(r[2])]) for w, r in zip(ws, lt)) / sum(ws)
        att[t], dfn[t] = (f_ * n + k) / (n + k), (a_ * n + k) / (n + k)
    return att, dfn


def test_helpers():
    assert recency_weights(3, None) == [1.0, 1.0, 1.0]
    assert recency_weights(3, 1.0) == pytest.approx([0.25, 0.5, 1.0])
    assert rescale_mean({1: 2.0, 2: 4.0}, {1: 1.0, 2: 2.0}) == pytest.approx({1: 1.0, 2: 2.0})
    log = game_log([_fx(2, 1, 2, 1.5, 0.5), _fx(1, 2, 1, 0.7, 0.9)])
    assert log[1] == [(1, 2, "a", 0.9, 0.7), (2, 2, "h", 1.5, 0.5)]   # chronological, from team 1's side


def test_off_reproduces_plain_ratings_exactly():
    fin = [_fx(1, 1, 2, 1.7, 0.4), _fx(1, 3, 4, 0.9, 1.1), _fx(2, 2, 3, 1.2, 1.3), _fx(2, 4, 1, 0.6, 2.2),
           _fx(3, 1, 3, 1.1, 0.0), _fx(3, 2, 4, 1.4, 0.8)]
    lg = {"h": 1.15, "a": 0.95}
    log = game_log(fin)
    for hl in (None, 3.0):
        assert ratings(log, lg, [1, 2, 3, 4, 5], hl, 3.0, 0) == _plain_ratings(log, lg, [1, 2, 3, 4, 5], hl, 3.0)


def _skewed():
    """A (1) only meets the weak attack W (3); B (2) only meets the strong attack S (4); W and S also play C, D.

    Every defence is truly average (1.0), so any defensive difference between A and B is schedule.
    """
    att = {1: 1.0, 2: 1.0, 3: 0.5, 4: 1.6, 5: 1.0, 6: 1.0}
    dfn = dict.fromkeys(att, 1.0)
    pairs = [(1, 3), (3, 1)] * 2 + [(2, 4), (4, 2)] * 2 + [(3, 5), (5, 3), (3, 6), (6, 3), (4, 5), (5, 4), (4, 6), (6, 4)] * 2
    return game_log(_true_league(att, dfn, pairs)), list(att)


def test_schedule_adjustment_corrects_defence_for_opponent_attack():
    log, teams = _skewed()
    _, d0 = ratings(log, LG, teams, None, 0.0, 0)
    _, d1 = ratings(log, LG, teams, None, 0.0, 50)
    assert d0[1] < 0.6 and d0[2] > 1.4                 # unadjusted: A looks elite, B looks leaky
    assert d1[1] > d0[1] and d1[2] < d0[2]             # adjusted: A worse (higher), B better (lower)
    assert abs(d1[1] - d1[2]) < 0.5 * abs(d0[1] - d0[2])
    _, d0k = ratings(log, LG, teams, 3.0, 3.0, 0)      # same direction with recency weights and shrinkage
    _, d1k = ratings(log, LG, teams, 3.0, 3.0, 20)
    assert d1k[1] > d0k[1] and d1k[2] < d0k[2]


def test_round_robin_identical_schedules_barely_move():
    teams = list(range(1, 11))
    att = {t: 0.8 + 0.04 * t for t in teams}
    dfn = {t: 1.2 - 0.04 * t for t in teams}
    log = game_log(_true_league(att, dfn, list(permutations(teams, 2))))
    a0, d0 = ratings(log, LG, teams, None, 3.0, 0)
    a1, d1 = ratings(log, LG, teams, None, 3.0, 20)
    assert max(abs(a1[t] - a0[t]) for t in teams) < 0.03
    assert max(abs(d1[t] - d0[t]) for t in teams) < 0.03
    assert sum(a1.values()) == pytest.approx(sum(a0.values()))   # league level preserved


def test_converges_and_stays_finite_with_zero_xg():
    fin = [_fx(1, 1, 2, 0.0, 2.0), _fx(2, 2, 1, 1.5, 0.0), _fx(3, 1, 3, 0.0, 1.0), _fx(4, 3, 2, 1.2, 0.0)]
    log = game_log(fin)
    for k in (0.0, 3.0):
        a50, d50 = ratings(log, LG, [1, 2, 3], None, k, 50)
        a60, d60 = ratings(log, LG, [1, 2, 3], None, k, 60)
        assert all(math.isfinite(v) and v >= 0 for v in [*a50.values(), *d50.values()])
        assert a50 == pytest.approx(a60, abs=1e-6) and d50 == pytest.approx(d60, abs=1e-6)
    assert ratings(log, LG, [1, 2, 3], None, 0.0, 50)[0][1] == 0.0   # team 1 never registered an xG


def _season(fin):
    return Season({}, {t: f"T{t}" for t in range(1, 5)}, [], {}, {}, fin, 4)


def test_team_state_ignores_fixtures_after_cut():
    early = [_fx(1, 1, 2, 1.7, 0.4), _fx(1, 3, 4, 0.9, 1.1), _fx(2, 2, 3, 1.2, 1.3), _fx(2, 4, 1, 0.6, 2.2)]
    late = [_fx(3, 1, 3, 5.0, 0.0), _fx(3, 2, 4, 0.0, 4.0)]
    cfg = load_config().with_model(team_sos_iters=20)
    a, b = team_state(_season(early + late), 2, cfg), team_state(_season(early), 2, cfg)
    assert (a.att, a.dfn, a.pn_att, a.pn_opp) == (b.att, b.dfn, b.pn_att, b.pn_opp)
    assert team_state(_season(early + late), 3, cfg).att != a.att


def test_team_state_pn_uses_adjusted_unweighted_ratings():
    fin = [_fx(1, 1, 2, 1.7, 0.4), _fx(1, 3, 4, 0.9, 1.1), _fx(2, 2, 3, 1.2, 1.3), _fx(2, 4, 1, 0.6, 2.2)]
    cfg = load_config().with_model(team_sos_iters=20)
    st = team_state(_season(fin), 2, cfg)
    log = game_log(fin)
    _, dfn0 = ratings(log, st.lg, [1, 2, 3, 4], None, cfg.model.team_shrink_k, 20)
    assert st.pn_att[1] == pytest.approx(sum(st.lg[r[2]] * dfn0[r[1]] for r in log[1]) / 2)
    assert team_state(_season(fin), 2, cfg.with_model(team_sos_iters=0)).pn_att[1] != pytest.approx(st.pn_att[1])
