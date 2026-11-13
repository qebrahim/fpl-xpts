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
| Model, uncalibrated | 2.964 | +0.29 | 0.289 |
| Model, calibrated (in-sample) | 2.944 | +0.04 | 0.289 |
| Naive: season PPG | 3.332 | | |
| Naive: last-four form | 3.365 | | |

Time split (fit rounds <= 6, test rounds >= 7): RMSE 2.840 -> 2.827, bias +0.260 -> -0.015.

The backtest applies **no availability flags**: a player who is injured after the cutoff is still projected and
scores 0. The live Projector drops players flagged out (`status` i/s/n/u or 0% chance) and scales the next
gameweek by the chance of playing. This mostly matters for the minutes section below.

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

## Opponent "defensive contributions allowed" factor (tested, shipped off)

Idea: defenders' DC hit rate (60+ minute games) varies by opponent (14% vs CRY to 54% vs TOT through GW10,
league 28.5%), so scale each player's hit rate by a per-opponent factor
`(hits made against t + k) / (hits expected from league position-group rates + k)`, divided by the average factor
of the opponents the player's team has faced (`teams.py: dc_obs_exp / dc_opp_factors`, `ModelCfg.dc_opp_k`).

| dc_opp_k | RMSE | RMSE cal | time split | top-12 | DEF dc Brier | MID dc Brier |
|---|---|---|---|---|---|---|
| off | 2.9641 | 2.9449 | 2.8355 -> 2.8261 | 4.52 | 0.14097 | 0.07695 |
| 5 | 2.9592 | 2.9401 | 2.8307 -> 2.8214 | 4.75 | 0.14325 | 0.07845 |
| 10 | 2.9601 | 2.9411 | 2.8317 -> 2.8226 | 4.76 | 0.14141 | 0.07766 |
| 20 | 2.9613 | 2.9423 | 2.8329 -> 2.8238 | 4.78 | 0.14067 | 0.07723 |
| 40 | 2.9624 | 2.9433 | 2.8338 -> 2.8247 | 4.74 | 0.14056 | 0.07704 |
| 80 | 2.9631 | 2.9440 | 2.8345 -> 2.8253 | 4.63 | 0.14067 | 0.07697 |

The dc component itself does not get better: DEF dc squared error changes by -0.002 +/- 0.002 at k=40 and MID gets
slightly worse at every k (bootstrap by player). Total RMSE does fall a little (-0.010 +/- 0.004 squared error at
k=40), but almost all of that comes from the dc change happening to line up with errors in *other* components,
mainly DEF clean sheets against teams like TOT/BRE/NFO, not from predicting DC better. On that evidence alone the
feature would stay off (`dc_opp_k = 0` reproduces the old projections exactly).

**Decision: shipped on at `dc_opp_k = 40`**, the conservative end of the sweep, as a modelling judgement that the
opponent matters for defensive actions, accepting that the measured gain is in total RMSE (2.964 -> 2.962,
calibrated 2.945 -> 2.943) and not yet in the dc component. Effect on GW11-15 projections: top-10 defenders move
by -0.43 to +0.37 points, midfielders by under 0.1, goalkeepers and forwards not at all. Re-test with more
gameweeks.

## Damping the opponent xG for clean sheets (tested, shipped off)

(This sweep was run before `dc_opp_k` was switched on, so its baseline row shows RMSE 2.9641 / 2.9449.)

