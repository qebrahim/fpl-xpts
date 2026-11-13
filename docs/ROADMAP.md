# Roadmap: planned modifications

Ordered roughly by priority. Each item says why it matters. "Parity" means: after the change,
`fplxpts squad/moves/backtest` must reproduce the golden numbers below unless the change is meant to move them.

**Golden numbers (data through GW10, shipped config):** GW11-15 expected points: Rudoni 22.9, Konsa 24.4,
N.Jackson 26.9, Isak 23.2, Haaland 25.5, Van Hecke 23.3. Backtest: 9,267 player-games, RMSE 2.964
(calibrated 2.945), time split 2.835 -> 2.826. (Updated when bonus became event-driven; before that:
Rudoni 21.8, Konsa 24.7, N.Jackson 28.8, Isak 25.0, Haaland 26.5, Van Hecke 23.2, RMSE 2.962 / 2.943, 2.840 -> 2.827.)

## P0: make it a solid, testable project (first session)

1. **Frozen API snapshot + golden test.** Save a GW10 snapshot of bootstrap-static, fixtures and
   element-summary under `tests/fixtures/` (trimmed) and add an integration test asserting the golden numbers.
   Lets CI run offline and stops refactors silently changing the model.
2. **Typed data model.** Replace the dict-based player rates and match rows with dataclasses / TypedDicts;
   add type hints and a type checker (pyright or mypy) to CI.
3. **CI.** Verify `.github/workflows/ci.yml` passes on 3.11-3.13; add ruff format / pre-commit.
4. **Error handling.** Friendly messages for ambiguous or unknown player names, API outages (fall back to
   cache), missing config keys; progress output for the first full fetch.
5. **Config validation.** Validate squad / model TOML (unknown keys, bad positions) with clear errors.
6. **Pull the Streamlit stub into the package** (`fplxpts.app`) and add a `fplxpts app` command.

## P1: model improvements (from the backtest and review)

1. **Out-of-sample reporting.** Make the backtest refit calibration at each cutoff (walk-forward) and report
   only out-of-sample error, instead of full-sample factors.
2. **Team news in team ratings.** Ratings use season-long xG that still includes players who are now
   injured/suspended (key attackers or defenders). Adjust attack/defence for who is actually available.
3. **Better minutes model.** Currently the mean of the last 5 games. Use starts vs sub appearances,
   rotation after cup/European weeks, and fixture congestion (Dec 26 - Jan 1 run). Backtest shows minutes
   over-projected by 6-14%.
4. **Suspension risk.** Yellow-card accumulation (5 by GW19 -> ban) is only a -1 point cost today.
5. **Haul probability for captaincy.** Replace expected points with a distribution per player
   (Poisson/negative-binomial per component) and report P(>=10) and P(<=2) alongside the mean.
6. **Penalty ingestion.** Penalty goals are a manual list in the squad TOML (FPL exposes only misses).
   Automate from a documented source (respect its terms) or a `data/pens.csv`. Scale the forward share by team
   attacking strength rather than a flat 0.10 xG per game; handle injured/suspended primary takers.
7. **Priors.** Strip penalty xG from last-season rates; handle promoted teams (no top-flight history) and
   club moves; consider a team-level prior from last season for the first few gameweeks.
8. **Bonus and saves.** Bonus is now event-driven (`bonus.py`, done). Remaining: model BPS directly (bonus is
   top-3 BPS *within a match*, so a goal is worth less when a teammate also scores), GK bonus (correlation fell
   slightly) and GK saves, which are over-projected (0.60): use shots-on-target faced rather than rate x minutes.
9. **Forward assists factor (2.04)** rests on ~850 player-games; stabilise it (stronger shrinkage or
   a model of forward xA) and re-check as data accumulates.
10. **Re-test volume-dependent goal calibration** and finishing persistence once there are 20+ gameweeks.

## P2: planner features

1. **Multi-week transfer planner.** Today it scores single swaps only and ignores the bank. Add beam search
   over 1-3 moves with hits (-4), free-transfer banking (cap 5), a bank balance and selling prices (taken from
   config, since the team endpoint needs a login).
2. **Chip planner.** Bench Boost / Free Hit / Wildcard / Triple Captain timing: detect double/blank
   gameweeks from fixtures, value Bench Boost from projected bench points, Free Hit from the gap between the
   current XI and the best XI in a gameweek. Check the chip reset gameweek from `chips` in bootstrap-static
   each season (first-half chips expired after GW19 in 2026/27).
3. **Roll vs use** a free transfer: value the banked transfer explicitly.
4. **Price-change awareness** (ownership and net transfers) for timing moves.

## P3: UI and deployment

1. **Streamlit app** (stub in `app/`): squad editor/upload, projections table, XI and captain, transfer
   suggestions, a backtest page with charts.
2. **(in progress)** **Or static site:** nightly GitHub Action runs the model and writes JSON; a small front end on GitHub Pages
   shows top lists and the backtest. No server to run.
3. **Charts:** calibration plot (predicted vs actual by bucket), per-gameweek fixture heatmap, residuals.
4. **Dockerfile** and a one-command run.

## P4: portfolio polish

- Screenshots / short GIF in the README; CI badge.
- Refresh `docs/BACKTEST.md` as the season progresses; add a plot of RMSE vs cutoff.
- Short write-up of the findings: defender goals over-projected ~2x, finishing under-performance does not
  persist, last-season priors add little, and what a 8%-variance model is still good for.
- Replace the placeholder name in `LICENSE`.

## Known limitations to keep documented

- Ten gameweeks of data; calibration partly fitted to the window it is judged on.
- Unofficial API; fields can change. Pen counts and some overrides are manual.
- `legacy/` holds the original exploratory scripts (hard-coded paths, chained). They are a parity reference
  only; do not extend them.
