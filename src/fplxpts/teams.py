"""Team attack/defence ratings from per-fixture xG: venue-normalised, schedule-adjusted, recency-weighted, shrunk."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .data import Season
from .players import counts_for_dc, dc_hit, pool_hit_rates, posgrp

opp_of = lambda v: "a" if v == "h" else "h"


@dataclass
class TeamState:
    lg: dict       # league-average xG by venue {"h": .., "a": ..}
    att: dict      # team id -> attack rating (1.0 = average), recency-weighted
    dfn: dict      # team id -> defence rating (xG conceded relative to average; lower is better)
    pn_att: dict   # average attack environment each team's players earned their rates in
    pn_opp: dict   # average opposing attack each team faced (used for goalkeeper saves)
    dc_opp: dict = field(default_factory=dict)  # team id -> DC hits its opponents make vs expectation (1.0 = average)
    pn_dc: dict = field(default_factory=dict)   # average dc_opp of the opponents each team has faced
    opp_xg_gamma: float = 1.0  # damping of the opponent-xG matchup used for clean sheets (1.0 = undamped)
    # (team, opp, venue) -> (expected goals for, against) in that fixture, overriding the rating product
    # (bookmaker-anchored fixtures, see anchor_fixtures); a (home, away) pair occurs once a season
    fixture_xg: dict = field(default_factory=dict)


def damped_opp_xg(lg_v: float, att_opp: float, dfn_team: float, gamma: float = 1.0) -> float:
    """Opponent's expected goals, with the matchup multiplier pulled towards 1 (the league venue average).

    gamma = 1 is the plain product lg_v * att_opp * dfn_team; gamma < 1 shrinks it geometrically.
    """
    return lg_v * (att_opp * dfn_team) ** gamma


def shrink_ratio(obs: float, exp: float, k: float) -> float:
    """Observed / expected count, shrunk towards 1.0 with k pseudo-units of expectation."""
    return (obs + k) / (exp + k)


def dc_obs_exp(season: Season, cut: int, min_live_minutes: float) -> dict:
    """team id -> (DC hits made against it, hits expected from league position-group rates), rounds <= cut.

    Counts outfield players' 60+ minute appearances, the same population players.py builds hit rates from.
    """
    els = season.elements
    H = {p: [r for r in rows if r["round"] <= cut] for p, rows in season.hist.items()}
    live = [p for p in H if sum(r["minutes"] for r in H[p]) >= min_live_minutes]
    pool = pool_hit_rates(H, live, els)
    out: dict = {}
    for p in live:
        pos = els[p]["element_type"]
        if pos == 1:
            continue
        for r in H[p]:
            if counts_for_dc(r):
                o, e = out.get(r["opponent_team"], (0.0, 0.0))
                out[r["opponent_team"]] = (o + dc_hit(r, pos), e + pool[posgrp(pos)])
    return out


def dc_opp_factors(obs_exp: dict, k: float) -> dict:
    """team id -> shrunk 'DC allowed' factor; k <= 0 switches the feature off (no factors, i.e. all 1.0)."""
    if k <= 0:
        return {}
    return {t: shrink_ratio(o, e, k) for t, (o, e) in obs_exp.items()}


MIN_RATING = 0.2  # floor on an opponent rating used as a divisor (guards against near-zero ratings)


def game_log(fin: list) -> dict:
    """team id -> chronological games [(ev, opp, venue, xg_for, xg_against)] from finished fixtures."""
    log: dict = {}
    for x in sorted(fin, key=lambda x: x["ev"]):
        log.setdefault(x["h"], []).append((x["ev"], x["a"], "h", x["xg_h"], x["xg_a"]))
        log.setdefault(x["a"], []).append((x["ev"], x["h"], "a", x["xg_a"], x["xg_h"]))
    return log


def recency_weights(n: int, hl: float | None) -> list:
    """Weights for n chronological games, halving every hl games back (None = equal weights)."""
    return [1.0 if hl is None else 0.5 ** ((n - 1 - i) / hl) for i in range(n)]


def ratings(log: dict, lg: dict, teams, hl: float | None, k: float, sos_iters: int = 0,
            extra: dict | None = None, extra_w: tuple = (0.0, 0.0)) -> tuple:
    """Attack and defence ratings (1.0 = league average), recency-weighted and shrunk with k pseudo-games.

    Each game's xG for (against) is divided by the league venue average and, when sos_iters > 0, also by the
    opponent's defence (attack) rating, so a team is not flattered by a soft schedule. The opponent ratings
    come from the previous pass (fixed-point iteration, sos_iters passes); each pass is rescaled so the league
    mean of each rating stays at its unadjusted value. sos_iters = 0 is the plain venue-normalised average.

    `extra` {team: [(opp, venue, goals_for, goals_against)]} adds odds-implied games (see odds_games) with weight
    extra_w = (attack, defence) each, relative to the most recent played game; they count as that many extra games
    in the shrinkage. No extra games (the default) is exactly the plain computation.
    """
    extra = extra or {}

    def one_pass(opp_att: dict, opp_dfn: dict) -> tuple:
        att, dfn = {}, {}
        for t in teams:
            lt = log.get(t, [])
            n = len(lt)
            if n == 0:
                att[t] = dfn[t] = 1.0
                continue
            ws = recency_weights(n, hl)
            sw = sum(ws)
            f_ = sum(w * (r[3] / (lg[r[2]] * max(opp_dfn.get(r[1], 1.0), MIN_RATING))) for w, r in zip(ws, lt)) / sw
            a_ = sum(w * (r[4] / (lg[opp_of(r[2])] * max(opp_att.get(r[1], 1.0), MIN_RATING))) for w, r in zip(ws, lt)) / sw
            ex = extra.get(t, [])
            if ex and (extra_w[0] > 0 or extra_w[1] > 0):
                wa, wd = extra_w[0] * len(ex), extra_w[1] * len(ex)
                ef = sum(e[2] / (lg[e[1]] * max(opp_dfn.get(e[0], 1.0), MIN_RATING)) for e in ex) / len(ex)
                ea = sum(e[3] / (lg[opp_of(e[1])] * max(opp_att.get(e[0], 1.0), MIN_RATING)) for e in ex) / len(ex)
                att[t] = ((f_ * sw + ef * wa) / (sw + wa) * (n + wa) + k) / (n + wa + k)
                dfn[t] = ((a_ * sw + ea * wd) / (sw + wd) * (n + wd) + k) / (n + wd + k)
                continue
            att[t] = (f_ * n + k) / (n + k)
            dfn[t] = (a_ * n + k) / (n + k)
        return att, dfn

    att0, dfn0 = one_pass({}, {})
    att, dfn = att0, dfn0
    for _ in range(sos_iters):
        att, dfn = one_pass(att, dfn)
        att, dfn = rescale_mean(att, att0), rescale_mean(dfn, dfn0)
    return att, dfn


def rescale_mean(r: dict, ref: dict) -> dict:
    """Scale ratings r so their mean equals the mean of ref."""
    s = sum(ref.values()) / sum(r.values())
    return {t: v * s for t, v in r.items()}


def odds_games(odds: dict) -> dict:
    """{(home, away): MatchOdds} -> {team: [(opp, venue, goals_for, goals_against)]} as extra rating games."""
    out: dict = {}
    for (h, a), o in odds.items():
        out.setdefault(h, []).append((a, "h", o.lam_home, o.lam_away))
        out.setdefault(a, []).append((h, "a", o.lam_away, o.lam_home))
    return out


def model_xg(st: TeamState, team: int, opp: int, venue: str) -> tuple:
    """The ratings' expected goals (for, against) of `team` playing `opp` at `venue`, ignoring any anchoring."""
    return st.lg[venue] * st.att[team] * st.dfn[opp], st.lg[opp_of(venue)] * st.att[opp] * st.dfn[team]


