"""Projector: ties the pieces together to produce expected points per player per future gameweek."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config, SquadCfg
from .data import Season, norm
from .pens import build_pen_model, strip_penalties
from .players import build_players
from .points import components, total
from .teams import team_state


@dataclass
class Projection:
    season: Season
    players: dict      # player id -> rates (after overrides)
    series: dict       # player id -> {gameweek: expected points}
    first_gw: int
    last_gw: int

    def pts(self, pid: int, lo: int | None = None, hi: int | None = None) -> float:
        return sum(v for gw, v in self.series.get(pid, {}).items() if (lo or 0) <= gw <= (hi or 99))

    def available(self, pid: int) -> bool:
        e = self.season.elements[pid]
        return pid in self.series and e["chance_of_playing_next_round"] in (None, 75, 100)


class Projector:
    def __init__(self, season: Season, cfg: Config, squad: SquadCfg | None = None, cut: int | None = None):
        self.season, self.cfg = season, cfg
        self.squad = squad or SquadCfg()
        self.cut = cut if cut is not None else season.current_gw

        self.pens = build_pen_model(season, self.squad.pen_goals)
        hist = strip_penalties(season, self.pens, cfg) if self.pens.taken else None
        self.players = build_players(season, self.cut, cfg, hist)
        for pid in self.pens.primary.values():           # normal forward-looking penalty share
            if pid in self.players:
                self.players[pid]["xg90"] += cfg.model.pen_share_xg
        self.state = team_state(season, self.cut, cfg)

        self.ids = {name: season.find(name, team, pos) for name, team, pos in self.squad.players}
        for name, ov in self.squad.overrides.items():
            self.players[self.ids[name]].update(ov)
        self.fit = {self.ids[n] for n in self.squad.assume_fit}

    def resolve(self, ref: str) -> int:
        """'Rudoni' or 'Rudoni@COV' -> player id (squad names first, then anyone)."""
        if ref in self.ids:
            return self.ids[ref]
        name, _, team = ref.partition("@")
        hits = [e["id"] for e in self.season.elements.values()
                if (not team or self.season.teams[e["team"]] == team)
                and (norm(name) in norm(e["web_name"]) or norm(name) in norm(e["second_name"]))]
        if len(hits) != 1:
            raise ValueError(f"{ref!r} matched {len(hits)} players; try NAME@TEAM")
        return hits[0]

    def project(self, first_gw: int | None = None, last_gw: int | None = None) -> Projection:
        first = first_gw or self.cut + 1
        last = last_gw or first + 7
        sched: dict = {}
        for f in self.season.fixtures:
            ev = f.get("event")
            if ev and first <= ev <= last and not f.get("finished"):
                sched.setdefault(f["team_h"], []).append((ev, "h", f["team_a"]))
                sched.setdefault(f["team_a"], []).append((ev, "a", f["team_h"]))
        series = {}
        for pid, p in self.players.items():
            e = self.season.elements[pid]
            if e["status"] in ("u", "s", "n") or e["chance_of_playing_next_round"] == 0:
                continue
            chance = 1.0 if pid in self.fit else (e["chance_of_playing_next_round"] if e["chance_of_playing_next_round"] is not None else 100) / 100
            d = {}
            for ev, venue, opp in sorted(sched.get(p["team"], [])):
                x = total(components(p, venue, opp, self.state), p["pos"], self.cfg.calibration)
                d[ev] = x * (chance if ev == first else (1.0 if chance >= 0.5 else 0.5))   # flag applies to the next GW only
            series[pid] = d
        return Projection(self.season, self.players, series, first, last)
