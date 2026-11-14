"""Past seasons from the community archive (archive.py) on a tiny synthetic season (tests/fixtures/archive):
four teams; R2 is a blank gameweek for BBB/DDD (their match moved to R3), R3 a double gameweek for them, R4 is
unfinished with another double; defender "Mover" moves from AAA to CCC after R2; one duplicate row and one
assistant-manager row; a previous season (2023-24) linked by player code for the prior."""
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from fplxpts import archive as A
from fplxpts import backtest as bt
from fplxpts.cli import archive_seasons, prior_season_name
from fplxpts.config import load_config
from fplxpts.model import Projector
from fplxpts.players import build_players, current_team
from fplxpts.points import actual_components, components, total
from fplxpts.teams import team_state

FIX = Path(__file__).parent / "fixtures" / "archive"
MOVER, MID, FWD = 2, 3, 4


def no_fetch(url):
    raise AssertionError(f"no network in tests: {url}")


@pytest.fixture(scope="module")
def season(tmp_path_factory):
    d = tmp_path_factory.mktemp("cache")
    for f in FIX.glob("*.csv"):
        shutil.copy(f, d / f.name)
    return A.load_archive_season(d, "2024-25", n_prior=1, fetch=no_fetch)


@pytest.fixture(scope="module")
def cfg():
    base = load_config()
    return base.with_model(prior_seasons=A.shift_prior_seasons(base.model.prior_seasons, "2024-25"))


def test_season_names_and_prior_shift():
    assert A.fpl_name("2024-25") == "2024/25"
    assert A.shift_name("2025/26", -2) == "2023/24"
    shipped = load_config().model.prior_seasons
    assert shipped == {"2025/26": 1.0, "2024/25": 0.5}
    assert A.shift_prior_seasons(shipped, "2024-25") == {"2023/24": 1.0, "2022/23": 0.5}
    assert A.shift_prior_seasons(shipped, "2025-26") == {"2024/25": 1.0, "2023/24": 0.5}
    assert A.shift_prior_seasons(shipped, "2026/27") == shipped        # the current season: unchanged


def test_scoring_rules_switch_dc_by_season():
    assert A.scoring_rules("2025-26")["dc"] and not A.scoring_rules("2024-25")["dc"]
    assert A.scoring_rules("2022-23")["gk_goal"] == 6 and A.scoring_rules("2025-26")["gk_goal"] == 10
    fx = {1: {"id": 1, "event": 1, "team_h": 1, "team_a": 2, "kickoff_time": None}}
    raw = {"element": "2", "fixture": "1", "was_home": "True", "minutes": "90", "expected_goals": "0.1",
           "expected_assists": "0", "expected_goals_conceded": "1", "defensive_contribution": "14"}
    before, after = A.match_row(raw, fx, A.scoring_rules("2024-25")), A.match_row(raw, fx, A.scoring_rules("2025-26"))
    assert before["defensive_contribution"] == 0 and after["defensive_contribution"] == 14
    assert actual_components(before, 2)["dc"] == 0 and actual_components(after, 2)["dc"] == 2


def test_loader_basic_structure(season):
    assert season.teams == {1: "AAA", 2: "BBB", 3: "CCC", 4: "DDD"}
    assert season.current_gw == 3                                        # R4 is unfinished
    assert 8 not in season.elements                                      # assistant manager dropped
    assert season.elements[MOVER]["element_type"] == 2 and season.elements[MOVER]["web_name"] == "Mover"
    assert season.elements[MOVER]["status"] == "a" and season.elements[MOVER]["chance_of_playing_next_round"] is None
    assert [r["fixture"] for r in season.hist[MID]] == [1, 4, 6]       # duplicate (Mid, fixture 4) dropped
    assert len(season.fin) == 6 and {x["ev"] for x in season.fin} == {1, 2, 3}
    f4 = next(x for x in season.fin if x["h"] == 2 and x["a"] == 4)
    assert f4 == {"ev": 3, "h": 2, "a": 4, "xg_h": 2.1, "xg_a": 1.5}   # team xG from the keepers' xGC
    assert all(r["defensive_contribution"] == 0 for rows in season.hist.values() for r in rows)   # no dc in 2024/25


def test_double_and_blank_gameweeks(season, cfg):
    mid = season.hist[MID]
    assert [r["round"] for r in mid] == [1, 3, 3]                        # blank in R2, double in R3
    assert [(r["opponent_team"], r["was_home"]) for r in mid if r["round"] == 3] == [(4, True), (3, False)]
    assert bt.played_rounds(season) == [1, 2, 3]
    rows = bt.evaluate(season, cfg.without_calibration(), cuts=[1, 2], horizon=5, last_gw=3)
    r3 = [r for r in rows if r.pid == MID and r.cut == 2 and r.rnd == 3]
    assert len(r3) == 2 and r3[0].comps != r3[1].comps                   # one prediction per match, own opponent
    assert sorted(r.points for r in r3) == [2, 7]
    assert not [r for r in rows if r.pid == MID and r.rnd == 2]          # nothing predicted in his blank week


