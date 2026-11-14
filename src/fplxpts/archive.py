"""Past seasons from the community FPL archive, turned into the same `Season` structure as the live API loader.

Source: **vaastav/Fantasy-Premier-League** (https://github.com/vaastav/Fantasy-Premier-League), MIT licence,
"FPL Historical Dataset" by Vaastav Anand. The data itself is the property of the Premier League / Fantasy Premier
League (and Understat for some files); the repository asks users to cite it and link back to it, which README.md
does. Files used per season (raw.githubusercontent.com, ``data/<season>/...``): ``gws/merged_gw.csv`` (one row per
player per match), ``fixtures.csv``, ``teams.csv`` and ``players_raw.csv`` (end-of-season player list, for names and
the cross-season player ``code``). Each file is downloaded once into the cache directory
(``vaastav_<season>_<name>.csv``) and re-read from disk; past seasons do not change, so there is no expiry.

Differences from the live API that this module handles (see also docs/BACKTEST.md, "Past seasons"):

- element ids and team ids are per season; players are linked across seasons by ``code``;
- each match row gets a ``team`` field (from the fixture and ``was_home``): the club he played for in that match,
  so mid-season transfers between clubs are seen correctly (the live rows have no such field);
- double gameweeks give two rows in one round (one per fixture), blank gameweeks none; postponed matches carry the
  round they were played in (``fixtures.csv`` ``event``), as in the live API;
- ``history_past`` (previous-season priors) is rebuilt from the archive's earlier seasons, aggregated by ``code``,
  with the FPL season names ("2024/25"); seasons without expected goals (before 2022/23) are not available;
- defensive-contribution points exist only from 2025/26 (`scoring_rules`): earlier seasons get
  ``defensive_contribution = 0`` in every row, so both the projected and the actual dc component are zero;
- 2022/23 has no expected-goals data before GW16 (FPL started publishing xG then; the archive has zeros): rounds
  before the first round with xG are dropped (`xg_rounds_only`), so that season starts at GW16 and its prior for
  2023/24 is built from GW16-38 only (minutes and xG over the same matches);
- 2024/25 "assistant manager" rows (position ``AM``) are dropped; there are no availability flags (every player
  has ``status = "a"``), the same limitation as the current-season backtest.
"""
from __future__ import annotations

import csv
import io
import time
import urllib.request
from pathlib import Path

from .data import Season

ARCHIVE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/{path}"
FILES = {"gws": "gws/merged_gw.csv", "fixtures": "fixtures.csv", "teams": "teams.csv", "players": "players_raw.csv"}
SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")   # archive seasons with expected goals (xG from 2022/23)
CURRENT = "2026/27"                                     # the season the shipped config (prior_seasons) is written for
POS_ID = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
UA = {"User-Agent": "fplxpts research project"}

INT_FIELDS = ("minutes", "starts", "goals_scored", "assists", "clean_sheets", "goals_conceded", "own_goals",
              "penalties_saved", "penalties_missed", "yellow_cards", "red_cards", "saves", "bonus", "bps",
              "total_points", "value", "defensive_contribution")


# ---------------------------------------------------------------------------------------------------------------
# season names and rules


def fpl_name(season: str) -> str:
    """Archive folder name "2024-25" -> FPL season name "2024/25" (as in history_past)."""
    return season.replace("-", "/")


def start_year(season: str) -> int:
    """First calendar year of a season in either spelling ("2024-25", "2024/25") -> 2024."""
    return int(season[:4])


def shift_name(season: str, years: int) -> str:
    """FPL season name moved by `years`: shift_name("2025/26", -2) -> "2023/24"."""
    y = start_year(season) + years
    return f"{y}/{(y + 1) % 100:02d}"


def shift_prior_seasons(prior: dict, target: str, reference: str = CURRENT) -> dict:
    """The config's prior_seasons {season name: weight}, written for `reference`, re-expressed for `target`.

    The weights stay attached to the same *relative* seasons: for the shipped {"2025/26": 1, "2024/25": 0.5}
    (last season 1, the one before 0.5) and target "2024-25" this gives {"2023/24": 1, "2022/23": 0.5}.
    """
    d = start_year(target) - start_year(reference)
    return {shift_name(k, d): w for k, w in prior.items()}


def scoring_rules(season: str) -> dict:
    """Scoring differences between seasons that matter for the model's components.

    dc: defensive-contribution points (+2 for DEF CBIT >= 10, MID/FWD CBIRT >= 12) were introduced in 2025/26.
    gk_goal: points for a goalkeeper goal (6 before 2025/26, 10 from then; GKs have no projected xG, so this only
    affects the actual goal component of a handful of rows).
    """
    y = start_year(season)
    return {"dc": y >= 2025, "gk_goal": 10 if y >= 2025 else 6}


