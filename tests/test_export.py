from types import SimpleNamespace

from fplxpts.export import build_export, eligible
from fplxpts.model import Projection


def fx(event, h, a, finished=False):
    return {"event": event, "team_h": h, "team_a": a, "finished": finished}


def make(n_def=12, top=10):
    els, rates, series = {}, {}, {}
    for i in range(1, n_def + 1):
        els[i] = {"element_type": 2, "team": 1, "now_cost": 45 + i, "web_name": f"D{i}", "minutes": 900,
                  "chance_of_playing_next_round": None}
        rates[i] = {"mf": 0.9}
        series[i] = {11: i * 0.5, 12: i * 0.25, 13: 1.0, 14: 1.0, 15: 1.0}
    # ineligible: low minutes, low mf, flagged unavailable
    els[101] = {"element_type": 2, "team": 1, "now_cost": 40, "web_name": "LowMin", "minutes": 100,
                "chance_of_playing_next_round": None}
    els[102] = {"element_type": 2, "team": 1, "now_cost": 40, "web_name": "LowMf", "minutes": 900,
                "chance_of_playing_next_round": None}
    els[103] = {"element_type": 2, "team": 1, "now_cost": 40, "web_name": "Hurt", "minutes": 900,
                "chance_of_playing_next_round": 0}
    for i in (101, 102, 103):
        rates[i] = {"mf": 0.9}
        series[i] = {g: 50.0 for g in range(11, 16)}
    rates[102]["mf"] = 0.3
    fixtures = [
        fx(11, 1, 2),                    # home vs BBB
        fx(12, 3, 1),                    # away at CCC
        fx(13, 1, 2), fx(13, 2, 1),      # double
        # GW14 blank
        fx(15, 1, 3),
        fx(10, 1, 2, finished=True),     # finished: ignored
        fx(11, 1, 3, finished=True),     # finished in a window gw: ignored
    ]
    season = SimpleNamespace(elements=els, teams={1: "AAA", 2: "BBB", 3: "CCC"}, fixtures=fixtures)
    return Projection(season, rates, series, 11, 18)


def test_top_level_keys_and_gameweeks():
    d = build_export(make(), 10, generated_at="2026-11-12T06:00:00Z")
    assert set(d) == {"schema", "generated_at", "data_through_gw", "gameweeks", "positions"}
    assert d["schema"] == 1 and d["data_through_gw"] == 10
    assert d["generated_at"] == "2026-11-12T06:00:00Z"
    assert d["gameweeks"] == [11, 12, 13, 14, 15]
    assert list(d["positions"]) == ["GK", "DEF", "MID", "FWD"]


def test_top_n_sorted_descending():
    d = build_export(make(), 10, top=10)
    defs = d["positions"]["DEF"]
    assert len(defs) == 10
    totals = [p["total"] for p in defs]
    assert totals == sorted(totals, reverse=True)
    assert d["positions"]["GK"] == []


def test_total_matches_by_gw():
    for p in build_export(make(), 10)["positions"]["DEF"]:
        assert len(p["by_gw"]) == 5
        assert abs(p["total"] - sum(g["xpts"] for g in p["by_gw"])) < 0.05


def test_blank_and_double_gameweeks():
    d = build_export(make(), 10)
    by = {g["gw"]: g for g in d["positions"]["DEF"][0]["by_gw"]}
    assert by[14]["fixtures"] == []
    assert by[13]["fixtures"] == [{"opp": "BBB", "home": True}, {"opp": "BBB", "home": False}]


def test_home_away_and_opponent_and_finished_ignored():
    d = build_export(make(), 10)
    by = {g["gw"]: g for g in d["positions"]["DEF"][0]["by_gw"]}
    assert by[11]["fixtures"] == [{"opp": "BBB", "home": True}]      # finished GW11 fixture ignored
    assert by[12]["fixtures"] == [{"opp": "CCC", "home": False}]
    assert by[15]["fixtures"] == [{"opp": "CCC", "home": True}]


def test_blank_gw_xpts_zero_when_missing_from_series():
    proj = make()
    del proj.series[12][14]
    p = next(p for p in build_export(proj, 10)["positions"]["DEF"] if p["id"] == 12)
    assert p["by_gw"][3] == {"gw": 14, "xpts": 0.0, "fixtures": []}


def test_ineligible_players_excluded():
    proj = make()
    assert not {101, 102, 103} & set(eligible(proj, 2))
    names = {p["name"] for p in build_export(proj, 10, top=50)["positions"]["DEF"]}
    assert names.isdisjoint({"LowMin", "LowMf", "Hurt"})


def test_entry_fields():
    p = build_export(make(), 10)["positions"]["DEF"][0]
    assert p["name"] == "D12" and p["team"] == "AAA" and p["price"] == 5.7
