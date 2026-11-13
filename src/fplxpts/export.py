"""JSON export of the top players per position, consumed by the static web front end."""
from __future__ import annotations

import json
from pathlib import Path

from .constants import POS


def eligible(proj, pos: int) -> list[int]:
    """Player ids in position `pos` that qualify for the ranked pool."""
    els = proj.season.elements
    return [p for p in proj.series if els[p]["element_type"] == pos and els[p]["minutes"] >= 270
            and proj.players[p]["mf"] >= 0.7 and proj.available(p)]


def fixtures_by_gw(season, team: int, gws: list[int]) -> dict[int, list[dict]]:
    """Unfinished fixtures of `team` per gameweek (same condition as Projector.project)."""
    out: dict[int, list[dict]] = {g: [] for g in gws}
    for f in season.fixtures:
        ev = f.get("event")
        if not ev or ev not in out or f.get("finished"):
            continue
        if f["team_h"] == team:
            out[ev].append({"opp": season.teams[f["team_a"]], "home": True})
        elif f["team_a"] == team:
            out[ev].append({"opp": season.teams[f["team_h"]], "home": False})
    return out


def player_entry(proj, pid: int, gws: list[int]) -> dict:
    season = proj.season
    e = season.elements[pid]
    fx = fixtures_by_gw(season, e["team"], gws)
    lo, hi = gws[0], gws[-1]
    return {
        "id": pid,
        "name": e["web_name"],
        "team": season.teams[e["team"]],
        "price": e["now_cost"] / 10,
        "total": round(proj.pts(pid, lo, hi), 2),
        "by_gw": [{"gw": g, "xpts": round(proj.series[pid].get(g, 0.0), 2), "fixtures": fx[g]} for g in gws],
    }


def build_export(proj, cut: int, weeks: int = 5, top: int = 10, generated_at: str = "") -> dict:
    lo = proj.first_gw
    gws = list(range(lo, lo + weeks))
    hi = gws[-1]
    positions = {}
    for pos, name in POS.items():
        ranked = sorted(eligible(proj, pos), key=lambda p: -proj.pts(p, lo, hi))[:top]
        positions[name] = [player_entry(proj, p, gws) for p in ranked]
    return {"schema": 1, "generated_at": generated_at, "data_through_gw": cut,
            "gameweeks": gws, "positions": positions}


def write_export(data: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
