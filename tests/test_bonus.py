import pytest

from fplxpts.bonus import event_counts, expected_bonus, fit_bonus_coefs, residual
from fplxpts.points import components
from fplxpts.teams import TeamState


def row(minutes=90, goals=0, assists=0, cs=0, saves=0, bonus=0):
    return {"minutes": minutes, "goals_scored": goals, "assists": assists, "clean_sheets": cs, "saves": saves, "bonus": bonus}


def state(att_opp=1.0):
    return TeamState(lg={"h": 1.5, "a": 1.2}, att={1: 1.0, 2: att_opp}, dfn={1: 1.0, 2: 1.0},
                     pn_att={1: 1.35, 2: 1.35}, pn_opp={1: 1.35, 2: 1.35})


def player(pos, xg90=0.4):
    k = {"base": 0.1, "goal": 1.0, "assist": 0.5, "cs": 0.6, "sav": 0.1}
    return {"pos": pos, "team": 1, "xg90": xg90, "xa90": 0.2, "bon_base90": 0.1, "bon_k": k, "sav90": 3.0 if pos == 1 else 0.0,
            "yc90": 0.1, "hit": 0.2, "mf": 0.9, "app": 1.9, "p60": 0.9}


def test_event_counts_clean_sheet_needs_60_minutes_and_saves_only_for_keepers():
    assert event_counts(row(minutes=59, cs=1), 2)["cs"] == 0
    assert event_counts(row(cs=1, saves=4), 2) == {"goal": 0, "assist": 0, "cs": 1, "sav": 0}
    assert event_counts(row(saves=4), 1)["sav"] == 4


def test_fit_recovers_exact_coefficients():
    rows = [row(goals=g, assists=a, bonus=0.2 + 1.5 * g + 0.5 * a)
            for g in range(3) for a in range(3) for _ in range(200)]
    c = fit_bonus_coefs(rows, 4)
    assert c["base"] == pytest.approx(0.2, abs=0.01)
    assert c["goal"] == pytest.approx(1.5, abs=0.01)
    assert c["assist"] == pytest.approx(0.5, abs=0.01)
    assert set(c) == {"base", "goal", "assist"}      # forwards get no clean-sheet / save terms


def test_fit_is_non_negative_and_safe_without_data():
    assert all(v == 0.0 for v in fit_bonus_coefs([], 2).values())
    noisy = [row(goals=1, bonus=0) for _ in range(50)] + [row(bonus=1) for _ in range(50)]
    assert all(v >= 0 for v in fit_bonus_coefs(noisy, 3).values())


def test_residual_is_zero_when_bonus_is_fully_explained():
    coefs = {"base": 0.2, "goal": 1.5, "assist": 0.5}
    r = row(minutes=90, goals=1, assists=1, bonus=0.2 + 1.5 + 0.5)
    assert residual(r, 3, coefs) == pytest.approx(0.0)


def test_expected_bonus_is_baseline_plus_marginal_events():
    k = {"goal": 1.0, "assist": 0.5, "cs": 0.6}
    assert expected_bonus(0.2, k, 0.9, {"goal": 0.4, "assist": 0.2, "cs": 0.5}) == pytest.approx(0.2 * 0.9 + 0.4 + 0.1 + 0.3)


def test_bonus_follows_the_events_expected_in_the_fixture():
    # forward: more expected goals -> more bonus
    assert components(player(4, 0.6), "h", 2, state())["bonus"] > components(player(4, 0.3), "h", 2, state())["bonus"]
    # defender: a weaker opponent attack means a likelier clean sheet and so more bonus
    weak = components(player(2), "h", 2, state(att_opp=0.6))["bonus"]
    strong = components(player(2), "h", 2, state(att_opp=1.6))["bonus"]
    assert weak > strong
