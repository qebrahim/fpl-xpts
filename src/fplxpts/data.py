"""Load a season's data from the FPL API into plain dicts.

Team xG per fixture is derived from goalkeeper expected-goals-conceded (the API has no team xG).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .api import FPLClient


def norm(x: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", x.lower()) if not unicodedata.combining(c))


@dataclass
class Season:
    elements: dict      # player id -> bootstrap element
    teams: dict         # team id -> short name
    fixtures: list      # raw fixtures
    hist: dict          # player id -> finished match rows, chronological
    past: dict          # player id -> history_past rows (previous seasons)
    fin: list           # finished fixtures with team xG: {ev, h, a, xg_h, xg_a}
    current_gw: int     # last fully finished gameweek

    @property
    def team_ids(self) -> dict:
        return {v: k for k, v in self.teams.items()}

    def find(self, name: str, team: str, pos: int | None = None) -> int:
        """Resolve 'Rudoni', 'COV' (and optionally a position id) to a player id; must be unique."""
        tid = self.team_ids[team]
        hits = [e["id"] for e in self.elements.values()
                if e["team"] == tid and (pos is None or e["element_type"] == pos)
                and (norm(name) in norm(e["web_name"]) or norm(name) in norm(e["second_name"]))]
        if len(hits) != 1:
            raise ValueError(f"{name!r} ({team}) matched {len(hits)} players: {[self.elements[h]['web_name'] for h in hits]}")
        return hits[0]


def load_season(client: FPLClient, min_minutes: int = 90) -> Season:
    boot, fixtures = client.bootstrap(), client.fixtures()
    elements = {e["id"]: e for e in boot["elements"]}
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    fxd = {f["id"]: f for f in fixtures}
    done = lambda fid: bool((fxd.get(fid) or {}).get("finished") or (fxd.get(fid) or {}).get("finished_provisional"))
    current_gw = max((e["id"] for e in boot["events"] if e["finished"]), default=0)

    gks = [e["id"] for e in elements.values() if e["element_type"] == 1 and e["minutes"] > 0]
    cand = [e["id"] for e in elements.values() if e["minutes"] >= min_minutes]
    summ = client.element_summaries(sorted(set(gks) | set(cand)))

    hist = {p: [r for r in summ[p]["history"] if done(r["fixture"])] for p in cand}
    past = {p: summ[p]["history_past"] for p in cand}

    xga: dict = {}
    for p in gks:
        t = elements[p]["team"]
        for r in summ[p]["history"]:
            if done(r["fixture"]) and r["minutes"] > 0:
                xga[(r["fixture"], t)] = xga.get((r["fixture"], t), 0.0) + float(r["expected_goals_conceded"])
    fin = []
    for f in sorted(fixtures, key=lambda f: (f.get("event") or 99, f["id"])):
        if f.get("finished") and f["event"] and (f["id"], f["team_h"]) in xga and (f["id"], f["team_a"]) in xga:
            fin.append({"ev": f["event"], "h": f["team_h"], "a": f["team_a"],
                        "xg_h": xga[(f["id"], f["team_a"])], "xg_a": xga[(f["id"], f["team_h"])]})
    return Season(elements, teams, fixtures, hist, past, fin, current_gw)
