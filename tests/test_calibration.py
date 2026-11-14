"""Calibration fit: pseudo-point shrinkage, walk-forward (no look-ahead) refits, TOML round trip."""
import pytest

from fplxpts.backtest import (
    CAL_K,
    Row,
    calibration_toml,
    fit_calibration,
    shrunk_ratio,
    walk_forward_calibration,
    walk_forward_predicted,
)
from fplxpts.config import load_config
from fplxpts.constants import COMPONENTS


def _row(cut, rnd, pred_goal, act_goal, pos=4, pid=1):
    comps = {c: 0.0 for c in COMPONENTS} | {"goal": pred_goal}
    actual = {c: 0 for c in COMPONENTS} | {"goal": act_goal}
    return Row(pid, cut, rnd, pos, comps, actual, act_goal)


def test_shrunk_ratio_limits():
    assert shrunk_ratio(30.0, 60.0, 0.0) == pytest.approx(0.5)          # k = 0: raw ratio
    assert shrunk_ratio(30.0, 60.0, 1e9) == pytest.approx(1.0, abs=1e-6)  # huge k: no calibration
    assert shrunk_ratio(30.0, 60.0, 60.0) == pytest.approx(0.75)        # (30 + 60) / (60 + 60)
    assert shrunk_ratio(-30.0, -60.0, 60.0) == pytest.approx(0.75)      # negative components (gc, yc) symmetric
    assert shrunk_ratio(-30.0, -60.0, 0.0) == pytest.approx(0.5)
    k_small, k_big = shrunk_ratio(30.0, 60.0, 10.0), shrunk_ratio(30.0, 60.0, 100.0)
    assert 0.5 < k_small < k_big < 1.0                                   # monotone pull towards 1


def test_fit_calibration_k0_is_raw_and_default_shrinks():
    rows = [_row(1, 2, 10.0, 25), _row(1, 3, 10.0, 25)]                  # FWD goal: predicted 20, actual 50
    assert fit_calibration(rows, k=0)[(4, "goal")] == pytest.approx(2.5)
    assert fit_calibration(rows, k=20)[(4, "goal")] == pytest.approx(70 / 40)   # the pre-2026-11 method
    assert fit_calibration(rows)[(4, "goal")] == pytest.approx((50 + CAL_K) / (20 + CAL_K))
    assert (4, "assist") not in fit_calibration(rows, k=0)               # nothing predicted -> no factor (1.0)


def test_walk_forward_uses_only_target_rounds_up_to_the_cutoff():
    # Predictions made at cutoff 1 for rounds 2-4 and at cutoff 2 for rounds 3-4.
    rows = [
        _row(1, 2, 10.0, 5),     # known at cutoff 2: ratio 0.5
        _row(1, 3, 10.0, 40),    # target round 3 > 2: must NOT inform cutoff-2 factors (would give 45/20)
        _row(1, 4, 10.0, 40),
        _row(2, 3, 10.0, 40),    # the rows being predicted at cutoff 2 themselves
        _row(2, 4, 10.0, 40),
    ]
    cals = walk_forward_calibration(rows, k=0)
    assert cals[1] == {}                                                 # no outcomes known at cutoff 1 -> all 1.0
    assert cals[2][(4, "goal")] == pytest.approx(0.5)                    # only the round-2 row
    pred = walk_forward_predicted(rows, k=0)
    assert list(pred) == pytest.approx([10.0, 10.0, 10.0, 5.0, 5.0])
    # a leak would show up as a dependence on later outcomes: changing them must not move cutoff-2 factors
    leaked = rows[:1] + [r._replace(actual={**r.actual, "goal": 0}) for r in rows[1:]]
    assert walk_forward_calibration(leaked, k=0)[2] == cals[2]


def test_walk_forward_falls_back_to_one_without_enough_data():
    rows = [_row(1, 2, 10.0, 5), _row(2, 3, 10.0, 5), _row(3, 4, 10.0, 5)]
    cals = walk_forward_calibration(rows, k=0, min_rows=2)
    assert cals[1] == {} and cals[2] == {}                               # 0 and 1 known rows
    assert cals[3][(4, "goal")] == pytest.approx(0.5)                    # rounds 2 and 3 known at cutoff 3
    assert list(walk_forward_predicted(rows, k=0, min_rows=2)) == pytest.approx([10.0, 10.0, 5.0])


