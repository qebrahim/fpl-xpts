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
