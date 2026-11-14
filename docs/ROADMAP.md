# Roadmap: planned modifications

Ordered roughly by priority. Each item says why it matters. "Parity" means: after the change,
`fplxpts squad/moves/backtest --no-odds` must reproduce the golden numbers below unless the change is meant to move
them.

**Golden numbers (data through GW10, shipped config, bookmaker odds OFF):** live odds change from day to day, so the
golden numbers are defined with `--no-odds`: `fplxpts --ttl 999999999 squad --no-odds --squad config/squad.example.toml`,
`fplxpts --ttl 999999999 export --no-odds --out ...`, `fplxpts --ttl 999999999 backtest --no-odds`.
GW11-15 expected points: Rudoni 22.7, Konsa 25.0,
N.Jackson 26.0, Isak 23.8, Haaland 26.6, Van Hecke 21.9 (Isak's minutes are overridden by hand in
`config/squad.example.toml`; without the override, as in the export, he is 25.2). Backtest: 9,267 player-games,
RMSE 2.965 (calibrated in-sample 2.945, walk-forward 2.958), time split 2.847 -> 2.833. The backtest with the shipped
historical odds (deterministic, Football-Data.co.uk CSV; plain `fplxpts backtest`): RMSE 2.955 (in-sample 2.935,
walk-forward 2.948), time split 2.843 -> 2.830. (Updated when `prior_lambda` was put back from 0.3 to 0.15 after an
isolated sweep (docs/BACKTEST.md, "prior_lambda kept at 0.15") and every calibration factor was refitted; before that:
Rudoni 22.8, Konsa 24.9, N.Jackson 26.1, Isak 24.2, Haaland 27.2, Van Hecke 21.6, Isak without override 25.6,
RMSE 2.966 / 2.946 / 2.958, 2.850 -> 2.836 without odds and 2.956 / 2.936 / 2.949, 2.846 -> 2.833 with. Updated when
the recency half-lives and last-season prior were changed on the evidence of four past seasons, `form_halflife` 4 -> 8,
`team_halflife` 3 -> 8, `prior_min` 450 -> 300, `prior_lambda` 0.15 -> 0.3, and every calibration factor was refitted; before that: Rudoni 22.7, Konsa 24.7,
N.Jackson 26.1, Isak 22.7, Haaland 25.3, Van Hecke 22.5, Isak without override 24.1, RMSE 2.963 / 2.943 / 2.955,
2.840 -> 2.826 without odds and 2.953 / 2.933 / 2.945, 2.837 -> 2.824 with. Updated when save points became E[floor(saves / 3)] and the GK
saves factor was refitted, 0.668 -> 0.959: the six outfield golden numbers did not move, goalkeepers did, e.g. Raya
20.9 -> 20.7; before that the backtest lines were 2.964 / 2.944 / 2.956, 2.840 -> 2.825 without odds and
2.954 / 2.934 / 2.946, 2.837 -> 2.823 with. Odds anchoring, `odds_weight = 0.5`, and the ratings nudge,
`odds_ratings_weight = 1`, do not move the odds-off numbers; the odds-on backtest line was added then. Before the nudge
was switched on the odds-on line was RMSE 2.959 / 2.939 / 2.951, 2.840 -> 2.826. Updated when the calibration
factors were refitted with pseudo-point shrinkage k = 160 and walk-forward calibration was added; before that:
Rudoni 22.6, Konsa 24.9, N.Jackson 26.7, Isak 23.2, Haaland 25.6, Van Hecke 22.6, Isak without override 24.5,
RMSE 2.964 / 2.944, 2.840 -> 2.827. Updated when the minutes model started skipping inferred
injury/suspension absences, `absence_starts_before = 2`; the six squad numbers did not move, before that: Isak
without override 19.7, RMSE 2.962 / 2.943, 2.837 -> 2.827. Updated when strength-of-schedule team ratings were switched on,
`team_sos_iters = 20`; before that: Rudoni 22.9, Konsa 24.7, N.Jackson 26.9, Isak 23.2, Haaland 25.5,
Van Hecke 23.1, RMSE 2.962 / 2.943, 2.834 -> 2.825. Updated when the opponent DC-allowed factor was switched on,
`dc_opp_k = 40`; before that: Rudoni 22.9, Konsa 24.4, N.Jackson 26.9, Isak 23.2, Haaland 25.5, Van Hecke 23.3,
RMSE 2.964 / 2.945, 2.835 -> 2.826. Updated when bonus became event-driven; before that:
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

1. **Out-of-sample reporting.** (mostly done) `fplxpts backtest` now refits the calibration at each cutoff on
   outcomes known by then (`backtest.walk_forward_calibration`) and prints that out-of-sample line next to the
   in-sample one; the shrinkage strength (k = 160) was chosen on it (see docs/BACKTEST.md). Remaining: the
   hyper-parameter sweeps and feature tests elsewhere in docs/BACKTEST.md still quote in-sample calibrated RMSE;
   report walk-forward for future ones, and add a by-cutoff plot.
2. **Team news in team ratings.** Ratings use season-long xG that still includes players who are now
   injured/suspended (key attackers or defenders). Adjust attack/defence for who is actually available.
3. **Better minutes model.** The mean of the last 5 games, now skipping inferred injury/suspension absences
   (done, `absence_starts_before = 2`: a run of 0-minute games is dropped when the player started his last two
   played games before it and his first game back; see docs/BACKTEST.md). Remaining: starts vs sub appearances,
   rotation after cup/European weeks, fixture congestion (Dec 26 - Jan 1 run), a better way to tell rotation from
   injury than the start/bench/start pattern (FPL rows have no injury flag), and the general over-projection
   (predicted minutes are ~8 per game too high, 67 vs 58, before calibration; the skip rule adds ~0.6). Re-check the
   rule at 20+ gameweeks, ideally with historical availability flags in the backtest.
4. **Suspension risk.** Yellow-card accumulation (5 by GW19 -> ban) is only a -1 point cost today.
5. **Haul probability for captaincy.** Replace expected points with a distribution per player
   (Poisson/negative-binomial per component) and report P(>=10) and P(<=2) alongside the mean.
6. **Penalty ingestion.** Penalty goals are a manual list in the squad TOML (FPL exposes only misses).
   Automate from a documented source (respect its terms) or a `data/pens.csv`. Scale the forward share by team
   attacking strength rather than a flat 0.10 xG per game; handle injured/suspended primary takers.
7. **Priors.** Strip penalty xG from last-season rates (open, and a reason `prior_lambda` stayed at 0.15: last
   season's xG still includes penalties, so a taker's prior double-counts them next to the flat `pen_share_xg`, more so
   the heavier the prior; re-test a stronger prior once they are stripped); handle promoted teams (no top-flight history) and
   club moves; consider a team-level prior from last season for the first few gameweeks.
8. **Bonus and saves.** Bonus is now event-driven (`bonus.py`, done). Remaining: model BPS directly (bonus is
   top-3 BPS *within a match*, so a goal is worth less when a teammate also scores), GK bonus (correlation fell
   slightly) and GK saves: save points are now E[floor(saves / 3)] (done; factor 0.67 -> 0.96). Remaining: use shots-on-target faced rather than rate x minutes.
9. **Forward assists factor** (raw 2.21, shipped 1.50 after k = 160 shrinkage) rests on ~850 player-games
   (114 expected points); stronger shrinkage is now in. Remaining: a model of forward xA, re-check as data
   accumulates. Same for FWD dc (raw 0.08, shipped 0.72) and GK yc.
10. **Re-test volume-dependent goal calibration** and finishing persistence once there are 20+ gameweeks.
11. **Opponent DC-allowed factor** (`dc_opp_k = 40`, on by default): backtest through GW10 showed a small gain in
    total RMSE but no gain on the dc component itself (see docs/BACKTEST.md). Re-test at 20+ gameweeks and switch
    it off (`dc_opp_k = 0`) if the total-RMSE gain does not persist.
12. **Damped opponent xG for clean sheets** (`opp_xg_gamma`, implemented, 1.0 = off): flattens the over-strong
    clean-sheet response to the opponent in-sample, but gamma chosen on early rounds does worse on later rounds and
    stronger `team_shrink_k` is no better (see docs/BACKTEST.md). Re-test at 20+ gameweeks, perhaps with gamma
    depending on games played.
13. **Strength-of-schedule team ratings** (`team_sos_iters = 20`, on by default): opponent-adjusted attack/defence
    ratings improved team-level opponent-xG error (vs match xG) slightly and were neutral on goals and total RMSE,
    with a small, non-significant worsening of the time split (see docs/BACKTEST.md). Re-test at 20+ gameweeks;
    consider adjusting for the opponent's rating at the time of the match rather than its current rating.

14. **Bookmaker odds** (`odds.py`, `odds_weight = 0.5`, on by default; see docs/BACKTEST.md). Done: Football-Data.co.uk
    historical odds in the backtest (pre-match averages, round c+1 only at cutoff c), The Odds API for live
    projections (cached 12 h, fallback to the model when there is no key or no odds), next-round blend of team
    expected goals on both sides. The ratings nudge (`odds_ratings_weight = 1`, odds as extra
    games in the team ratings; switched on after being tested and shipped off), which also improved rounds 2-5 ahead
    significantly; re-check that it holds at 20+ gameweeks. Remaining: re-test w and b with more gameweeks; anchor GW+2 fixtures when the live feed has
    them (needs a backtest with odds taken that far ahead); Asian handicap / exact totals lines; record the fetch
    time relative to kickoff (closing odds were clearly better than the pre-match averages); add the
    `ODDS_API_KEY` repository secret.
15. **Football-Data match xG as the team xG source** (not started, out of scope of the odds work): the
    Football-Data CSV also has per-match xG (`HxG`, `AxG`). Team xG is currently derived from goalkeeper
    expected-goals-conceded in the FPL API; compare the two in the backtest and consider switching or averaging.

16. **Follow-ups from the past-seasons study** (docs/BACKTEST.md, "Past seasons"; `fplxpts backtest --season all`;
    the shipped defaults were frozen for the study; the longer recency windows have since been shipped). In order of
    evidence:
    - **Calibrate towards last season's factors.** Shrink the walk-forward factors towards the previous season's
      instead of towards 1 (`(sum actual + k * f_prev) / (sum predicted + k)`): significantly better in all three
      past seasons with a predecessor (-0.009 to -0.015 squared error overall, -0.09 to -0.16 at cutoffs 1-5). For the
      live model, refit the shipped factors with 2025/26 rows as the target: several shipped factors (cs, gc, GK
      bonus, MID goal/assist) lie outside every past season's range and look like ten-week luck. Implemented as an
      option, off by default (`fplxpts backtest --fit --prior-season 2025-26`); re-checked with the new half-lives
      and previewed, not shipped (docs/BACKTEST.md): -0.006 to -0.023 overall, -0.04 to -0.12 at cutoffs 1-5. To
      adopt: choose k (640 looks better than 160 on past seasons), paste the factors, update the golden numbers.
    - **Longer recency windows** (DONE 2026-11, owner's decision on the past-season evidence). `form_halflife` 8 and
      `team_halflife` 8 with `prior_min` 300 are shipped, calibration refitted; `prior_lambda` was first raised to 0.3
      with them and then put back to 0.15 (DONE 2026-11): an isolated sweep (docs/BACKTEST.md, "prior_lambda kept at
      0.15") found 0.3 no better than 0.15 in any season (0.15 significantly better at cutoffs 1-5 of 2025/26,
      borderline at cutoffs 6-10 of 2026/27), and last-season xG still contains penalties, so a heavier prior
      double-counts penalty xG for takers (see item 7). As a four-value combination (with `prior_lambda` 0.3, before the
      revert) the change improved walk-forward squared error in all four past seasons after the saves fix (-0.013 to
      -0.042) and was slightly worse, not significantly, on 2026/27 GW1-10 (+0.020 [-0.012, +0.052], top-12 4.64 ->
      4.50; see docs/BACKTEST.md).
      Follow-up: re-test on 2026/27 at GW20 (old vs new settings, walk-forward); revert if the current season keeps
      disagreeing significantly.
    - **Team-level prior from last season** for the start of a season: shrink each team's ratings towards its
      previous-season rating (halfway to 1, 6 pseudo-games), promoted teams towards the relegated teams' average.
      Small but significant gain in all three seasons, about -0.1 for promoted teams' players at cutoffs 1-5 (they are
      over-projected by +0.4 to +1.2 points per game early). Needs the previous season's fixtures/xG (the archive
      loader has them; the live API does not keep last season's team xG).
    - **Opponent DC factor**: no effect on 2025/26, the only other season with defensive contributions; switch off
      (`dc_opp_k = 0`) unless 2026/27 GW20+ shows a gain (item 11).
    - **Saves points as E[floor(saves / 3)]** under Poisson (like `gc_penalty`), not `saves / 3` (DONE, see
      docs/BACKTEST.md): the GK saves factor was 0.57-0.67 in every season, and GK bonus (0.54-0.59 past, 0.86 shipped) rides on over-projected saves and
      clean sheets.
    - **Season-start bias** (+0.26 to +0.32 per player-game at cutoffs 1-5 in every season): mostly the calibration
      having nothing to fit on; the first follow-up above addresses it. Summer movers' priors were earned in another
      team's system (the prior hurt them in 2025/26).
    - Backtest gaps that remain: no historical availability flags; the archive's 2022/23 has no xG before GW16; only
      2025/26 has the full two-season prior. Add 2026/27 to `archive.SEASONS` once the archive publishes it.

## P2: planner features

1. **Multi-week transfer planner.** Today it scores single swaps only and ignores the bank. Add beam search
   over 1-3 moves with hits (-4), free-transfer banking (cap 5), a bank balance and selling prices (taken from
   config, since the team endpoint needs a login).
2. **Chip planner.** Bench Boost / Free Hit / Wildcard / Triple Captain timing: detect double/blank
   gameweeks from fixtures, value Bench Boost from projected bench points, Free Hit from the gap between the
   current XI and the best XI in a gameweek. Check the chip reset gameweek from `chips` in bootstrap-static
   each season (first-half chips expired after GW19 in 2026/27).
   The Projector now sums a double gameweek's two fixtures, and past seasons (`backtest --season`) give double/
   blank-gameweek rounds to test the planner on.
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
  persist, last-season priors help over a whole season (the ten-week search said they add little), and what a
  8%-variance model is still good for.
- Replace the placeholder name in `LICENSE`.

## Known limitations to keep documented

- Ten gameweeks of data; shipped calibration fitted on the whole window (the walk-forward line is the
  out-of-sample check, and only its early cutoffs identify the shrinkage strength).
- Past seasons (`backtest --season`) come from a community archive; they have no availability flags either, 2022/23
  has no xG before GW16; the half-lives and prior weights were chosen on them, the other hyper-parameters were not
  re-tuned (docs/BACKTEST.md, Past seasons).
- Unofficial API; fields can change. Pen counts and some overrides are manual.
- `legacy/` holds the original exploratory scripts (hard-coded paths, chained). They are a parity reference
  only; do not extend them.