def test_calibration_toml_round_trips_through_load_config(tmp_path):
    cal = {(1, "sav"): 0.668, (2, "goal"): 0.567, (2, "gc"): 0.772, (4, "assist"): 1.502}
    path = tmp_path / "cfg.toml"
    path.write_text("[model]\nform_halflife = 4.0\n\n" + calibration_toml(cal))
    assert load_config(path).calibration == pytest.approx(cal)


# --- calibration shrunk towards a prior (e.g. last season's factors); off by default -------------------------------

def _mixed_rows():
    rows = [_row(1, 2, 10.0, 25), _row(1, 3, 10.0, 5), _row(2, 3, 4.0, 2, pos=2, pid=2)]
    gc = {c: 0.0 for c in COMPONENTS} | {"gc": -1.5}                          # a negative component (DEF gc)
    rows.append(Row(3, 1, 2, 2, gc, {c: 0 for c in COMPONENTS} | {"gc": -1}, -1))
    return rows


def test_shrunk_ratio_with_target():
    assert shrunk_ratio(30.0, 60.0, 60.0, 1.0) == shrunk_ratio(30.0, 60.0, 60.0)    # target 1.0 = today's formula
    assert shrunk_ratio(30.0, 60.0, 60.0, 0.8) == pytest.approx((30 + 48) / 120)
    assert shrunk_ratio(0.0, 0.0, 160.0, 0.7) == pytest.approx(0.7)                 # no data: the target
    assert shrunk_ratio(-30.0, -60.0, 60.0, 0.8) == pytest.approx((30 + 48) / 120)  # negative components symmetric


def test_fit_calibration_without_prior_is_unchanged():
    rows = _mixed_rows()
    for k in (0.0, 20.0, CAL_K):
        assert fit_calibration(rows, k, prior=None) == fit_calibration(rows, k)
        assert fit_calibration(rows, k, prior={}) == fit_calibration(rows, k)
    assert walk_forward_calibration(rows, prior=None) == walk_forward_calibration(rows)


def test_fit_calibration_prior_limits():
    prior = {(4, "goal"): 0.85, (2, "goal"): 0.6, (2, "gc"): 0.9, (1, "sav"): 0.95}
    # no data: every factor equals the prior (cells with nothing predicted included)
    assert fit_calibration([], prior=prior) == prior
    assert walk_forward_calibration([_row(1, 2, 10.0, 5)], prior=prior)[1] == prior    # cutoff 1: nothing known yet
    # little data: close to the prior; lots of data: close to the raw ratio (0.5 here)
    few = [_row(1, 2, 2.0, 1)]
    many = [_row(1, 2, 10.0, 5, pid=i) for i in range(10_000)]
    assert fit_calibration(few, prior=prior)[(4, "goal")] == pytest.approx((1 + CAL_K * 0.85) / (2 + CAL_K))
    assert abs(fit_calibration(few, prior=prior)[(4, "goal")] - 0.85) < 0.01
    assert fit_calibration(many, prior=prior)[(4, "goal")] == pytest.approx(0.5, abs=0.002)
    # negative component: pseudo-points of 'actual = prior x predicted' on the negative side
    rows = _mixed_rows()
    assert fit_calibration(rows, prior=prior)[(2, "gc")] == pytest.approx((-1 - CAL_K * 0.9) / (-1.5 - CAL_K))


def test_fit_calibration_missing_prior_cell_behaves_like_one():
    rows = _mixed_rows()
    prior = {(2, "goal"): 0.6}                                  # no FWD goal and no DEF gc cell (e.g. dc before 2025/26)
    with_prior, plain = fit_calibration(rows, prior=prior), fit_calibration(rows)
    assert with_prior[(4, "goal")] == plain[(4, "goal")] and with_prior[(2, "gc")] == plain[(2, "gc")]
    assert with_prior[(2, "goal")] != plain[(2, "goal")]
    assert (4, "assist") not in with_prior                      # nothing predicted, no prior -> no factor (1.0)


def test_walk_forward_with_prior_uses_only_known_rounds():
    prior = {(4, "goal"): 0.8}
    rows = [_row(1, 2, 10.0, 5), _row(1, 3, 10.0, 40), _row(2, 3, 10.0, 40)]
    cals = walk_forward_calibration(rows, k=CAL_K, prior=prior)
    assert cals[1] == prior
    assert cals[2][(4, "goal")] == pytest.approx((5 + CAL_K * 0.8) / (10 + CAL_K))     # only the round-2 row
    leaked = rows[:1] + [r._replace(actual={**r.actual, "goal": 0}) for r in rows[1:]]
    assert walk_forward_calibration(leaked, k=CAL_K, prior=prior)[2] == cals[2]
