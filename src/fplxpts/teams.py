"""Team attack/defence ratings from per-fixture xG, venue-normalised, recency-weighted and shrunk."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .data import Season

opp_of = lambda v: "a" if v == "h" else "h"


@dataclass
class TeamState:
    lg: dict       # league-average xG by venue {"h": .., "a": ..}
    att: dict      # team id -> attack rating (1.0 = average), recency-weighted
    dfn: dict      # team id -> defence rating (xG conceded relative to average; lower is better)
    pn_att: dict   # average attack environment each team's players earned their rates in
    pn_opp: dict   # average opposing attack each team faced (used for goalkeeper saves)


def team_state(season: Season, cut: int, cfg: Config) -> TeamState:
    fc = [x for x in season.fin if x["ev"] <= cut]
    lg = {"h": sum(x["xg_h"] for x in fc) / len(fc), "a": sum(x["xg_a"] for x in fc) / len(fc)}
    log: dict = {}
    for x in fc:
        log.setdefault(x["h"], []).append((x["ev"], x["a"], "h", x["xg_h"], x["xg_a"]))
        log.setdefault(x["a"], []).append((x["ev"], x["h"], "a", x["xg_a"], x["xg_h"]))
    k = cfg.model.team_shrink_k

    def ratings(hl):
        att, dfn = {}, {}
        for t in season.teams:
            lt = log.get(t, [])
            n = len(lt)
            if n == 0:
                att[t] = dfn[t] = 1.0
                continue
            ws = [1.0 if hl is None else 0.5 ** ((n - 1 - i) / hl) for i in range(n)]
            sw = sum(ws)
            f_ = sum(w * (r[3] / lg[r[2]]) for w, r in zip(ws, lt)) / sw
            a_ = sum(w * (r[4] / lg[opp_of(r[2])]) for w, r in zip(ws, lt)) / sw
            att[t] = (f_ * n + k) / (n + k)
            dfn[t] = (a_ * n + k) / (n + k)
        return att, dfn

    att0, dfn0 = ratings(None)   # past-opponent norms use unweighted ratings, matching how player rates were earned
    pn_att = {t: sum(lg[r[2]] * dfn0[r[1]] for r in log[t]) / len(log[t]) for t in log}
    pn_opp = {t: sum(lg[opp_of(r[2])] * att0[r[1]] for r in log[t]) / len(log[t]) for t in log}
    att, dfn = ratings(cfg.model.team_halflife)
    return TeamState(lg, att, dfn, pn_att, pn_opp)
