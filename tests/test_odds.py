import json
import math
import os
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from fplxpts import backtest as bt
from fplxpts import odds as od
from fplxpts.points import anchored, components
from fplxpts.teams import TeamState, anchor_fixtures, blend, fixture_xg, model_xg, ratings, side_weights

FIX = Path(__file__).parent / "fixtures"
TEAMS = ["ARS", "AVL", "BOU", "BRE", "BHA", "CHE", "COV", "CRY", "EVE", "FUL",
         "HUL", "IPS", "LEE", "LIV", "MCI", "MUN", "NEW", "NFO", "SUN", "TOT"]
SHORT = {s: i for i, s in enumerate(TEAMS, 1)}
FAKE_KEY = "test-key-0123456789abcdef"   # not a real key


# --- de-vig and the Poisson solver --------------------------------------------------------------------------

def test_devig_sums_to_one():
    for prices in ([1.41, 4.7, 6.25], [2.1, 3.5, 3.41], [1.19, 6.77, 14.19]):
        p = od.devig_1x2(*prices)
        assert sum(p) == pytest.approx(1.0) and all(0 < x < 1 for x in p)
        assert p[0] > p[2] if prices[0] < prices[2] else p[0] < p[2]
    assert sum(od.devig_two_way(1.55, 2.38)) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        od.devig([1.0, 3.0])


@pytest.mark.parametrize("lh", [0.15, 0.4, 0.9, 1.4, 2.0, 3.0, 4.2])
@pytest.mark.parametrize("la", [0.15, 0.5, 1.1, 1.8, 3.5])
def test_poisson_round_trip(lh, la):
    ph, pd, pa = od.result_probs(lh, la)
    assert ph + pd + pa == pytest.approx(1.0, abs=1e-9)
    po = od.p_over(lh + la, 2.5)
    rh, ra = od.implied_lambdas(ph, pa, po, 2.5)
    assert rh == pytest.approx(lh, abs=1e-6) and ra == pytest.approx(la, abs=1e-6)


@pytest.mark.parametrize("line", [0.5, 1.5, 2.5, 3.5, 4.5])
def test_total_from_over_inverts_p_over(line):
    for t in (0.8, 2.0, 2.7, 4.0):
        assert od.total_from_over(od.p_over(t, line), line) == pytest.approx(t, abs=1e-6)


def test_quarter_and_whole_lines_rejected():
    for line in (2.0, 2.25, 2.75):
        with pytest.raises(ValueError):
            od.p_over(2.5, line)


def test_more_overs_and_stronger_home_mean_more_home_goals():
    lo = od.implied_lambdas(0.5, 0.25, 0.45)
    hi_total = od.implied_lambdas(0.5, 0.25, 0.60)
    hi_home = od.implied_lambdas(0.65, 0.12, 0.45)
    assert sum(hi_total) > sum(lo)
    assert hi_home[0] > lo[0] and hi_home[1] < lo[1] and sum(hi_home) == pytest.approx(sum(lo), abs=1e-6)


# --- team names -------------------------------------------------------------------------------------------

def test_team_name_mapping():
    assert od.team_id("Nott'm Forest", SHORT) == od.team_id("Nottingham Forest", SHORT) == SHORT["NFO"]
    assert od.team_id("Brighton and Hove Albion", SHORT) == od.team_id("Brighton", SHORT) == SHORT["BHA"]
    assert od.team_id("Man United", SHORT) == od.team_id("Manchester United", SHORT) == SHORT["MUN"]
    assert od.team_id(" tottenham hotspur ", SHORT) == SHORT["TOT"]
    with pytest.raises(KeyError, match="Wimbledon"):
        od.team_id("Wimbledon FC", SHORT)
    with pytest.raises(KeyError, match="West Ham"):        # known name, but not in this season's teams
        od.team_id("West Ham", SHORT)


# --- Football-Data.co.uk CSV ---------------------------------------------------------------------------------

def test_parse_football_data_fixture():
    text = (FIX / "football_data_E0_sample.csv").read_text(encoding="utf-8")
    op, cl = od.parse_football_data(text, SHORT, "open"), od.parse_football_data(text, SHORT, "close")
    assert len(op) == 4 and len(cl) == 5          # the last row has no pre-match home price
    m = op[0]
    assert (m.home, m.away, m.kickoff) == (SHORT["ARS"], SHORT["COV"], "2026-08-21")
    assert m.lam_home > 2 and 0 < m.lam_away < 1
    assert m.p_home + m.p_draw + m.p_away == pytest.approx(1.0)
    ph, _, pa = od.result_probs(m.lam_home, m.lam_away)
    assert ph / (ph + pa) == pytest.approx(m.p_home / (m.p_home + m.p_away), abs=1e-6)
    assert od.p_over(m.lam_home + m.lam_away, 2.5) == pytest.approx(od.devig_two_way(1.55, 2.38)[0], abs=1e-6)
    with pytest.raises(KeyError):
        od.parse_football_data(text.replace("Coventry", "Wimbledon"), SHORT)


