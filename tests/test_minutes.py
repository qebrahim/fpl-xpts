"""Minutes model: skipping inferred injury/suspension absences (players.absence_rows / minutes_window)."""
import pytest

from fplxpts.config import load_config
from fplxpts.data import Season
from fplxpts.players import absence_rows, build_players, minutes_inputs, minutes_window, zero_runs


def r(minutes, start=None, rnd=0):
    """Match row; `start` defaults to 'started' for 60+ minutes, sub otherwise."""
    return {"round": rnd, "minutes": minutes, "starts": int(minutes >= 60 if start is None else start)}


def rows(*mins):
    """'45s' = 45-minute sub appearance, 45 = 45-minute start, 0 = did not play."""
    out = []
    for i, m in enumerate(mins, 1):
        if isinstance(m, str):
            out.append(r(int(m[:-1]), 0, i))
        else:
            out.append(r(m, m > 0, i))
    return out


def old_inputs(rs):
    """The minutes model before absences were skipped: plain average over the last five rows."""
    last = rs[-5:]
    return {"mf": sum(x["minutes"] for x in last) / len(last) / 90,
            "app": sum((2 if x["minutes"] >= 60 else 1 if x["minutes"] > 0 else 0) for x in last) / len(last),
            "p60": sum(1 for x in last if x["minutes"] >= 60) / len(last)}


ISAK = rows(90, 90, 63, 90, 80, 0, 78, 76, 90, 90)


def test_zero_runs():
    assert zero_runs(rows(90, 0, 0, 90, 0)) == [(1, 3), (4, 5)]
    assert zero_runs(rows(90, 90)) == []


def test_off_is_the_plain_last_five():
    for rs in (ISAK, rows(0, "20s", 0, 0, 90), rows(90, 0, 0, 0)):
        assert minutes_window(rs, 5, starts_before=0) == rs[-5:]
        assert minutes_inputs(minutes_window(rs, 5, 0)) == old_inputs(rs)


def test_isolated_absence_of_a_starter_is_skipped():
    assert absence_rows(ISAK, 2, 1) == {5}
    got = minutes_inputs(minutes_window(ISAK, 5, 2, 1))
    assert got == pytest.approx({"mf": (80 + 78 + 76 + 90 + 90) / 450, "app": 2.0, "p60": 1.0})
    assert old_inputs(ISAK)["mf"] == pytest.approx(334 / 450)


def test_fringe_player_zeros_still_count():
    fringe = rows(0, "15s", 0, 0, "20s", 0, 90, 0, 0, "10s")   # unused sub most weeks, one start
    assert absence_rows(fringe, 2, 1) == set()
    assert minutes_inputs(minutes_window(fringe, 5, 2, 1)) == old_inputs(fringe)


def test_needs_two_starts_before_and_a_start_on_return():
    assert absence_rows(rows("30s", 90, 0, 90), 2, 1) == set()      # only one start before the run
    assert absence_rows(rows(90, 90, 0, 0, 90), 2, 1) == {2, 3}     # a two-game spell is skipped whole
    assert absence_rows(rows(90, 90, 0, 0, 90), 3, 1) == set()      # stricter setting
    assert absence_rows(rows(90, 90, 0, 90, 0, 0), 2, 2) == set()   # needs two starts back, has one
    assert absence_rows(rows(90, 90, 0, "20s", 90), 2, 0) == {2}    # starts_after=0: any return counts


def test_absentee_not_yet_back_keeps_counting():
    out_now = rows(90, 90, 90, 90, 90, 0, 0, 0)
    assert absence_rows(out_now, 2, 1) == set()
    assert minutes_inputs(minutes_window(out_now, 5, 2, 1))["mf"] == pytest.approx(2 * 90 / 450)


def test_return_as_a_substitute_does_not_yet_clear_the_spell():
    back_on_bench = rows(90, 90, 90, 0, 0, 0, "20s")
    assert absence_rows(back_on_bench, 2, 1) == set()
    assert minutes_inputs(minutes_window(back_on_bench, 5, 2, 1)) == old_inputs(back_on_bench)


def test_reinjured_after_returning_only_the_earlier_spell_is_skipped():
    rs = rows(90, 90, 0, 90, 90, 0, 0)
    assert absence_rows(rs, 2, 1) == {2}
    assert [x["minutes"] for x in minutes_window(rs, 5, 2, 1)] == [90, 90, 90, 0, 0]


def test_few_games():
    assert minutes_inputs(minutes_window(rows(90), 5, 2, 1)) == {"mf": 1.0, "app": 2.0, "p60": 1.0}
    # a skipped run always leaves at least starts_before + max(starts_after, 1) played games
    rs = rows(90, 70, 0, 0, 0, 80)
    assert minutes_window(rs, 5, 2, 1) == [rs[0], rs[1], rs[5]]
    assert minutes_inputs(minutes_window(rs, 5, 2, 1))["mf"] == pytest.approx(240 / 270)


def _full(m, start, rnd):
    return {"round": rnd, "minutes": m, "starts": start, "expected_goals": "0.1", "expected_assists": "0.1",
            "goals_scored": 0, "assists": 0, "clean_sheets": 0, "saves": 1, "bonus": 0, "yellow_cards": 0,
            "defensive_contribution": 5, "goals_conceded": 1}


def _season(pattern):
    """One player per position; the FWD (id 4) has the given minutes pattern, the rest play 90 every week."""
    els = {i: {"id": i, "team": 1, "element_type": i} for i in (1, 2, 3, 4)}
    hist = {i: [_full(90, 1, k) for k in range(1, len(pattern) + 1)] for i in (1, 2, 3)}
    hist[4] = [_full(m, int(m >= 60), k) for k, m in enumerate(pattern, 1)]
    return Season(els, {1: "AAA"}, [], hist, {}, [], len(pattern))


def test_build_players_off_reproduces_plain_last_five_and_respects_the_cut():
    pattern = [90, 90, 63, 90, 80, 0, 78, 76, 90, 90]
    s = _season(pattern)
    on = load_config().with_model(absence_starts_before=2, absence_starts_after=1)
    off = on.with_model(absence_starts_before=0)
    p_off, p_on = build_players(s, 10, off)[4], build_players(s, 10, on)[4]
    for k, v in old_inputs(s.hist[4]).items():
        assert p_off[k] == v
    assert p_on["mf"] == pytest.approx(414 / 450) and p_on["app"] == 2.0 and p_on["p60"] == 1.0
    assert {k: v for k, v in p_on.items() if k not in ("mf", "app", "p60")} == \
           {k: v for k, v in p_off.items() if k not in ("mf", "app", "p60")}
    # at cut 6 the player has not returned yet, so the 0 counts; later rows must not leak in
    early = build_players(s, 6, on)[4]
    assert early["mf"] == pytest.approx((90 + 63 + 90 + 80 + 0) / 450)
    trimmed = _season(pattern[:6])
    assert build_players(trimmed, 6, on)[4] == early