Finding: out of sample, P(clean sheet) reacts too strongly to the opponent. By predicted opponent xG (team level,
next 5 rounds, data through GW10): <0.9 predicted 45% vs actual 56%; 1.5-1.8 19% vs 26%; >=1.8 13% vs 25%.
Tested fix: `opp_xg = lg_v * (att_opp * dfn_team) ** gamma` for the clean sheet (`teams.py: damped_opp_xg`,
`ModelCfg.opp_xg_gamma`), with and without also feeding the goals-conceded penalty. Brier is on P(cs and 60')
after refitting one scale per position (what the calibration factor does); team Brier is on raw exp(-xG).

| setting | RMSE | RMSE cal | time split | top-12 | GK cs Brier | DEF cs Brier | team Brier | team P(cs) xG>=1.8 | late team Brier |
|---|---|---|---|---|---|---|---|---|---|
| gamma 1.0 (shipped) | 2.9641 | 2.9449 | 2.8355 -> 2.8261 | 4.52 | 0.17607 | 0.15459 | 0.20780 | 0.13 / 0.25 | 0.21297 |
| gamma 0.85 | 2.9641 | 2.9454 | 2.8364 -> 2.8274 | 4.50 | 0.17584 | 0.15442 | 0.20790 | 0.14 / 0.25 | 0.21381 |
| gamma 0.7 | 2.9643 | 2.9461 | 2.8375 -> 2.8290 | 4.52 | 0.17580 | 0.15439 | 0.20819 | 0.14 / 0.25 | 0.21485 |
| gamma 0.55 | 2.9649 | 2.9472 | 2.8390 -> 2.8307 | 4.49 | 0.17598 | 0.15452 | 0.20869 | 0.15 / 0.25 | 0.21611 |
| gamma 0.4 | 2.9657 | 2.9487 | 2.8407 -> 2.8327 | 4.44 | 0.17639 | 0.15482 | 0.20939 | 0.16 / 0.25 | 0.21757 |
| gamma 0.25 | 2.9668 | 2.9504 | 2.8427 -> 2.8350 | 4.41 | 0.17705 | 0.15530 | 0.21029 | 0.17 / 0.25 | 0.21923 |
| team_shrink_k 6 | 2.9633 | 2.9458 | 2.8408 -> 2.8320 | 4.46 | 0.17582 | 0.15427 | 0.20832 | 0.14 / 0.25 | 0.21490 |
| team_shrink_k 10 | 2.9654 | 2.9486 | 2.8462 -> 2.8376 | 4.39 | 0.17613 | 0.15447 | 0.20905 | 0.15 / 0.25 | 0.21653 |

(Gamma rows are clean-sheet only; also damping the gc penalty was slightly worse on total RMSE at every gamma.)
Damping does pull the bucket means together, but it does not help where it counts: the in-sample cs Brier gains
are tiny (GK -0.0003 at 0.7) and selecting gamma on target rounds <= 6 picks 0.25, which is *worse* than 1.0 on
rounds > 6 (GK+DEF cs Brier 0.1629 vs 0.1601, team Brier 0.2192 vs 0.2130, time-split RMSE 2.835 vs 2.826).
Damping and stronger rating shrinkage help early (few games per team) and hurt later. Paired bootstraps (by
player / fixture) put every cs-Brier change within noise; the time-split total squared error is significantly
worse for gamma <= 0.55 and for team_shrink_k 6 and 10. Most of the high-xG miss is away teams at strong home
attacks (115 fixtures: 13% predicted, 30% actual); since that bucket's actual goals against (1.72) would still
imply only 18% under Poisson, it is mostly goal-count over-dispersion around the prediction, not a mis-scaled
xG. A negative-binomial zero probability was tried as a quick check and does not beat a plain scale factor out
of sample either. So **gamma stays 1.0** (reproduces the old projections exactly). Re-test with more gameweeks.

## Strength-of-schedule team ratings (tested, shipped on)

Problem: team ratings averaged each game's xG divided only by the league venue average, so after ~10 games a team
that had met weak attacks looked like a better defence than it is (and soft defences flattered attacks).
Change (`teams.py: ratings`, `ModelCfg.team_sos_iters`): each game's xG for is also divided by the opponent's
defence rating and xG against by the opponent's attack rating; the opponent ratings come from the previous pass
(fixed-point iteration from the unadjusted ratings), with the same recency weights and `team_shrink_k` shrinkage
each pass, opponent ratings floored at 0.2 as divisors, and each pass rescaled so the league mean of each rating
stays at its unadjusted value. It converges to ~1e-5 within 20 passes. The past-opponent norms `pn_att` / `pn_opp`
(the environment player rates were earned in) are built from the *adjusted* unweighted ratings, so the
numerator and denominator of the matchup multipliers are on the same scale (building them from unadjusted ratings
instead was within noise: RMSE 2.9621 vs 2.9616, time split 2.8265 vs 2.8269). `pn_dc` is unchanged (it uses the
DC-allowed factors, not the xG ratings). `team_sos_iters = 0` reproduces the old ratings exactly.

At GW10 the ratings move by up to 0.11 (Fulham and Spurs attack -0.11, having met soft defences; Sunderland and
Leeds attack +0.08/+0.09; Everton defence +0.10 worse, having met weak attacks recently).

| team_sos_iters | RMSE | RMSE cal | time split | top-12 | opp-xG vs match xG RMSE, next 1 / next 5 | vs goals RMSE, next 1 / next 5 | GK cs Brier | DEF cs Brier | MID goal RMSE | FWD goal RMSE |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 (off) | 2.9624 | 2.9433 | 2.8338 -> 2.8247 | 4.74 | 0.8305 / 0.8288 | 1.2267 / 1.2053 | 0.17650 | 0.15419 | 1.4809 | 2.0418 |
| 1 | 2.9612 | 2.9427 | 2.8372 -> 2.8278 | 4.66 | 0.8212 / 0.8194 | 1.2241 / 1.2039 | 0.17595 | 0.15390 | 1.4806 | 2.0452 |
| 2 | 2.9612 | 2.9425 | 2.8357 -> 2.8261 | 4.79 | 0.8235 / 0.8241 | 1.2240 / 1.2056 | 0.17601 | 0.15397 | 1.4803 | 2.0453 |
| 3 | 2.9616 | 2.9430 | 2.8367 -> 2.8271 | 4.69 | 0.8239 / 0.8240 | 1.2249 / 1.2063 | 0.17603 | 0.15401 | 1.4806 | 2.0467 |
| 20 (shipped) | 2.9616 | 2.9430 | 2.8366 -> 2.8269 | 4.73 | 0.8239 / 0.8246 | 1.2249 / 1.2066 | 0.17603 | 0.15401 | 1.4805 | 2.0468 |

Team-level rows: predicted opponent xG `lg * att_opp * dfn_team` for every fixture in the next 1 or 5 rounds after
each cutoff (180 / 700 team-matches; 176 / 696 with match xG). Paired bootstrap at 20 passes (2000 reps, by fixture
for team metrics, by player for player metrics; difference on - off, 95% CI): opp-xG squared error vs match xG
-0.011 [-0.033, +0.014] next 1 and -0.007 [-0.022, +0.009] next 5 (MAE -0.010 / -0.005, CIs just touching 0); vs
goals -0.004 [-0.035, +0.025] and +0.003 [-0.015, +0.021]; player squared error -0.005 [-0.025, +0.016]
uncalibrated, -0.002 [-0.022, +0.018] calibrated; time-split (rounds > 6) squared error +0.013 [-0.014, +0.040];
cs Brier GK -0.0005 [-0.0023, +0.0016], DEF -0.0002 [-0.0009, +0.0005]; goal squared error MID -0.001 [-0.008,
+0.006], FWD +0.021 [-0.023, +0.066]. A single pass (a partial, damped adjustment) is the only setting with a CI
clear of zero on team xG (next 5: -0.016 [-0.031, -0.000]) but is worse on the time split and top-12, and was
picked in-sample, so the converged version ships.

**Decision: shipped on at `team_sos_iters = 20`.** Every effect is small and inside the noise at 10 gameweeks; the
direction is right on the most direct test (opponent xG vs match xG), neutral on goals and total RMSE, slightly
worse but not significantly on the time split. Calibration factors were not refitted. Re-test with more gameweeks.

## Minutes model: skipping injury absences (tested, shipped on)

Problem: `mf` (minutes share), `app` (appearance points) and `p60` (P(60+ minutes)) are plain averages over the last
five match rows, and a game missed through injury or suspension is a 0-minute row that counts exactly like being
dropped. Isak (minutes 90 90 63 90 80 **0** 78 76 90 90) had mf 0.74 / app 1.6 / p60 0.8 at GW10 and was projected
19.7 over GW11-15 although he is fit and starting. Current availability is already handled by FPL's flags in the
live Projector, so past absences should not also depress the minutes model.

Data: FPL match rows have `minutes` and `starts` but no injury or squad flag. There is one row per team match from
the player's arrival (24 of 372 players arrived mid-season), so "injured", "suspended", "not in the squad" and
"unused substitute" all look the same: 0 minutes, 0 starts. 814 of 3,678 rows (GW1-10) are 0-minute rows. There were
no double or blank gameweeks in GW1-10 (one row per player per round).

Rule (`players.py: absence_rows / minutes_window`, `ModelCfg.absence_starts_before / absence_starts_after`): a run of
consecutive 0-minute rows is treated as an absence and skipped when the player **started each of his last 2 played
games before it and his first played game after it** (an established starter who is back in the side). The five-game
window then reaches further back. Runs the player has not returned from (still out), or returned from only as a
substitute, keep counting, and so do zeros of players who were not starting before. Because a skipped run is always
bracketed by at least three starts, the window never shrinks below three games because of the rule. Only rows up to
the cutoff are used (a run is not skipped until the return game is itself before the cutoff).
`absence_starts_before = 0` reproduces the old mf/app/p60 exactly.

Candidates (the "return" variants require the player to have played again after the zeros):

| rule | player-cutoffs changed (of 2,556) | RMSE | RMSE cal | time split | top-12 u / c | minutes bias / MAE / RMSE, all | changed group: minutes bias / MAE / RMSE (old on same games) | app RMSE cal, changed (old) |
|---|---|---|---|---|---|---|---|---|
| A: off (old) | 0 | 2.9616 | 2.9430 | 2.8366 -> 2.8269 | 4.73 / 4.68 | +8.4 / 24.0 / 35.2 | | |
| B: skip all zeros | 899 | 3.0577 | 3.0142 | 2.9603 -> 2.8970 | 4.38 / 4.36 | +16.2 / 26.0 / 39.1 | +26.9 / 39.3 / 49.4 (+0.6 / 32.8 / 38.1) | 1.009 (0.871) |
| B + return | 591 | 2.9726 | 2.9436 | 2.8558 -> 2.8286 | 4.57 / 4.51 | +12.3 / 23.7 / 35.5 | +13.7 / 30.9 / 39.5 (-6.7 / 32.6 / 37.8) | 0.827 (0.880) |
| C: starts in >= 60% of last 10 (excl. the run) | 557 | 3.0476 | 3.0084 | 2.9431 -> 2.8916 | 4.40 / 4.38 | +14.5 / 25.4 / 38.8 | +33.6 / 41.2 / 53.4 (+3.0 / 34.4 / 39.1) | 1.068 (0.888) |
| C 60% + return | 318 | 2.9713 | 2.9450 | 2.8516 -> 2.8301 | 4.59 / 4.52 | +11.1 / 23.5 / 35.5 | +17.9 / 29.9 / 41.9 (-6.5 / 34.8 / 39.1) | 0.847 (0.909) |
| C 75% + return | 247 | 2.9705 | 2.9453 | 2.8506 -> 2.8312 | 4.65 / 4.56 | +10.7 / 23.6 / 35.6 | +21.0 / 29.0 / 42.8 (-5.1 / 34.5 / 38.8) | 0.850 (0.904) |
| D: 1 start before, 1 after | 149 | 2.9662 | 2.9452 | 2.8435 -> 2.8287 | 4.65 / 4.54 | +9.2 / 24.0 / 35.4 | +19.6 / 30.0 / 40.9 (-0.9 / 31.4 / 36.4) | 0.853 (0.858) |
| **D2: 2 starts before, 1 after (shipped)** | **110** | **2.9638** | **2.9437** | **2.8395 -> 2.8266** | **4.65 / 4.54** | **+8.9 / 23.9 / 35.2** | **+15.4 / 28.4 / 40.7 (-4.4 / 34.1 / 39.1)** | **0.865 (0.915)** |
| D2 + latest game a start | 85 | 2.9638 | 2.9438 | 2.8395 -> 2.8270 | 4.65 / 4.54 | +8.8 / 23.9 / 35.2 | +17.9 / 25.3 / 39.7 (-3.0 / 32.6 / 37.8) | 0.831 (0.889) |
| 2 starts before, 2 after | 51 | 2.9628 | 2.9436 | 2.8384 -> 2.8274 | 4.68 / 4.66 | +8.6 / 24.0 / 35.2 | +20.5 / 27.2 / 40.9 (+1.6 / 31.9 / 36.8) | 0.869 (0.877) |
| 3 starts before, 1 after | 90 | 2.9645 | 2.9447 | 2.8411 -> 2.8286 | 4.65 / 4.54 | +8.8 / 23.9 / 35.3 | +22.7 / 29.8 / 43.7 (+1.3 / 34.4 / 39.5) | 0.920 (0.929) |

Minutes are predicted `mf * 90` against actual minutes in the predicted games (9,267 player-games); the unchanged
group is a sanity check and barely moves for D2 (bias +8.7, MAE 23.7, RMSE 35.0 vs +8.4 / 24.0 / 35.2 for everyone
under A). Paired bootstrap by player (2,000 reps, rule - A, 95% CI) for D2: total squared error +0.013 [-0.013, +0.042]
uncalibrated, +0.004 [-0.019, +0.030] calibrated, time-split (rounds > 6, calibrated) -0.002 [-0.036, +0.035]; changed
group minutes absolute error **-5.7 [-11.4, -0.5]**, squared error +133 [-299, +591] min^2 (not significant).
Skipping zeros without requiring a return (B, C) is significantly worse on every total measure (e.g. B +0.58
[+0.34, +0.84] uncalibrated) because it hands full minutes to players who are still out.

The no-flags wrinkle: in the backtest the changed group's next games include re-injuries and spells the live model
would have caught from the flags (e.g. João Pedro: GW5 absence skipped at cutoffs 6-7, then out from GW8 and flagged
`i` now; he is 6 of the 13 new top-12 picks (uncalibrated) and scored 2 points in them, which is most of the
top-12 drop; by-cutoff bootstrap
of the top-12 change: -0.08 [-0.21, 0.00] uncalibrated, -0.13 [-0.33, -0.02] calibrated). As a proxy for flags,
dropping the 680 predicted games (7.3%) that were, in hindsight, part of an injury-like spell (a 0-minute run after a
start that ended with a start, or that runs to GW10 for a player flagged now): D2 changed-group minutes bias -13.5 ->
+6.6, MAE 30.8 -> 21.5 (difference -9.3 [-14.0, -4.0]), RMSE 35.6 -> 32.7 (squared error -202 [-577, +210]); total
calibrated RMSE 2.9652 -> 2.9633 (-0.012 [-0.032, +0.009]); top-12 4.95 -> 4.92 uncalibrated, 4.94 -> 4.88 calibrated.
With the flag proxy "B + return" has the lowest total RMSE (2.9563, -0.053 [-0.145, +0.041]) but it also skips the
zeros of fringe and rotation players, which is not the intent and is worse without the proxy.

**Decision: shipped on at `absence_starts_before = 2`, `absence_starts_after = 1`.** It is the rule that matches the
intent (ignore injury absences of established players), changes few inputs (110 player-cutoffs, 4.3%; 35 players at
GW10), improves minutes MAE for the players it changes, and is within noise on total RMSE and the time split. Bias
moves up slightly (calibrated +0.019 -> +0.040; by position GK -0.047 -> -0.044, DEF +0.021 -> +0.057, MID +0.026 ->
+0.038, FWD +0.032 -> +0.056) because affected players do miss more of their next games than a regular starter. The
app calibration factors would move by about 1% on a refit (actual/predicted app: DEF 0.860 -> 0.848, MID 0.887 ->
0.883, FWD 0.937 -> 0.931, GK 0.931 -> 0.930); they were not refitted. Limitation: a strict start / bench / start
rotation pattern looks the same as a one-game injury. Effect at GW10: no squad-example player moves (Isak's minutes
are overridden there); Isak without the override 19.7 -> 24.5 over GW11-15.

## Limitations

- Only 10 gameweeks; calibration factors are partly fitted to the window they are evaluated on (the time
  split mitigates but does not remove this). Refit as the season grows.
- The backtest uses raw histories. Per-match penalty data is not available for past gameweeks, so
  penalties are stripped only in live projections.
- Last-season priors include penalty xG and cannot see club changes.
- Goal and assist calibration was tested for dependence on shot volume (bucketed ratios); it did not improve
  the time-split error, so flat per-position factors are used.