def test_top_k_sums_a_double_gameweek():
    R = namedtuple("R", "pid cut rnd pos comps actual points")
    comps = lambda x: {c: (x if c == "app" else 0.0) for c in ("app", "goal", "assist", "cs", "gc", "dc", "bonus", "sav", "yc")}
    rows = [R(1, 1, 2, 3, comps(3.0), None, 1), R(1, 1, 2, 3, comps(3.0), None, 2),   # 2 matches: 6 projected, 3 scored
            R(2, 1, 2, 3, comps(5.0), None, 10)]
    assert bt.top_k_actual(rows, k=1) == 3.0                             # player 1 (6.0 over the round) ranks first
    assert bt.top_k_actual(rows, k=2) == 6.5


def test_mid_season_transfer_uses_the_club_of_each_match(season, cfg):
    mv = season.hist[MOVER]
    assert [r["team"] for r in mv] == [1, 1, 3]
    assert season.elements[MOVER]["team"] == 3                           # end-of-season club
    assert build_players(season, 2, cfg)[MOVER]["team"] == 1             # at the cutoff he is still at AAA
    assert build_players(season, 3, cfg)[MOVER]["team"] == 3
    assert current_team([], 7) == 7 and current_team([{"round": 1}], 7) == 7   # live rows have no team field
    p = build_players(season, 2, cfg)[MOVER]
    st = team_state(season, 2, cfg)
    row = mv[2]                                                          # R3 for CCC at home v BBB
    assert bt.at_club(p, row)["team"] == 3 and bt.at_club(p, {"round": 3})["team"] == 1
    rows = bt.evaluate(season, cfg.without_calibration(), cuts=[2], horizon=5, last_gw=3)
    got = next(r for r in rows if r.pid == MOVER)
    assert got.comps == components({**p, "team": 3}, "h", 2, st)


def test_prior_from_previous_season_by_code(season, cfg):
    past = season.past[MOVER]                                            # element 40 in 2023/24, same code 9002
    assert len(past) == 1 and past[0]["season_name"] == "2023/24" and past[0]["minutes"] == 170
    assert float(past[0]["expected_goals"]) == pytest.approx(0.40) and float(past[0]["expected_assists"]) == pytest.approx(0.10)
    assert season.past[FWD] == []                                        # not in the previous season
    assert "2023/24" in cfg.model.prior_seasons


def test_rounds_without_xg_are_dropped():
    rows = lambda rnd, xg: {"round": rnd, "expected_goals": xg, "expected_goals_conceded": 0.0, "minutes": 90}
    hist = {1: [rows(1, 0.0), rows(2, 0.0), rows(3, 0.4)], 2: [rows(1, 0.0)]}
    assert A.xg_rounds_only(hist) == {1: [rows(3, 0.4)]}


def test_archive_csv_downloads_once(tmp_path):
    calls = []
    fetch = lambda url: calls.append(url) or b"a,b\n1,2\n"
    assert A.read_csv(A.archive_csv(tmp_path, "2024-25", "teams", fetch)) == [{"a": "1", "b": "2"}]
    assert A.read_csv(A.archive_csv(tmp_path, "2024-25", "teams", fetch)) == [{"a": "1", "b": "2"}]
    assert calls == ["https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/2024-25/teams.csv"]


def test_archive_seasons_cli_names():
    assert archive_seasons(["all"]) == ["2025-26", "2024-25", "2023-24", "2022-23"]
    assert archive_seasons(["2024/25", "2024-25"]) == ["2024-25"]
    with pytest.raises(SystemExit):
        archive_seasons(["2019-20"])


def test_projector_adds_both_fixtures_of_a_double_gameweek(season, cfg):
    pr = Projector(season, cfg.without_calibration(), cut=3)
    proj = pr.project(4, 4)
    p = pr.players[MID]                                                  # BBB: B v A and D v B in R4
    want = sum(total(components(p, v, o, pr.state), 3) for v, o in (("h", 1), ("a", 4)))
    assert proj.series[MID][4] == pytest.approx(want)
    one = total(components(pr.players[1], "a", 2, pr.state), 1)          # AAA plays once in R4
    assert proj.series[1][4] == pytest.approx(one)


def test_prior_season_name_previous_and_no_look_ahead():
    assert prior_season_name("previous", "2026/27") == "2025-26"
    assert prior_season_name("previous", "2024-25") == "2023-24"
    assert prior_season_name("2024/25", "2026/27") == "2024-25"
    for bad, target in (("2025-26", "2025-26"), ("2025-26", "2024-25"), ("previous", "2022-23"), ("2019-20", "2026/27")):
        with pytest.raises(SystemExit):
            prior_season_name(bad, target)
