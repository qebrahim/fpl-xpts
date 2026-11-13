# Backtest: method and findings

Data: 2026/27 season, GW1-10 (finished), via the public FPL API. Re-run with `fplxpts backtest --fit`.

## Method

For each cutoff gameweek `c` in 1..9 the model is rebuilt using **only** matches up to `c`, then predicts
each player's expected points for rounds `c+1 .. c+5` (capped at GW10) using the actual fixture (opponent,
venue). Predictions are compared with the points players really scored (including 0-minute games).
Players need at least 90 minutes by the cutoff. That gives 9,267 player-games.

Baselines: season points-per-game so far, and the last four games.

Calibration: for each (position, component) the factor is `sum(actual) / sum(predicted)`, shrunk towards 1
with 20 pseudo-points. To avoid grading the factors on the data they were fitted on, there is also a
**time split**: fit on target rounds <= 6, test on rounds >= 7.

## Results

| Predictor | RMSE | Bias | Corr |
|---|---|---|---|
| Model, uncalibrated | 2.964 | +0.27 | 0.288 |
| Model, calibrated (in-sample) | 2.945 | +0.02 | 0.288 |
| Naive: season PPG | 3.332 | | |
| Naive: last-four form | 3.365 | | |

Time split (fit rounds <= 6, test rounds >= 7): RMSE 2.835 -> 2.826, bias +0.227 -> -0.048.

**Bonus by how it is earned** (`bonus.py`): bonus is projected from the expected goals, assists, clean sheet and
saves in each fixture (per-position marginal bonus per event, fitted on rounds up to the cutoff) plus the
player's own residual baseline, instead of a flat rate per 90. Bonus-component correlation with actual bonus rose
for DEF/MID/FWD (e.g. FWD 0.22 -> 0.26, all 0.17 -> 0.20) and fell for GK (0.13 -> 0.08); total RMSE is
unchanged because bonus is a small share of points. The bonus calibration factors moved towards 1 for outfield
players (FWD 1.29 -> 1.06, MID 0.75 -> 0.81, DEF 0.88 -> 0.92), i.e. the model now explains most of the position
differences itself.

The model explains only about 8% of the variance in single-week points (corr 0.29). That is normal for FPL:
most of a week's points are luck. The useful signal is in ranking players, not in point estimates.

## Hyper-parameter search (27 settings)

Form half-life {season-long, 4, 6 games} x last-season prior weight {0, 0.15, 0.3} x prior pseudo-minutes
{180, 270, 450}. Best: half-life 4, prior weight 0.15, prior minutes 450 (RMSE 2.9622 vs 2.9703 for
season-long with no prior). The paired squared-error difference is -0.048 +/- 0.033 (bootstrap by player),
so the gain is consistent in direction but **not statistically significant**. The last-season prior in
particular adds very little; it is kept small as a stabiliser.

## What the backtest found (calibration factors)

| Position | Component | Factor | Reading |
|---|---|---|---|
| DEF | goal | 0.52 | defender goal threat over-projected ~2x |
| MID | goal | 0.79 | mid xG converted ~20% worse than projected |
| FWD | goal | 0.83 | |
| FWD | assist | 2.04 | forward assists under-projected (small sample: ~850 player-games) |
| DEF | cs / gc | 1.12 / 0.76 | clean sheets more likely than Poisson-on-xG says |
| MID | cs | 1.26 | |
| GK | sav | 0.60 | saves over-projected |
| all | app | 0.86-0.94 | minutes over-projected (rotation under-priced) |

## Does finishing persist?

Hypothesis: players who under-perform their xG keep under-performing, so haircut them. Test: group
attackers by earlier (goals - xG) and compare later goal points with the volume-calibrated projection.
Result: players who had under-performed scored **1.2-1.3x** the projection afterwards, and over-performers
about 1.0x. No evidence for a haircut, so none is applied. (Caveat: extremes of goals-minus-xG are
confounded with shot volume, hence the volume control.)

## Limitations

- Only 10 gameweeks; calibration factors are partly fitted to the window they are evaluated on (the time
  split mitigates but does not remove this). Refit as the season grows.
- The backtest uses raw histories. Per-match penalty data is not available for past gameweeks, so
  penalties are stripped only in live projections.
- Last-season priors include penalty xG and cannot see club changes.
- Goal and assist calibration was tested for dependence on shot volume (bucketed ratios); it did not improve
  the time-split error, so flat per-position factors are used.