def test_football_data_csv_cache(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return (FIX / "football_data_E0_sample.csv").read_bytes()

    t1 = od.football_data_csv(tmp_path, "2627", ttl=3600, fetch=fetch)
    t2 = od.football_data_csv(tmp_path, "2627", ttl=3600, fetch=fetch)       # fresh cache: no download
    assert t1 == t2 and len(calls) == 1 and calls[0].endswith("/mmz4281/2627/E0.csv")
    assert (tmp_path / "football-data_E0_2627.csv").exists()
    old = time.time() - 7200
    os.utime(tmp_path / "football-data_E0_2627.csv", (old, old))

    def broken(url):
        raise OSError("offline")

    assert od.football_data_csv(tmp_path, "2627", ttl=3600, fetch=broken) == t1      # stale copy used offline
    with pytest.raises(OSError):
        od.football_data_csv(tmp_path / "empty", "2627", fetch=broken)


def test_season_code():
    assert od.season_code([{"kickoff_time": "2026-08-21T19:00:00Z"}, {"kickoff_time": "2027-05-23T15:00:00Z"}]) == "2627"


def test_odds_by_round_and_availability():
    fixtures = [{"event": 1, "team_h": 1, "team_a": 2, "kickoff_time": "2026-08-21T19:00:00Z"},
                {"event": 2, "team_h": 2, "team_a": 1, "kickoff_time": "2026-08-29T14:00:00Z"},
                {"event": None, "team_h": 3, "team_a": 1, "kickoff_time": None}]
    ms = [od.MatchOdds(1, 2, "2026-08-21", 1.5, 1.0), od.MatchOdds(2, 1, "2026-09-20", 1.2, 1.1),   # date too far
          od.MatchOdds(3, 1, None, 1.0, 1.0)]                                                        # no event
    by = od.odds_by_round(ms, fixtures)
    assert list(by) == [1] and list(by[1]) == [(1, 2)]
    assert od.available_at({1: {"a": 1}, 2: {"b": 2}, 3: {"c": 3}}, 1) == {"b": 2}
    assert od.available_at({1: {"a": 1}}, 5) == {}


# --- The Odds API -------------------------------------------------------------------------------------------

def test_parse_odds_api_fixture():
    events = json.loads((FIX / "odds_api_sample.json").read_text())
    ms, unknown = od.parse_odds_api(events, SHORT)
    assert len(ms) == 1 and len(unknown) == 1 and "Wimbledon" in unknown[0]   # e2 has no totals -> skipped
    m = ms[0]
    assert (m.home, m.away, m.n_books) == (SHORT["MCI"], SHORT["FUL"], 2)
    a, b = od.devig_1x2(1.41, 4.7, 6.25), od.devig_1x2(1.44, 4.6, 6.0)
    assert m.p_home == pytest.approx((a[0] + b[0]) / 2)
    t = (od.total_from_over(od.devig_two_way(1.65, 2.2)[0], 2.5) + od.total_from_over(od.devig_two_way(2.6, 1.45)[0], 3.5)) / 2
    assert m.lam_home + m.lam_away == pytest.approx(t, abs=1e-6)                # 2.75 line ignored
    assert m.lam_home > m.lam_away


def test_parse_dotenv():
    text = '''# comment
ODDS_API_KEY="abc def"
export OTHER='x#y'
PLAIN=value # trailing comment
EMPTY=
  SPACED = 42
NOEQUALS
'''
    env = od.parse_dotenv(text)
    assert env == {"ODDS_API_KEY": "abc def", "OTHER": "x#y", "PLAIN": "value", "EMPTY": "", "SPACED": "42"}


def test_api_key_precedence(tmp_path):
    f = tmp_path / ".env"
    f.write_text("ODDS_API_KEY=from-file\n")
    assert od.api_key({"ODDS_API_KEY": "from-env"}, f) == "from-env"
    assert od.api_key({"ODDS_API_KEY": ""}, f) == "from-file"            # empty (e.g. missing CI secret) -> file
    assert od.api_key({}, f) == "from-file"
    assert od.api_key({}, tmp_path / "missing.env") is None
    f.write_text("ODDS_API_KEY=\n")
    assert od.api_key({}, f) is None


def _season():
    fixtures = [{"id": 1, "event": 11, "team_h": SHORT["MCI"], "team_a": SHORT["FUL"], "finished": False,
                 "kickoff_time": "2026-11-21T12:30:00Z"},
                {"id": 2, "event": 11, "team_h": SHORT["AVL"], "team_a": SHORT["SUN"], "finished": False,
                 "kickoff_time": "2026-11-21T15:00:00Z"}]
    return SimpleNamespace(fixtures=fixtures, team_ids=SHORT)


def test_live_odds_fallback_without_key(tmp_path):
    live = od.live_odds(_season(), 11, tmp_path, None)
    assert live.anchored == 0 and live.fixtures == 2 and live.summary() is None
    assert "0 of 2" in live.message() and "2 use the model" in live.message() and "no ODDS_API_KEY" in live.message()


def test_live_odds_fallback_on_failed_request(tmp_path):
    def fail(key):
        raise od.OddsError("The Odds API request failed (401)")

    live = od.live_odds(_season(), 11, tmp_path, FAKE_KEY, fetch=fail)
    assert live.anchored == 0 and "401" in live.message() and FAKE_KEY not in live.message()
    assert not (tmp_path / od.ODDS_CACHE).exists()


def test_live_odds_cached_and_key_never_stored(tmp_path):
    calls = []
    events = json.loads((FIX / "odds_api_sample.json").read_text())

    def fetch(key):
        calls.append(1)
        return events, {"x-requests-remaining": "498"}

    live = od.live_odds(_season(), 11, tmp_path, FAKE_KEY, fetch=fetch)
    again = od.live_odds(_season(), 11, tmp_path, FAKE_KEY, fetch=fetch)
    assert len(calls) == 1                                    # second call served from the disk cache
    assert live.anchored == again.anchored == 1               # AVL-SUN has no totals -> falls back
    assert "1 of 2" in live.message() and "Wimbledon" in live.message()
    assert live.summary()["fixtures_anchored"] == 1 and live.summary()["source"] == "The Odds API"
    for f in tmp_path.iterdir():
        assert FAKE_KEY not in f.name and FAKE_KEY not in f.read_text()


def test_fetch_error_does_not_leak_key(monkeypatch):
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized " + req.full_url, {}, None)

    monkeypatch.setattr(od.urllib.request, "urlopen", boom)
    with pytest.raises(od.OddsError) as ei:
        od.fetch_odds_api(FAKE_KEY)
    e = ei.value
    assert FAKE_KEY not in str(e) and FAKE_KEY not in repr(e) and "401" in str(e)
    assert e.__cause__ is None and e.__context__ is None


# --- model integration --------------------------------------------------------------------------------------

def state(**kw):
    return TeamState(lg={"h": 1.5, "a": 1.2}, att={1: 1.1, 2: 0.9}, dfn={1: 0.95, 2: 1.05},
                     pn_att={1: 1.35, 2: 1.3}, pn_opp={1: 1.3, 2: 1.4}, **kw)


def player(pos=3):
    return {"pos": pos, "team": 1, "xg90": 0.4, "xa90": 0.2, "bon_base90": 0.15,
            "bon_k": {"base": 0.1, "goal": 0.8, "assist": 0.5, "cs": 0.4, "sav": 0.1},
            "sav90": 3.0 if pos == 1 else 0.0, "yc90": 0.1, "hit": 0.2, "mf": 0.9, "app": 1.9, "p60": 0.9}


ODDS = {(1, 2): od.MatchOdds(1, 2, None, 2.2, 0.7)}


def test_blend_and_side_weights():
    assert blend(1.0, 2.0, 0.0) == 1.0 and blend(1.0, 2.0, 1.0) == 2.0 and blend(1.0, 2.0, 0.25) == pytest.approx(1.25)
    assert side_weights(0.5, "both") == (0.5, 0.5) and side_weights(0.5, "attack") == (0.5, 0.0)
    assert side_weights(0.5, "defence") == (0.0, 0.5)
    with pytest.raises(ValueError):
        side_weights(0.5, "defense")


def test_weight_zero_is_model_only_and_off_reproduces_components():
    st = state()
    assert anchor_fixtures(st, ODDS, 0.0) == {}
    st.fixture_xg = anchor_fixtures(st, ODDS, 0.0)
    for pos in (1, 2, 3, 4):
        assert components(player(pos), "h", 2, st) == components(player(pos), "h", 2, state())   # exact


def test_weight_one_is_odds_only():
    st = state()
    st.fixture_xg = anchor_fixtures(st, ODDS, 1.0)
    assert fixture_xg(st, 1, 2, "h") == (2.2, 0.7) and fixture_xg(st, 2, 1, "a") == (0.7, 2.2)
    assert fixture_xg(st, 1, 2, "a") == model_xg(st, 1, 2, "a")          # reverse fixture not anchored
    d = components(player(2), "h", 2, st)
    assert d["cs"] == pytest.approx(math.exp(-0.7) * 0.9 * 4)
    mf_, _ = model_xg(st, 1, 2, "h")
    base = components(player(3), "h", 2, state())
    assert components(player(3), "h", 2, st)["goal"] == pytest.approx(base["goal"] * 2.2 / mf_)


def test_anchoring_at_model_values_is_identity():
    st = state(opp_xg_gamma=0.7)
    st.fixture_xg = {(1, 2, "h"): model_xg(st, 1, 2, "h")}
    for pos in (1, 2, 3, 4):
        a, b = components(player(pos), "h", 2, st), components(player(pos), "h", 2, state(opp_xg_gamma=0.7))
        assert a == pytest.approx(b, rel=1e-12)


def test_anchored_formula():
    att_m, opp_m, opp_xg, cs_xg = anchored(0.9, 1.1, 1.2, 1.5, (3.0, 0.6), 1.2, 1.0)
    assert att_m == pytest.approx(1.8) and opp_m == pytest.approx(0.55) and opp_xg == 0.6 and cs_xg == pytest.approx(0.6)
    assert anchored(0.9, 1.1, 1.2, 1.5, (3.0, 0.6), 1.2, 0.5)[3] == pytest.approx(1.2 * 0.5 ** 0.5)


def test_sides_touch_only_their_components():
    att, dfn = state(), state()
    att.fixture_xg = anchor_fixtures(att, ODDS, 1.0, "attack")
    dfn.fixture_xg = anchor_fixtures(dfn, ODDS, 1.0, "defence")
    base = components(player(1), "h", 2, state())
    ca, cd = components(player(1), "h", 2, att), components(player(1), "h", 2, dfn)
    assert ca["cs"] == base["cs"] and ca["sav"] == base["sav"] and ca["gc"] == base["gc"]
    assert cd["cs"] > base["cs"] and cd["sav"] < base["sav"]
    m3 = components(player(3), "h", 2, state())
    assert components(player(3), "h", 2, att)["goal"] > m3["goal"] and components(player(3), "h", 2, dfn)["goal"] == m3["goal"]


def test_ratings_extra_games():
    log = {1: [(1, 2, "h", 2.0, 1.0), (2, 2, "a", 1.0, 1.5)], 2: [(1, 1, "a", 1.0, 2.0), (2, 1, "h", 1.5, 1.0)]}
    lg = {"h": 1.5, "a": 1.25}
    plain = ratings(log, lg, [1, 2], 3.0, 3.0, 2)
    assert ratings(log, lg, [1, 2], 3.0, 3.0, 2, {}, (1.0, 1.0)) == plain
    assert ratings(log, lg, [1, 2], 3.0, 3.0, 2, {1: [(2, "h", 3.0, 0.2)]}, (0.0, 0.0)) == plain
    plain0 = ratings(log, lg, [1, 2], 3.0, 3.0, 0)
    ex = {1: [(2, "h", 3.0, 0.2)], 2: [(1, "a", 0.2, 3.0)]}
    att, dfn = ratings(log, lg, [1, 2], 3.0, 3.0, 0, ex, (1.0, 1.0))
    assert att[1] > plain0[0][1] and dfn[1] < plain0[1][1] and att[2] < plain0[0][2] and dfn[2] > plain0[1][2]
    att_d, dfn_d = ratings(log, lg, [1, 2], 3.0, 3.0, 0, ex, (0.0, 1.0))      # defence side only
    assert att_d == pytest.approx(plain0[0]) and dfn_d[1] < plain0[1][1]
    # one extra game at weight 1 with no recency decay and no shrinkage is a plain average with the real games
    a1, _ = ratings({1: [(1, 2, "h", 1.5, 1.0)]}, lg, [1], None, 0.0, 0, {1: [(2, "h", 3.0, 1.0)]}, (1.0, 1.0))
    assert a1[1] == pytest.approx((1.5 / 1.5 + 3.0 / 1.5) / 2)


def test_backtest_uses_only_next_round_odds(monkeypatch):
    seen = {}

    def fake_team_state(season, cut, cfg, odds=None):
        seen[cut] = dict(odds or {})
        return state()

    monkeypatch.setattr(bt, "team_state", fake_team_state)
    monkeypatch.setattr(bt, "build_players", lambda season, cut, cfg: {})
    rounds = {r: {(r, r + 100): f"odds for round {r}"} for r in range(1, 11)}
    season = SimpleNamespace(current_gw=10, hist={}, fixtures=[])
    bt.evaluate(season, None, list(range(1, 10)), 5, 10, rounds)
    bt.team_rows(season, None, list(range(1, 10)), 5, 10, rounds)
    assert sorted(seen) == list(range(1, 10))
    for c, odds in seen.items():
        assert list(odds.values()) == [f"odds for round {c + 1}"]
