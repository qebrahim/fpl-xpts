from pathlib import Path

import pytest

from fplxpts.config import load_config, load_squad
from fplxpts.data import Season
from fplxpts.pens import build_pen_model, strip_penalties

ROOT = Path(__file__).resolve().parents[1]


def test_default_config_loads():
    cfg = load_config()
    assert cfg.model.form_halflife == 8.0 and cfg.model.team_halflife == 8.0
    assert cfg.model.prior_min == 300 and cfg.model.prior_lambda == pytest.approx(0.3)
    assert cfg.calibration[(3, "goal")] == pytest.approx(0.805)   # MID goal factor
    assert cfg.without_calibration().calibration == {}


def test_example_squad_loads_and_top_level_keys_are_not_swallowed():
    sq = load_squad(ROOT / "config" / "squad.example.toml")
    assert len(sq.players) == 15
    assert sq.assume_fit == ["Calafiori", "Thomas"]
    assert "Isak" in sq.overrides and len(sq.pen_goals) > 5


def _season():
    el = lambda i, team, typ, missed=0, order=None: {"id": i, "team": team, "element_type": typ, "web_name": f"Taker{i}",
                                                       "second_name": f"Taker{i}", "penalties_missed": missed, "penalties_order": order}
    elements = {1: el(1, 10, 3, order=1), 2: el(2, 10, 3, order=2), 3: el(3, 11, 4, order=1), 4: el(4, 10, 1)}
    row = lambda rnd, xg, g: {"round": rnd, "expected_goals": str(xg), "goals_scored": g}
    hist = {1: [row(1, 0.1, 0), row(2, 0.85, 1), row(3, 0.9, 1)], 2: [], 3: []}
    return Season(elements, {10: "AAA", 11: "BBB"}, [], hist, {}, [], 10)


def test_pen_model_and_stripping():
    s = _season()
    pm = build_pen_model(s, [("Taker1", "AAA", 1)])
    assert pm.taken == {1: 1} and pm.primary[10] == 1          # the player who has taken one beats FPL order
    assert pm.primary[11] == 3                                  # no pens yet -> FPL order-1 player
    from fplxpts.config import load_config
    adj = strip_penalties(s, pm, load_config())
    # the penalty is removed from the highest-xG game that had a goal (round 3), leaving round 2 untouched
    assert float(adj[1][2]["expected_goals"]) == pytest.approx(0.14) and adj[1][2]["goals_scored"] == 0
    assert float(adj[1][1]["expected_goals"]) == pytest.approx(0.85) and adj[1][1]["goals_scored"] == 1
    assert s.hist[1][2]["goals_scored"] == 1                    # original untouched
