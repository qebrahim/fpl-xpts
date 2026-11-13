"""Command line interface:  fplxpts {project,squad,moves,backtest,export}"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from . import backtest as bt
from .api import FPLClient
from .config import SquadCfg, load_config, load_squad
from .constants import POS
from .data import load_season
from .export import build_export, eligible, write_export
from .model import Projector
from .optimize import pick_lineup, single_moves


def _load(args):
    cfg = load_config(args.config)
    season = load_season(FPLClient(args.cache, ttl=args.ttl))
    squad = load_squad(args.squad) if getattr(args, "squad", None) else SquadCfg()
    return cfg, season, squad


def _row(proj, pid, lo, hi):
    e = proj.season.elements[pid]
    return f"{e['web_name']:<14}{proj.season.teams[e['team']]:<4} £{e['now_cost'] / 10:4.1f}m  {proj.pts(pid, lo, hi):5.1f}"


def cmd_project(args):
    cfg, season, squad = _load(args)
    pr = Projector(season, cfg, squad)
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
    pr = Projector(season, cfg, squad)
    proj = pr.project(args.first, args.last)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = build_export(proj, pr.cut, args.weeks, args.top, now)
    write_export(data, args.out)
    n = sum(len(v) for v in data["positions"].values())
    print(f"Wrote {n} players, GW{data['gameweeks'][0]}-{data['gameweeks'][-1]} (data through GW{pr.cut}) to {args.out}")


def cmd_squad(args):
    cfg, season, squad = _load(args)
    pr = Projector(season, cfg, squad)
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
    pr = Projector(season, cfg, squad)
    proj = pr.project(args.first, args.last)
    lo = proj.first_gw
    windows = ((lo, lo + 4), (lo, proj.last_gw))
    moves = single_moves(list(pr.ids.values()), proj, windows, args.max_cost)
    print(f"Best single transfers (gain over GW{windows[0][0]}-{windows[0][1]} | GW{windows[1][0]}-{windows[1][1]} | cost)")
    name = lambda p: season.elements[p]["web_name"]
    for m in moves[: args.top]:
        print(f"  {name(m.out):<13}-> {name(m.into):<13} {m.gains[0]:+5.1f} | {m.gains[1]:+5.1f} | £{m.cost:+.1f}m")


def cmd_backtest(args):
    cfg, season, _ = _load(args)
    last = season.current_gw
    cuts = list(range(1, last))
    rows = bt.evaluate(season, cfg.without_calibration(), cuts, args.horizon, last)
    print(f"Walk-forward backtest: cutoffs GW{cuts[0]}-{cuts[-1]}, next {args.horizon} rounds, {len(rows)} player-games")
    m0, m1 = bt.metrics(rows), bt.metrics(rows, cfg.calibration)
    print(f"  model (uncalibrated)  RMSE {m0['rmse']:.3f}  bias {m0['bias']:+.3f}  corr {m0['corr']:.3f}  top-12 picks {bt.top_k_actual(rows):.2f}")
    print(f"  model (calibrated)    RMSE {m1['rmse']:.3f}  bias {m1['bias']:+.3f}  corr {m1['corr']:.3f}  top-12 picks {bt.top_k_actual(rows, cfg.calibration):.2f}  (in-sample)")
    for kind in ("ppg", "form4"):
        print(f"  naive {kind:<14} RMSE {bt.baseline_rmse(season, kind, cuts, args.horizon, last):.3f}")
    ts = bt.time_split(rows)
    print(f"  time split (fit rounds<=6 n={ts['train_n']}, test rounds>6 n={ts['test_n']}): "
          f"RMSE {ts['uncalibrated']['rmse']:.3f} -> {ts['calibrated']['rmse']:.3f}")
    if args.fit:
        print("\n# paste into src/fplxpts/default.toml\n" + bt.calibration_toml(bt.fit_calibration(rows)))


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

    p = sub.add_parser("project", help="top players by position")
    window(p)
    p.add_argument("--squad", help="squad TOML (for pen counts and overrides)")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_project)

    p = sub.add_parser("export", help="write top players per position as JSON for the web front end")
    window(p)
    p.add_argument("--out", required=True)
    p.add_argument("--pens", help="TOML with [[pen_goals]] tables (default: data/pens.toml if present)")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("squad", help="your squad, lineups and captains")
    window(p)
    p.add_argument("--squad", required=True)
    p.add_argument("--swap", action="append", help="OUT:IN, e.g. Schade:Rudoni (repeatable)")
    p.set_defaults(fn=cmd_squad)

    p = sub.add_parser("moves", help="best single transfers")
    window(p)
    p.add_argument("--squad", required=True)
    p.add_argument("--max-cost", type=float, default=0.5, help="max extra spend in GBP m")
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(fn=cmd_moves)

    p = sub.add_parser("backtest", help="walk-forward backtest and calibration check")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--fit", action="store_true", help="print freshly fitted calibration factors")
    p.set_defaults(fn=cmd_backtest)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
