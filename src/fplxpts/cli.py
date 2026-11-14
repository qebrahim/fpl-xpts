"""Command line interface:  fplxpts {project,squad,moves,backtest,export}

`backtest --season 2024-25` (repeatable, or `all`) replays a past season from the community archive (archive.py).
`backtest --prior-season 2025-26` (or `previous`) shrinks the walk-forward / fitted calibration factors towards that
past season's full-season factors (fitted with the current settings) instead of towards 1.0; off by default.

Bookmaker odds (odds.py) are used when the odds settings in the model config are on: live odds from The Odds API for
project/squad/moves/export (key from ODDS_API_KEY or .env; a missing key or failed request falls back to the model's
own numbers with one status line), and historical Football-Data.co.uk odds for backtest. --no-odds turns them off.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from . import backtest as bt
from .api import FPLClient
from .archive import CURRENT, SEASONS, load_archive_season, scoring_rules, shift_prior_seasons, start_year
from .config import SquadCfg, load_config, load_squad
from .constants import POS
from .data import load_season
from .export import build_export, eligible, write_export
from .model import Projector
from .odds import (
    LiveOdds,
    api_key,
    football_data_csv,
    live_odds,
    odds_by_round,
    parse_football_data,
    season_code,
)
from .optimize import pick_lineup, single_moves


def _load(args):
    cfg = load_config(args.config)
    season = load_season(FPLClient(args.cache, ttl=args.ttl))
    squad = load_squad(args.squad) if getattr(args, "squad", None) else SquadCfg()
    return cfg, season, squad


def odds_on(cfg, args) -> bool:
    """Whether the bookmaker-odds settings are on and not disabled with --no-odds."""
    return (cfg.model.odds_weight > 0 or cfg.model.odds_ratings_weight > 0) and not getattr(args, "no_odds", False)


def _live_odds(cfg, season, args) -> LiveOdds | None:
    """Live odds for the next gameweek when the feature is on (prints one status line), else None. Never raises."""
    if not odds_on(cfg, args):
        return None
    live = live_odds(season, season.current_gw + 1, args.cache, api_key())
    print(live.message())
    return live


def _projector(cfg, season, squad, args) -> Projector:
    live = _live_odds(cfg, season, args)
    args.live_odds = live
    return Projector(season, cfg, squad, odds=live.by_fixture if live else None)


def _row(proj, pid, lo, hi):
    e = proj.season.elements[pid]
    return f"{e['web_name']:<14}{proj.season.teams[e['team']]:<4} £{e['now_cost'] / 10:4.1f}m  {proj.pts(pid, lo, hi):5.1f}"


def cmd_project(args):
    cfg, season, squad = _load(args)
    pr = _projector(cfg, season, squad, args)
    proj = pr.project(args.first, args.last)
    lo, hi = proj.first_gw, proj.first_gw + args.weeks - 1
    print(f"Expected points GW{lo}-{hi} (data through GW{pr.cut}); top {args.top} by position")
    for pos, name in POS.items():
        pool = eligible(proj, pos)
        print(f"\n{name}")
        for p in sorted(pool, key=lambda p: -proj.pts(p, lo, hi))[: args.top]:
            print("  " + _row(proj, p, lo, hi))


def cmd_export(args):
    pens = args.pens or ("data/pens.toml" if Path("data/pens.toml").exists() else None)
    args.squad = pens
    cfg, season, squad = _load(args)
    pr = _projector(cfg, season, squad, args)
    proj = pr.project(args.first, args.last)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = build_export(proj, pr.cut, args.weeks, args.top, now)
    if args.live_odds is not None:                       # additive field; absent when the feature is off
        data["odds"] = args.live_odds.summary()
    write_export(data, args.out)
    n = sum(len(v) for v in data["positions"].values())
    print(f"Wrote {n} players, GW{data['gameweeks'][0]}-{data['gameweeks'][-1]} (data through GW{pr.cut}) to {args.out}")


def cmd_squad(args):
    cfg, season, squad = _load(args)
    pr = _projector(cfg, season, squad, args)
    proj = pr.project(args.first, args.last)
    ids = list(pr.ids.values())
    for swap in args.swap or []:
        out, _, into = swap.partition(":")
        ids = [pr.resolve(into) if p == pr.resolve(out) else p for p in ids]
    lo, hi = proj.first_gw, proj.first_gw + args.weeks - 1
    print(f"Squad, expected points GW{lo}-{hi}")
    for p in sorted(ids, key=lambda p: (season.elements[p]["element_type"], -proj.pts(p, lo, hi))):
        per = [round(proj.series.get(p, {}).get(g, 0.0), 1) for g in range(lo, hi + 1)]
        print("  " + _row(proj, p, lo, hi) + f"   {per}")
    name = lambda p: season.elements[p]["web_name"]
    for gw in range(lo, hi + 1):
        lu = pick_lineup(ids, proj, gw)
        print(f"\nGW{gw}  {lu.formation}  XI {lu.total:.1f}  (C {name(lu.captain)}, VC {name(lu.vice)})")
        print("   XI   : " + ", ".join(f"{name(p)} {proj.series[p][gw]:.1f}" for p in lu.xi))
        print("   Bench: " + ", ".join(f"{name(p)} {proj.series.get(p, {}).get(gw, 0.0):.1f}" for p in lu.bench))


def cmd_moves(args):
    cfg, season, squad = _load(args)
    pr = _projector(cfg, season, squad, args)
    proj = pr.project(args.first, args.last)
    lo = proj.first_gw
    windows = ((lo, lo + 4), (lo, proj.last_gw))
    moves = single_moves(list(pr.ids.values()), proj, windows, args.max_cost)
    print(f"Best single transfers (gain over GW{windows[0][0]}-{windows[0][1]} | GW{windows[1][0]}-{windows[1][1]} | cost)")
    name = lambda p: season.elements[p]["web_name"]
    for m in moves[: args.top]:
        print(f"  {name(m.out):<13}-> {name(m.into):<13} {m.gains[0]:+5.1f} | {m.gains[1]:+5.1f} | £{m.cost:+.1f}m")


def _historical_odds(cfg, season, args, ttl: int | None = None) -> dict | None:
    """{round: {(home, away): MatchOdds}} from the Football-Data.co.uk CSV (cached) when the feature is on."""
    if not odds_on(cfg, args):
        return None
    kind = "close" if args.closing_odds else "open"
    try:
        text = football_data_csv(args.cache, season_code(season.fixtures), ttl=ttl or max(args.ttl, 86400))
        rounds = odds_by_round(parse_football_data(text, season.team_ids, kind), season.fixtures)
    except Exception as e:  # noqa: BLE001 - report and run without odds
        print(f"Bookmaker odds unavailable ({type(e).__name__}: {e}); backtest runs with odds off")
        return None
    label = "closing averages (upper bound)" if kind == "close" else "pre-match averages"
    print(f"Bookmaker odds: Football-Data.co.uk {label} for {sum(len(v) for v in rounds.values())} fixtures; "
          f"at cutoff c only round c+1 is used (odds_weight {cfg.model.odds_weight}, side {cfg.model.odds_side}, "
          f"ratings weight {cfg.model.odds_ratings_weight})")
    return rounds


def _backtest_report(cfg, season, args, cuts, last, odds_rounds, cal_note: str, split_round: int = 6,
                     cal_label: str = "calibrated, in-sample", prior: dict | None = None):
    """Print the walk-forward backtest lines for one season (shared by the live season and archive seasons).
    `prior`: calibration factors the walk-forward, time-split and --fit factors are shrunk towards (None = 1.0)."""
    rows = bt.evaluate(season, cfg.without_calibration(), cuts, args.horizon, last, odds_rounds)
    print(f"Walk-forward backtest: cutoffs GW{cuts[0]}-{cuts[-1]}, next {args.horizon} rounds, {len(rows)} player-games")
    wf_note = "towards the prior season's factors" if prior else "towards 1.0"
    m0, m1, wf = bt.metrics(rows), bt.metrics(rows, cfg.calibration), bt.walk_forward_metrics(rows, prior=prior)
    print(f"  model (uncalibrated)          RMSE {m0['rmse']:.3f}  bias {m0['bias']:+.3f}  corr {m0['corr']:.3f}  top-12 picks {bt.top_k_actual(rows):.2f}")
    print(f"  {'model (' + cal_label + ')':<30}RMSE {m1['rmse']:.3f}  bias {m1['bias']:+.3f}  corr {m1['corr']:.3f}  top-12 picks {bt.top_k_actual(rows, cfg.calibration):.2f}"
          f"  ({cal_note})")
    print(f"  model (calibrated, walk-fwd)  RMSE {wf['rmse']:.3f}  bias {wf['bias']:+.3f}  corr {wf['corr']:.3f}  top-12 picks {wf['top12']:.2f}"
          f"  (out-of-sample: refit at each cutoff on rounds <= cutoff, shrunk {wf_note})")
    for kind in ("ppg", "form4"):
        print(f"  naive {kind:<23} RMSE {bt.baseline_rmse(season, kind, cuts, args.horizon, last):.3f}")
    ts = bt.time_split(rows, split_round, prior=prior)
    print(f"  time split (fit rounds<={split_round} n={ts['train_n']}, test rounds>{split_round} n={ts['test_n']}): "
          f"RMSE {ts['uncalibrated']['rmse']:.3f} -> {ts['calibrated']['rmse']:.3f}, "
          f"bias {ts['uncalibrated']['bias']:+.3f} -> {ts['calibrated']['bias']:+.3f}")
    if odds_rounds:
        r0 = bt.evaluate(season, cfg.without_calibration(), cuts, args.horizon, last)
        z0, w0 = bt.metrics(r0), bt.walk_forward_metrics(r0, prior=prior)
        nx = [i for i, r in enumerate(rows) if r.rnd == r.cut + 1]
        wf1, wf0 = bt.walk_forward_predicted(rows, prior=prior), bt.walk_forward_predicted(r0, prior=prior)
        n1 = bt.score([rows[i] for i in nx], wf1[nx])["rmse"], bt.score([r0[i] for i in nx], wf0[nx])["rmse"]
        print(f"  same model, odds off          RMSE {z0['rmse']:.3f}  walk-fwd {w0['rmse']:.3f}; next-round rows walk-fwd "
              f"RMSE {n1[0]:.3f} with odds vs {n1[1]:.3f} without")
    if args.fit:
        how = "shrunk towards the prior season's factors" if prior else "shrunk towards 1.0"
        print(f"\n# paste into src/fplxpts/default.toml (k = {bt.CAL_K:g}, {how})\n"
              + bt.calibration_toml(bt.fit_calibration(rows, prior=prior)))


def prior_season_name(value: str, target: str) -> str:
    """--prior-season value -> archive season name. "previous" = the season before `target` ("2026-27" for the live
    season). The prior must be an earlier season than the one tested (its factors use that season's outcomes)."""
    name = (f"{start_year(target) - 1}-{start_year(target) % 100:02d}" if value == "previous"
            else value.replace("/", "-"))
    if name not in SEASONS:
        raise SystemExit(f"no archive season {name!r} for --prior-season; available: {', '.join(SEASONS)} or 'previous'")
    if start_year(name) >= start_year(target):
        raise SystemExit(f"--prior-season {name} is not before the backtested season {target}")
    return name


def season_factors(base, args, name: str) -> dict:
    """Full-season calibration factors of archive season `name` with the current model settings (shrunk towards
    1.0 with k = CAL_K; the historical odds on unless --no-odds), as `backtest --season NAME --fit` prints them."""
    season = load_archive_season(args.cache, name)
    cfg = base.with_model(prior_seasons=shift_prior_seasons(base.model.prior_seasons, name)).without_calibration()
    odds_rounds = _historical_odds(cfg, season, args, ttl=10**10)
    last = season.current_gw
    cuts = [c for c in bt.played_rounds(season) if c < last]
    cal = bt.fit_calibration(bt.evaluate(season, cfg, cuts, args.horizon, last, odds_rounds))
    print(f"Calibration prior: {name} full-season factors, current settings, {len(cal)} cells (missing cells count as 1.0)")
    return cal


def cmd_backtest(args):
    if args.season:
        return _backtest_archive(args)
    cfg, season, _ = _load(args)
    prior = season_factors(cfg, args, prior_season_name(args.prior_season, CURRENT)) if args.prior_season else None
    last = season.current_gw
    cuts = list(range(1, last))
    odds_rounds = _historical_odds(cfg, season, args)
    _backtest_report(cfg, season, args, cuts, last, odds_rounds, "shipped factors, fitted on these rows", prior=prior)


def archive_seasons(names: list[str]) -> list[str]:
    """--season values -> archive season names ("all" = every available season, newest first)."""
    out: list[str] = []
    for n in names:
        for s in (reversed(SEASONS) if n == "all" else [n.replace("/", "-")]):
            if s not in SEASONS:
                raise SystemExit(f"unknown archive season {n!r}; available: {', '.join(SEASONS)} or 'all'")
            if s not in out:
                out.append(s)
    return out


def _backtest_archive(args):
    """Walk-forward backtest of past seasons from the cached community archive (each season on its own: its own
    teams, players, priors from the season before, scoring rules and Football-Data.co.uk odds file)."""
    base = load_config(args.config)
    for i, name in enumerate(archive_seasons(args.season)):
        season = load_archive_season(args.cache, name)
        cfg = base.with_model(prior_seasons=shift_prior_seasons(base.model.prior_seasons, name))
        rules = scoring_rules(name)
        print(("\n" if i else "") + f"Season {name} (archive: vaastav/Fantasy-Premier-League; prior seasons "
              f"{cfg.model.prior_seasons}; defensive-contribution points {'on' if rules['dc'] else 'off (not in the rules)'})")
        prior = season_factors(base, args, prior_season_name(args.prior_season, name)) if args.prior_season else None
        played = bt.played_rounds(season)
        last = season.current_gw
        cuts = [c for c in played if c < last]
        odds_rounds = _historical_odds(cfg, season, args, ttl=10**10)   # past seasons' files do not change
        _backtest_report(cfg, season, args, cuts, last, odds_rounds,
                         "shipped factors, fitted on 2026/27: out of sample here",
                         split_round=(cuts[0] + last) // 2, cal_label="shipped factors", prior=prior)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fplxpts", description="Expected-points model for Fantasy Premier League")
    ap.add_argument("--config", help="model config TOML (default: packaged default.toml)")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--ttl", type=int, default=3600, help="cache lifetime in seconds")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def window(p):
        p.add_argument("--first", type=int, help="first gameweek (default: next)")
        p.add_argument("--last", type=int, help="last gameweek to project (default: first+7)")
        p.add_argument("--weeks", type=int, default=5, help="window length for totals")

    def no_odds(p):
        p.add_argument("--no-odds", action="store_true", help="ignore bookmaker odds (model's own numbers only)")

    p = sub.add_parser("project", help="top players by position")
    window(p)
    no_odds(p)
    p.add_argument("--squad", help="squad TOML (for pen counts and overrides)")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_project)

    p = sub.add_parser("export", help="write top players per position as JSON for the web front end")
    window(p)
    no_odds(p)
    p.add_argument("--out", required=True)
    p.add_argument("--pens", help="TOML with [[pen_goals]] tables (default: data/pens.toml if present)")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("squad", help="your squad, lineups and captains")
    window(p)
    no_odds(p)
    p.add_argument("--squad", required=True)
    p.add_argument("--swap", action="append", help="OUT:IN, e.g. Schade:Rudoni (repeatable)")
    p.set_defaults(fn=cmd_squad)

    p = sub.add_parser("moves", help="best single transfers")
    window(p)
    no_odds(p)
    p.add_argument("--squad", required=True)
    p.add_argument("--max-cost", type=float, default=0.5, help="max extra spend in GBP m")
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(fn=cmd_moves)

    p = sub.add_parser("backtest", help="walk-forward backtest and calibration check")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--fit", action="store_true", help="print freshly fitted calibration factors")
    p.add_argument("--no-odds", action="store_true", help="backtest without bookmaker odds")
    p.add_argument("--closing-odds", action="store_true", help="use closing odds (an upper bound, not realistic)")
    p.add_argument("--season", action="append",
                   help=f"past season from the cached archive instead of the live one ({', '.join(SEASONS)}, or 'all'); "
                        "repeatable")
    p.add_argument("--prior-season",
                   help="shrink the walk-forward and --fit calibration towards this past season's full-season factors "
                        "(fitted with the current settings) instead of 1.0: a season name or 'previous'; off by default")
    p.set_defaults(fn=cmd_backtest)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