def fixture_xg(st: TeamState, team: int, opp: int, venue: str) -> tuple:
    """Expected goals (for, against) used for this fixture: the anchored values if any, else the ratings'."""
    return st.fixture_xg.get((team, opp, venue)) or model_xg(st, team, opp, venue)


def blend(model: float, odds: float, w: float) -> float:
    """Linear blend of a model and an odds-implied expected-goals number: w = 0 model only, w = 1 odds only."""
    return model if w <= 0 else odds if w >= 1 else (1 - w) * model + w * odds


SIDES = ("both", "attack", "defence")


def side_weights(w: float, side: str) -> tuple:
    """(weight on the attacking side, weight on the defensive side) for one blend weight and side setting."""
    if side not in SIDES:
        raise ValueError(f"odds_side must be one of {SIDES}, got {side!r}")
    return (w if side in ("both", "attack") else 0.0, w if side in ("both", "defence") else 0.0)


def anchor_fixtures(st: TeamState, odds: dict, w: float, side: str = "both") -> dict:
    """{(team, opp, venue): (xg_for, xg_against)} for the fixtures in `odds`, each team's goals blended with the
    odds-implied ones. `side` = "attack" blends only a team's own goals (its goals/assists multiplier), "defence"
    only the goals it concedes (clean sheet, goals conceded, saves), "both" both. Empty when w <= 0."""
    wa, wd = side_weights(w, side)
    if wa <= 0 and wd <= 0:
        return {}
    out = {}
    for (h, a), o in odds.items():
        for t, u, v, gf, ga in ((h, a, "h", o.lam_home, o.lam_away), (a, h, "a", o.lam_away, o.lam_home)):
            mf, ma = model_xg(st, t, u, v)
            out[(t, u, v)] = (blend(mf, gf, wa), blend(ma, ga, wd))
    return out


