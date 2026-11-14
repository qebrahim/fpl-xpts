"""Configuration: model hyper-parameters, calibration factors and the user's squad file."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .constants import POS_ID

_DEFAULT = Path(__file__).with_name("default.toml")


@dataclass(frozen=True)
class ModelCfg:
    """Model hyper-parameters. The shipped values live in default.toml; these dataclass defaults are the older or
    switched-off values (e.g. the half-lives 3/4 and prior 450/0.15 used before 2026-11, features off)."""
    team_halflife: float = 3.0
    team_shrink_k: float = 3.0
    team_sos_iters: int = 0   # strength-of-schedule passes for team ratings; 0 = off
    form_halflife: float | None = 4.0
    prior_min: float = 450.0
    prior_apps: float = 3.0
    prior_lambda: float = 0.15
    prior_cap_minutes: float = 2500.0
    prior_min_season_minutes: float = 450.0
    min_live_minutes: float = 90.0
    pen_xg: float = 0.76
    pen_share_xg: float = 0.10
    dc_opp_k: float = 0.0   # pseudo expected-hits shrinking the opponent DC-allowed factor; 0 = off
    opp_xg_gamma: float = 1.0  # exponent on the opponent-xG matchup multiplier for clean sheets; <1 damps it
    absence_starts_before: int = 0  # starts needed before a 0-minute run to treat it as an injury absence; 0 = off
    absence_starts_after: int = 1   # starts needed on return before that run is dropped from the minutes window
    odds_weight: float = 0.0          # blend weight of bookmaker-implied team goals in fixtures with odds; 0 = off, 1 = odds only
    odds_side: str = "both"           # which side the odds anchor: "both", "attack" (goals/assists) or "defence" (cs/gc/saves)
    odds_ratings_weight: float = 0.0  # each next-round fixture's odds count as this many extra games in team ratings; 0 = off
    prior_seasons: dict = field(default_factory=lambda: {"2025/26": 1.0, "2024/25": 0.5})


@dataclass(frozen=True)
class Config:
    model: ModelCfg
    calibration: dict  # {(pos_id, component): factor}

    def with_model(self, **kw) -> Config:
        return replace(self, model=replace(self.model, **kw))

    def without_calibration(self) -> Config:
        return replace(self, calibration={})


def load_config(path: str | Path | None = None) -> Config:
    with open(path or _DEFAULT, "rb") as fh:
        raw = tomllib.load(fh)
    m = dict(raw.get("model", {}))
    if m.get("form_halflife") == 0:
        m["form_halflife"] = None
    cal = {}
    for pos, comps in raw.get("calibration", {}).items():
        for comp, v in comps.items():
            cal[(POS_ID[pos], comp)] = float(v)
    return Config(model=ModelCfg(**m), calibration=cal)


@dataclass
class SquadCfg:
    """The user's 15 players plus per-player assumptions.

    players:   [(name, team, pos)]     name is matched against web_name / second_name
    overrides: {name: {mf, app, p60}}  e.g. returning from injury and assumed back to full minutes
    assume_fit:[name]                  ignore FPL's chance-of-playing flag for these players
    pen_goals: [(name, team, n)]       penalty GOALS scored this season (FPL does not expose them)
    """
    players: list = field(default_factory=list)
    overrides: dict = field(default_factory=dict)
    assume_fit: list = field(default_factory=list)
    pen_goals: list = field(default_factory=list)


def load_squad(path: str | Path) -> SquadCfg:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return SquadCfg(
        players=[(p["name"], p["team"], POS_ID[p["pos"]]) for p in raw.get("players", [])],
        overrides=raw.get("overrides", {}),
        assume_fit=raw.get("assume_fit", []),
        pen_goals=[(p["name"], p["team"], int(p["n"])) for p in raw.get("pen_goals", [])],
    )