# ---------------------------------------------------------------------------------------------------------------
# download + cache


def archive_csv(cache_dir: str | Path, season: str, name: str, fetch=None) -> str:
    """Text of one archive file (`name` in FILES) for `season`, downloaded once into `cache_dir` and then always
    read from disk (past seasons are static; delete the file to re-download)."""
    path = Path(cache_dir) / f"vaastav_{season}_{name}.csv"
    if path.exists():
        return path.read_text(encoding="utf-8-sig")
    raw = (fetch or _get)(ARCHIVE_URL.format(season=season, path=FILES[name]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw.decode("utf-8-sig")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        time.sleep(0.5)   # be polite between the handful of files
        return r.read()


def read_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


# ---------------------------------------------------------------------------------------------------------------
# pure conversion


def _bool(x) -> bool:
    return str(x).strip().lower() in ("true", "1")


def _int(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def parse_fixtures(rows: list[dict]) -> list[dict]:
    """fixtures.csv -> live-API-like fixture dicts (ids and scores as ints, finished as bool, event None if unset)."""
    out = []
    for f in rows:
        ev = _int(f.get("event")) or None
        out.append({"id": int(f["id"]), "event": ev, "team_h": int(f["team_h"]), "team_a": int(f["team_a"]),
                    "team_h_score": _int(f["team_h_score"]) if f.get("team_h_score") not in ("", None) else None,
                    "team_a_score": _int(f["team_a_score"]) if f.get("team_a_score") not in ("", None) else None,
                    "finished": _bool(f.get("finished")), "finished_provisional": _bool(f.get("finished")),
                    "kickoff_time": f.get("kickoff_time") or None})
    return out


def match_row(r: dict, fx: dict, rules: dict) -> dict:
    """One merged_gw row -> a live-API-like history row plus `team` (the club he played for in this match, from the
    fixture). The round is the fixture's event (the round the match was actually played in)."""
    f = fx[int(r["fixture"])]
    home = _bool(r["was_home"])
    row = {k: _int(r.get(k)) for k in INT_FIELDS}
    row.update({
        "element": int(r["element"]), "fixture": f["id"], "round": f["event"], "was_home": home,
        "team": f["team_h"] if home else f["team_a"], "opponent_team": f["team_a"] if home else f["team_h"],
        "kickoff_time": f["kickoff_time"],
        "expected_goals": float(r["expected_goals"] or 0), "expected_assists": float(r["expected_assists"] or 0),
        "expected_goals_conceded": float(r["expected_goals_conceded"] or 0),
    })
    if not rules["dc"]:
        row["defensive_contribution"] = 0
    return row


def history_rows(gw_rows: list[dict], fixtures: list[dict], rules: dict) -> tuple[dict, dict]:
    """({element: chronological match rows}, {element: position id}) from merged_gw rows. Rows of unknown
    positions (2024/25 assistant managers) and exact duplicates of a (player, fixture) are dropped."""
    fx = {f["id"]: f for f in fixtures}
    hist: dict = {}
    pos: dict = {}
    seen: set = set()
    for r in gw_rows:
        if r["position"] not in POS_ID:
            continue
        key = (int(r["element"]), int(r["fixture"]))
        if key in seen:
            continue
        seen.add(key)
        row = match_row(r, fx, rules)
        hist.setdefault(row["element"], []).append(row)
        pos[row["element"]] = POS_ID[r["position"]]
    for rows in hist.values():
        rows.sort(key=lambda x: (x["round"], x["kickoff_time"] or "", x["fixture"]))
    return hist, pos


def xg_rounds_only(hist: dict) -> dict:
    """Match rows from the first round that has any expected-goals data on (2022/23: xG starts at GW16; earlier
    rounds carry zeros, which would read as 'no chances created' and as a zero league xG)."""
    rounds = {r["round"] for rows in hist.values() for r in rows if r["expected_goals"] or r["expected_goals_conceded"]}
    if not rounds:
        return {}
    first = min(rounds)
    out = {p: [r for r in rows if r["round"] >= first] for p, rows in hist.items()}
    return {p: rows for p, rows in out.items() if rows}


def season_totals(hist: dict, code_of: dict, season_name: str) -> dict:
    """{code: history_past-style row} with minutes, expected goals and assists summed over one season's rows."""
    out: dict = {}
    for pid, rows in hist.items():
        c = code_of.get(pid)
        if c is None:
            continue
        t = out.setdefault(c, {"season_name": season_name, "element_code": c, "minutes": 0,
                               "expected_goals": 0.0, "expected_assists": 0.0})
        t["minutes"] += sum(r["minutes"] for r in rows)
        t["expected_goals"] += sum(r["expected_goals"] for r in rows)
        t["expected_assists"] += sum(r["expected_assists"] for r in rows)
    for t in out.values():   # strings, like the live API
        t["expected_goals"], t["expected_assists"] = f"{t['expected_goals']:.2f}", f"{t['expected_assists']:.2f}"
    return out


def team_xg(hist: dict, pos: dict, fixtures: list[dict]) -> list[dict]:
    """Finished fixtures with team xG from goalkeeper expected goals conceded, as in data.load_season."""
    xga: dict = {}
    for pid, rows in hist.items():
        if pos.get(pid) != 1:
            continue
        for r in rows:
            if r["minutes"] > 0:
                k = (r["fixture"], r["team"])
                xga[k] = xga.get(k, 0.0) + r["expected_goals_conceded"]
    fin = []
    for f in sorted(fixtures, key=lambda f: (f.get("event") or 99, f["id"])):
        if f["finished"] and f["event"] and (f["id"], f["team_h"]) in xga and (f["id"], f["team_a"]) in xga:
            fin.append({"ev": f["event"], "h": f["team_h"], "a": f["team_a"],
                        "xg_h": xga[(f["id"], f["team_a"])], "xg_a": xga[(f["id"], f["team_h"])]})
    return fin


def elements_from(players: list[dict], hist: dict, pos: dict) -> dict:
    """{element: bootstrap-like element} for players with match rows. Position comes from the match rows; `team`
    is the club of his last match row (the per-match `team` on each row is what the model uses); no availability
    flags exist in the archive, so every player is available."""
    raw = {int(p["id"]): p for p in players}
    out = {}
    for pid, rows in hist.items():
        p = raw.get(pid, {})
        name = p.get("web_name") or f"player{pid}"
        out[pid] = {"id": pid, "code": _int(p.get("code")) or None, "web_name": name,
                    "first_name": p.get("first_name", ""), "second_name": p.get("second_name", name),
                    "element_type": pos[pid], "team": rows[-1]["team"], "now_cost": rows[-1]["value"],
                    "minutes": sum(r["minutes"] for r in rows), "status": "a", "chance_of_playing_next_round": None,
                    "penalties_missed": sum(r["penalties_missed"] for r in rows), "penalties_order": None}
    return out


def build_season(season: str, gw_rows: list[dict], fixture_rows: list[dict], team_rows: list[dict],
                 player_rows: list[dict], previous: dict | None = None, min_minutes: int = 90) -> Season:
    """A `Season` for an archive season from its raw CSV rows.

    previous: {archive season: (gw_rows, fixture_rows, player_rows)} of earlier seasons for the history_past priors
    (only those listed are used). Players with fewer than `min_minutes` in the season are left out of `hist`, as in
    the live loader (they can never be projected)."""
    rules = scoring_rules(season)
    fixtures = parse_fixtures(fixture_rows)
    hist, pos = history_rows(gw_rows, fixtures, rules)
    hist = xg_rounds_only(hist)
    elements = elements_from(player_rows, hist, pos)
    teams = {int(t["id"]): t["short_name"] for t in team_rows}
    fin = team_xg(hist, pos, fixtures)

    past: dict = {}
    for prev, (g, fr, pr) in sorted((previous or {}).items()):
        ph = xg_rounds_only(history_rows(g, parse_fixtures(fr), scoring_rules(prev))[0])
        tot = season_totals(ph, {int(p["id"]): _int(p["code"]) for p in pr}, fpl_name(prev))
        for pid, e in elements.items():
            if e["code"] in tot:
                past.setdefault(pid, []).append(tot[e["code"]])

    cand = [p for p, e in elements.items() if e["minutes"] >= min_minutes]
    current_gw = max((f["event"] for f in fixtures if f["finished"] and f["event"]), default=0)
    return Season(elements, teams, fixtures, {p: hist[p] for p in cand}, {p: past.get(p, []) for p in cand},
                  fin, current_gw)


def load_archive_season(cache_dir: str | Path, season: str, n_prior: int = 2, fetch=None) -> Season:
    """Season `season` ("2024-25") from the cached archive, with up to `n_prior` earlier archive seasons
    (those in SEASONS) feeding the history_past priors."""
    if season not in SEASONS:
        raise ValueError(f"archive season must be one of {SEASONS}, got {season!r}")
    get = lambda s, n: read_csv(archive_csv(cache_dir, s, n, fetch))
    i = SEASONS.index(season)
    previous = {s: (get(s, "gws"), get(s, "fixtures"), get(s, "players")) for s in SEASONS[max(0, i - n_prior):i]}
    return build_season(season, get(season, "gws"), get(season, "fixtures"), get(season, "teams"),
                        get(season, "players"), previous)