def team_state(season: Season, cut: int, cfg: Config, odds: dict | None = None) -> TeamState:
    """Team ratings from fixtures up to round `cut`. `odds` {(home, away): MatchOdds} must hold only odds known at
    `cut` (in the backtest, round cut + 1: odds.available_at); they are used only if the odds settings are on."""
    fc = [x for x in season.fin if x["ev"] <= cut]
    lg = {"h": sum(x["xg_h"] for x in fc) / len(fc), "a": sum(x["xg_a"] for x in fc) / len(fc)}
    log = game_log(fc)
    m = cfg.model
    # past-opponent norms use unweighted ratings, matching how player rates were earned; they are schedule-
    # adjusted the same way as the forward ratings so the numerator and denominator of att_m / opp_m agree
    att0, dfn0 = ratings(log, lg, season.teams, None, m.team_shrink_k, m.team_sos_iters)
    pn_att = {t: sum(lg[r[2]] * dfn0[r[1]] for r in log[t]) / len(log[t]) for t in log}
    pn_opp = {t: sum(lg[opp_of(r[2])] * att0[r[1]] for r in log[t]) / len(log[t]) for t in log}
    odds = odds or {}
    extra_w = side_weights(m.odds_ratings_weight, m.odds_side) if odds else (0.0, 0.0)
    att, dfn = ratings(log, lg, season.teams, m.team_halflife, m.team_shrink_k, m.team_sos_iters, odds_games(odds), extra_w)
    dc_opp = dc_opp_factors(dc_obs_exp(season, cut, m.min_live_minutes), m.dc_opp_k)
    pn_dc = {t: sum(dc_opp.get(r[1], 1.0) for r in log[t]) / len(log[t]) for t in log} if dc_opp else {}
    st = TeamState(lg, att, dfn, pn_att, pn_opp, dc_opp, pn_dc, m.opp_xg_gamma)
    st.fixture_xg = anchor_fixtures(st, odds, m.odds_weight, m.odds_side)
    return st
