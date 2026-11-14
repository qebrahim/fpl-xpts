# Backtest: method and findings

Data: 2026/27 season, GW1-10 (finished), via the public FPL API; bookmaker odds from Football-Data.co.uk. Re-run
with `fplxpts backtest --fit` (`--no-odds` for the model without odds).

## Method

For each cutoff gameweek `c` in 1..9 the model is rebuilt using **only** matches up to `c`, then predicts
each player's expected points for rounds `c+1 .. c+5` (capped at GW10) using the actual fixture (opponent,
venue). Predictions are compared with the points players really scored (including 0-minute games).
Players need at least 90 minutes by the cutoff. That gives 9,267 player-games.

Baselines: season points-per-game so far, and the last four games.

Calibration: for each (position, component) the factor is `(sum(actual) + k) / (sum(predicted) + k)`, the
actual/predicted ratio shrunk towards 1 with k = 160 pseudo-points (`backtest.CAL_K`; it was k = 20 before the
comparison below). The shipped factors are fitted on all rows, so the "in-sample" line grades them on the data they
were fitted on. Two out-of-sample checks: **walk-forward calibration** (factors refitted at every cutoff from
outcomes known at that cutoff, see below) and a single **time split** (fit on target rounds <= 6, test on rounds >= 7).

## Results

| Predictor | RMSE | Bias | Corr |
|---|---|---|---|
| Model, uncalibrated | 2.964 | +0.29 | 0.289 |
| Model, calibrated (in-sample: shipped factors, fitted on these rows) | 2.944 | +0.03 | 0.289 |
| Model, calibrated walk-forward (out-of-sample) | 2.956 | +0.14 | 0.286 |
| Naive: season PPG | 3.332 | | |
| Naive: last-four form | 3.365 | | |

The three model rows are without bookmaker odds (`fplxpts backtest --no-odds`). With the shipped odds anchoring
(next round only, pre-match odds, blend `odds_weight = 0.5` plus ratings nudge `odds_ratings_weight = 1`, see the section
below) they are 2.954 / 2.934 / 2.946 (bias +0.30 / +0.04 / +0.14, top-12 4.71 / 4.87 / 4.72), time split 2.837 -> 2.823.
(With the blend alone, before the nudge was switched on: 2.959 / 2.939 / 2.951, top-12 4.68 / 4.68 / 4.58, 2.840 -> 2.826.)

Top-12 picks (average actual points of the 12 highest-projected players per cutoff and round): uncalibrated 4.65,
in-sample calibrated 4.57, walk-forward 4.54.

Time split (fit rounds <= 6, test rounds >= 7): RMSE 2.840 -> 2.825, bias +0.260 -> +0.008 (with k = 20 it was
2.840 -> 2.827, bias -0.015).

The walk-forward bias (+0.14) is much higher than in-sample because the first cutoffs have no or little data to fit
on: cutoff 1 is uncalibrated (bias +0.53 on its 660 rows), cutoffs 2-3 are mostly shrunk to 1. From cutoff 4 on
(6,212 rows) walk-forward calibration gives RMSE 2.813 vs 2.824 uncalibrated and bias +0.04 vs +0.24.

## Walk-forward calibration and shrinkage of the factors

`backtest.walk_forward_calibration`: for each cutoff c, the factors applied to the predictions made at c are fitted
only on backtest rows whose **target round is <= c**. Those rows were predicted at earlier cutoffs (c' < round <= c)
from data up to c', and their outcomes were known at c. A row predicted at c (target round c+1..c+5) is never in its
own training set, and no outcome from a round after c is used. With no rows (cutoff 1) every factor is 1.0
(`min_rows` can raise that threshold). `fplxpts backtest` prints this as the walk-forward line.

Variants compared on the same 9,267 rows (WF = walk-forward; per-position columns are the WF bias; TS = time-split
RMSE on rounds > 6; dSE = difference in mean squared error vs the chosen k = 160, walk-forward, with a 95% interval
from a paired bootstrap by player, 2,000 reps; dTop12 bootstrapped by (cutoff, round)):

| variant | in-sample RMSE / bias | WF RMSE | WF bias | GK | DEF | MID | FWD | WF top-12 | TS | dSE vs k=160 | dTop12 vs k=160 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 2.9638 / +0.292 | 2.9638 | +0.292 | +0.27 | +0.27 | +0.33 | +0.23 | 4.65 | 2.8395 | +0.047 [-0.014, +0.104] | +0.12 [-0.06, +0.31] |
| raw ratio (k = 0) | 2.9429 / +0.021 | 3.0010 | +0.163 | -0.14 | +0.10 | +0.21 | +0.50 | 4.45 | 2.8267 | +0.269 [+0.147, +0.407] | -0.09 [-0.27, +0.06] |
| pseudo-points k = 20 (old) | 2.9431 / +0.022 | 2.9600 | +0.130 | -0.05 | +0.10 | +0.19 | +0.13 | 4.59 | 2.8266 | +0.025 [+0.006, +0.045] | +0.06 [-0.07, +0.18] |
| k = 40 | 2.9432 / +0.023 | 2.9576 | +0.130 | -0.00 | +0.10 | +0.19 | +0.11 | 4.58 | 2.8264 | +0.010 [-0.002, +0.024] | +0.05 [-0.04, +0.15] |
| k = 80 | 2.9434 / +0.026 | 2.9562 | +0.134 | +0.05 | +0.11 | +0.18 | +0.10 | 4.50 | 2.8259 | +0.003 [-0.004, +0.009] | -0.04 [-0.12, +0.05] |
| **k = 160 (shipped)** | **2.9436 / +0.033** | **2.9558** | **+0.144** | **+0.10** | **+0.12** | **+0.19** | **+0.10** | **4.54** | **2.8253** | | |
| k = 320 | 2.9440 / +0.045 | 2.9561 | +0.160 | +0.14 | +0.13 | +0.20 | +0.13 | 4.55 | 2.8249 | +0.001 [-0.006, +0.009] | +0.01 [-0.07, +0.09] |
| k = 640 | 2.9448 / +0.066 | 2.9568 | +0.181 | +0.18 | +0.15 | +0.22 | +0.15 | 4.57 | 2.8253 | +0.006 [-0.012, +0.022] | +0.03 [-0.06, +0.12] |
| log scale, weight n/(n+k), k = 300 games | 2.9435 / +0.041 | 2.9567 | +0.173 | +0.12 | +0.15 | +0.21 | +0.15 | 4.56 | 2.8251 | +0.005 [-0.009, +0.018] | +0.03 [-0.04, +0.10] |
| log scale, weight S/(S+k), k = 160 points | 2.9436 / +0.025 | 2.9552 | +0.134 | +0.07 | +0.11 | +0.18 | +0.07 | 4.53 | 2.8255 | -0.004 [-0.009, +0.003] | -0.01 [-0.09, +0.07] |
| pooled across positions, raw | 2.9474 / +0.023 | 2.9567 | +0.111 | -0.09 | +0.16 | +0.15 | -0.08 | 4.65 | 2.8251 | +0.006 [-0.033, +0.047] | +0.11 [-0.10, +0.33] |
| pooled across positions, k = 80 | 2.9471 / +0.026 | 2.9542 | +0.115 | +0.03 | +0.16 | +0.14 | -0.09 | 4.63 | 2.8243 | -0.009 [-0.042, +0.027] | +0.09 [-0.12, +0.32] |

(Also swept: pseudo-points k = 5, 10, 60, 100, 120, 200; linear shrinkage of the ratio with weight n/(n+k) in
player-games, k = 100-10,000; log scale with weight n/(n+k), k = 100-10,000; log scale in points, k = 10-80. None
beat the best rows above by more than noise.)

Readings:
- **The raw ratio overfits out of sample**: significantly worse than no calibration at all (+0.22 [+0.08, +0.37]
  squared error vs none), driven by early cutoffs where a handful of games sets the factor (FWD walk-forward bias
  +0.50).
- **Shrinkage fixes that, and stronger shrinkage than the old k = 20 is better**: k = 20 vs k = 160 +0.025
  [+0.006, +0.045]. The curve is flat from k = 80 to 320; the minimum is at 160-200.
- **Calibration vs none** (k = 160): -0.047 [-0.104, +0.014] squared error overall, not significant over all
  cutoffs, but from cutoff 4 on it is RMSE 2.813 vs 2.824 (-0.062 [-0.143, +0.023]) and fixes most of the +0.24
  bias. It is kept.
- The gain from shrinkage comes almost entirely from cutoffs 2-3; from cutoff 4 on (1,100+ training rows) raw,
  k = 20 and k = 160 are within 0.001 RMSE. So with ten gameweeks the backtest cannot tell how strongly the
  full-data factors should be shrunk; k = 160 is the out-of-sample optimum, not a proven one for the full sample.
- Pooling across positions is within noise on RMSE but leaves position biases (DEF +0.16, FWD -0.09 walk-forward)
  that per-position factors remove; the log-scale forms are within noise of the linear one.

**Decision: per-position pseudo-points shrinkage with k = 160** (`fit_calibration(rows, k=CAL_K)`; `k=0` is the
raw ratio, `k=20` the old method). Same formula as before, only k changed, which is the simplest option among those
tied for best. A cell with S expected points gets the raw ratio with weight about S/(S+160): big cells (app, cs,
goals) barely move, small ones (FWD assist 114 points, FWD dc 72, GK yc 24) are pulled hard towards 1.

Refit on all rows (data through GW10, current default model), old shipped (k = 20, fitted before `dc_opp_k`,
`team_sos_iters` and the minutes absence rule) -> new:

| | GK | DEF | MID | FWD |
|---|---|---|---|---|
| app | 0.932 -> 0.937 | 0.861 -> 0.852 | 0.887 -> 0.885 | 0.938 -> 0.938 |
| goal | | 0.516 -> 0.567 | 0.786 -> 0.796 | 0.832 -> 0.846 |
| assist | | 0.974 -> 0.972 | 1.046 -> 1.037 | 2.038 -> 1.502 |
| cs | 1.158 -> 1.135 | 1.118 -> 1.100 | 1.259 -> 1.212 | |
| gc | 0.818 -> 0.865 | 0.763 -> 0.772 | | |
| dc | | 0.995 -> 0.987 | 0.984 -> 0.989 | 0.284 -> 0.716 |
| bonus | 0.793 -> 0.862 | 0.920 -> 0.927 | 0.813 -> 0.835 | 1.057 -> 1.037 |
| sav | 0.601 -> 0.668 | | | |
| yc | 0.843 -> 0.963 | 1.014 -> 0.999 | 1.011 -> 1.004 | 0.705 -> 0.853 |

Effect on GW11-15 projections (top 10 per position in the site data): forwards -0.2 to -0.6 (N.Jackson 26.74 ->
26.12, Haaland 25.61 -> 25.32; Barry and Haaland swap 2nd/3rd), defenders -0.07 to -0.18, goalkeepers +0.13 to
+0.47 (saves and bonus factors moved up; Verbruggen and Petrović swap 4th/5th), midfielders within +-0.08. No
player enters or leaves a top 10.

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

Shipped (shrunk, k = 160) factors, with the raw ratio in brackets:

| Position | Component | Factor | Reading |
|---|---|---|---|
| DEF | goal | 0.57 (0.50) | defender goal threat over-projected ~2x |
| MID | goal | 0.80 (0.78) | mid xG converted ~20% worse than projected |
| FWD | goal | 0.85 (0.82) | |
| FWD | assist | 1.50 (2.21) | forward assists under-projected (small sample: 114 expected points) |
| DEF | cs / gc | 1.10 / 0.77 (1.11 / 0.75) | clean sheets more likely than Poisson-on-xG says |
| MID | cs | 1.21 (1.26) | |
| GK | sav | 0.67 (0.59) | saves over-projected |
| all | app | 0.85-0.94 | minutes over-projected (rotation under-priced) |

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

## Bookmaker odds as an anchor for team goals (tested, shipped on: next-round blend w = 0.5, ratings nudge b = 1)

Idea: bookmaker prices for a match carry information the xG ratings do not (team news, lineups, market
consensus). A scratch test had found odds-implied goals beat the model's next-round team prediction on clean
sheets. Here it is redone on the current model (strength-of-schedule ratings, all current defaults) with the
**pre-match** prices a forecaster would actually have when building the next gameweek's projections.

Conversion (`odds.py`): 1X2 and over/under 2.5 prices are de-vigged proportionally; the over/under probability fixes
the Poisson total `T` (the sum of two Poissons is Poisson(T)), and `P(home) / (P(home) + P(away))` fixes the split
into `(lambda_home, lambda_away)`. Both steps are monotone and solved by bisection; they invert the Poisson model
exactly (round-trip tests). Data: Football-Data.co.uk's 2026/27 Premier League CSV (100 matches, GW1-10), average
pre-match prices (`AvgH/AvgD/AvgA`, `Avg>2.5/Avg<2.5`) as the realistic proxy for odds fetched a few days before
kickoff; the closing averages (`AvgC...`) are reported only as an upper bound. **At cutoff c only the odds for round
c+1 are used** (`odds.available_at`, with a leakage test).

Variants (all in `teams.py`, `ModelCfg.odds_weight / odds_side / odds_ratings_weight`; all at 0 reproduce the old
output byte for byte):

- **A, next-round anchoring:** in fixtures with odds, each team's expected goals for and against are blended,
  `(1 - w) * model + w * odds`, and the blended values are used everywhere the fixture's team expectations enter
  `points.components`: goals conceded (gc penalty), clean sheet (with the usual `opp_xg_gamma` damping), saves
  (scaled by `xg_against / model xg_against`), and the attacking multiplier. The last is the subtle one:
  `att_m = lg_v * dfn_opp / pn_att_T` is the team's model expected goals `lg_v * att_T * dfn_opp` divided by
  `att_T * pn_att_T`, the team-strength-times-environment its players' rates were earned in. So the anchored
  multiplier is `xg_for / (att_T * pn_att_T)`, i.e. `att_m * xg_for / model xg_for`, which keeps the player-rate
  normalisation (`points.anchored`). `odds_side` restricts the blend to "attack" (a team's own goals: goals,
  assists, attacking bonus) or "defence" (goals it concedes: cs, gc, saves).
- **B, ratings nudge:** the next round's odds-implied goals are added to the team-ratings fit as one extra game per
  team with weight `b` relative to the most recent played game (same venue normalisation, strength-of-schedule
  division and `team_shrink_k` shrinkage as real games; `teams.ratings(extra=...)`). This moves the ratings, so
  rounds 2-5 ahead (no odds) are affected too. The past-opponent norms `pn_att` / `pn_opp` are not touched.

Team level (one row per team-match from the defending side: expected goals conceded vs goals conceded;
P(clean sheet) = exp(-lambda); 180 team-matches next round, 700 over the next 5 rounds). Differences vs off on the
next round, 95% CI from a paired bootstrap **by match** (2,000 reps). A "attack" leaves goals conceded unchanged and A
"defence" equals A "both" at team level, so they are omitted:

| variant | next-1 goals RMSE | next-1 CS Brier | next-1 log-loss | next-5 goals RMSE | next-5 CS Brier | next-5 log-loss | d CS Brier next-1 | d log-loss next-1 |
|---|---|---|---|---|---|---|---|---|
| off | 1.2235 | 0.2053 | 1.4981 | 1.2062 | 0.2071 | 1.4904 | | |
| A w = 0.25 | 1.2025 | 0.2022 | 1.4852 | 1.2008 | 0.2063 | 1.4871 | -0.0031 [-0.0057, -0.0006] | -0.013 [-0.026, -0.001] |
| **A w = 0.5 (shipped)** | **1.1892** | **0.1994** | **1.4772** | **1.1974** | **0.2056** | **1.4850** | **-0.0059 [-0.0112, -0.0008]** | **-0.021 [-0.046, +0.003]** |
| A w = 0.75 | 1.1837 | 0.1969 | 1.4740 | 1.1960 | 0.2049 | 1.4842 | -0.0084 [-0.0167, -0.0005] | -0.024 [-0.061, +0.011] |
| A w = 1 (odds only) | 1.1863 | 0.1946 | 1.4756 | 1.1966 | 0.2044 | 1.4846 | -0.0107 [-0.0223, +0.0004] | -0.023 [-0.071, +0.024] |
| B b = 0.5 | 1.2055 | 0.2028 | 1.4868 | 1.1955 | 0.2055 | 1.4835 | -0.0025 [-0.0043, -0.0007] | -0.011 [-0.021, -0.003] |
| B b = 1 | 1.1958 | 0.2013 | 1.4808 | 1.1896 | 0.2045 | 1.4797 | -0.0040 [-0.0071, -0.0010] | -0.017 [-0.033, -0.003] |
| B b = 2 | 1.1865 | 0.1994 | 1.4751 | 1.1838 | 0.2032 | 1.4761 | -0.0059 [-0.0107, -0.0012] | -0.023 [-0.046, -0.002] |
| B b = 4 | 1.1809 | 0.1977 | 1.4717 | 1.1798 | 0.2020 | 1.4736 | -0.0076 [-0.0144, -0.0010] | -0.026 [-0.057, +0.002] |
| A 0.5 + B 1 | 1.1831 | 0.1977 | 1.4733 | 1.1864 | 0.2036 | 1.4778 | -0.0076 [-0.0146, -0.0009] | -0.025 [-0.057, +0.006] |
| closing: A w = 0.5 | 1.1839 | 0.1983 | 1.4736 | 1.1960 | 0.2053 | 1.4841 | -0.0070 [-0.0122, -0.0020] | -0.025 [-0.050, -0.002] |
| closing: A w = 1 | 1.1760 | 0.1924 | 1.4679 | 1.1940 | 0.2038 | 1.4827 | -0.0129 [-0.0240, -0.0019] | -0.030 [-0.078, +0.015] |
| closing: B b = 1 | 1.1925 | 0.2007 | 1.4786 | 1.1897 | 0.2042 | 1.4797 | -0.0046 [-0.0075, -0.0016] | -0.020 [-0.035, -0.006] |

Player level (9,267 player-games, 2,556 of them next-round rows). RMSE uncalibrated / in-sample calibrated (shipped
factors) / walk-forward calibrated (`walk_forward_metrics`); top-12 = average actual points of the 12 highest
projected per (cutoff, round), uncalibrated / walk-forward; cs Brier on P(cs and 60') per GK/DEF row, goal squared
error per MID/FWD row, both next-round rows, uncalibrated:

| variant | next-1 u / in-s / WF | all u / in-s / WF | top-12 next-1 | top-12 all | GK cs Brier | DEF cs Brier | MID goal SE | FWD goal SE |
|---|---|---|---|---|---|---|---|---|
| off | 2.9369 / 2.9316 / 2.9351 | 2.9638 / 2.9436 / 2.9558 | 5.14 / 5.07 | 4.65 / 4.54 | 0.1793 | 0.1527 | 2.3608 | 4.0455 |
| A both w = 0.25 | 2.9260 / 2.9212 / 2.9241 | 2.9608 / 2.9408 / 2.9529 | 5.15 / 4.92 | 4.65 / 4.50 | 0.1767 | 0.1512 | 2.3559 | 3.9940 |
| **A both w = 0.5 (shipped)** | **2.9187 / 2.9136 / 2.9164** | **2.9588 / 2.9387 / 2.9508** | **5.26 / 5.23** | **4.68 / 4.58** | **0.1744** | **0.1499** | **2.3542** | **3.9581** |
| A both w = 0.75 | 2.9148 / 2.9085 / 2.9118 | 2.9578 / 2.9373 / 2.9496 | 5.25 / 5.37 | 4.68 / 4.62 | 0.1723 | 0.1488 | 2.3557 | 3.9378 |
| A both w = 1 | 2.9144 / 2.9062 / 2.9102 | 2.9576 / 2.9367 / 2.9491 | 5.59 / 5.56 | 4.77 / 4.62 | 0.1704 | 0.1480 | 2.3604 | 3.9330 |
| A attack w = 0.5 | 2.9298 / 2.9252 / 2.9271 | 2.9619 / 2.9419 / 2.9540 | 5.06 / 5.05 | 4.63 / 4.53 | 0.1793 | 0.1527 | 2.3542 | 3.9581 |
| A attack w = 1 | 2.9287 / 2.9233 / 2.9246 | 2.9615 / 2.9413 / 2.9538 | 5.12 / 5.19 | 4.65 / 4.57 | 0.1793 | 0.1527 | 2.3604 | 3.9330 |
| A defence w = 0.5 | 2.9248 / 2.9193 / 2.9235 | 2.9605 / 2.9402 / 2.9524 | 5.19 / 5.32 | 4.67 / 4.60 | 0.1744 | 0.1499 | 2.3608 | 4.0455 |
| A defence w = 1 | 2.9186 / 2.9115 / 2.9170 | 2.9588 / 2.9381 / 2.9502 | 5.35 / 5.51 | 4.71 / 4.61 | 0.1704 | 0.1480 | 2.3608 | 4.0455 |
| B b = 0.5 | 2.9294 / 2.9244 / 2.9277 | 2.9590 / 2.9389 / 2.9510 | 5.20 / 5.04 | 4.66 / 4.64 | 0.1772 | 0.1515 | 2.3582 | 4.0190 |
| B b = 1 | 2.9251 / 2.9201 / 2.9235 | 2.9564 / 2.9363 / 2.9484 | 5.19 / 5.05 | 4.69 / 4.69 | 0.1760 | 0.1507 | 2.3567 | 4.0037 |
| B b = 2 | 2.9205 / 2.9155 / 2.9190 | 2.9538 / 2.9335 / 2.9457 | 5.22 / 5.11 | 4.72 / 4.68 | 0.1745 | 0.1499 | 2.3550 | 3.9869 |
| B b = 4 | 2.9168 / 2.9116 / 2.9155 | 2.9521 / 2.9314 / 2.9437 | 5.16 / 5.07 | 4.68 / 4.75 | 0.1730 | 0.1491 | 2.3537 | 3.9723 |
| A 0.5 + B 1 | 2.9157 / 2.9104 / 2.9136 | 2.9538 / 2.9336 / 2.9457 | 5.29 / 5.29 | 4.71 / 4.72 | 0.1730 | 0.1491 | 2.3530 | 3.9561 |
| closing: A w = 0.5 | 2.9156 / 2.9105 / 2.9132 | 2.9580 / 2.9378 / 2.9499 | 5.10 / 5.26 | 4.64 / 4.59 | 0.1732 | 0.1491 | 2.3515 | 3.9495 |
| closing: A w = 1 | 2.9077 / 2.8996 / 2.9034 | 2.9558 / 2.9349 / 2.9472 | 5.33 / 5.38 | 4.70 / 4.60 | 0.1681 | 0.1464 | 2.3543 | 3.9165 |

Paired bootstrap **by player** (2,000 reps), difference in squared error vs off (negative = better), 95% CI:

| variant | next-1 uncal | next-1 WF | all rows uncal | all rows WF | rounds 2-5 only, WF | GK+DEF cs Brier, next-1 | MID+FWD goal SE, next-1 |
|---|---|---|---|---|---|---|---|
| A both w = 0.25 | -0.063 [-0.091, -0.038] | -0.064 [-0.091, -0.039] | -0.017 [-0.025, -0.011] | -0.017 [-0.025, -0.010] | +0.001 [-0.001, +0.002] | -0.0017 [-0.0024, -0.0010] | -0.013 [-0.029, -0.000] |
| **A both w = 0.5** | **-0.106 [-0.161, -0.056]** | **-0.109 [-0.162, -0.060]** | **-0.029 [-0.044, -0.015]** | **-0.029 [-0.044, -0.016]** | **+0.001 [-0.002, +0.004]** | **-0.0032 [-0.0046, -0.0017]** | **-0.021 [-0.051, +0.004]** |
| A both w = 0.75 | -0.129 [-0.212, -0.052] | -0.136 [-0.217, -0.062] | -0.036 [-0.058, -0.014] | -0.037 [-0.059, -0.016] | +0.001 [-0.004, +0.006] | -0.0044 [-0.0067, -0.0020] | -0.023 [-0.068, +0.014] |
| A both w = 1 | -0.132 [-0.245, -0.027] | -0.145 [-0.255, -0.044] | -0.036 [-0.067, -0.008] | -0.039 [-0.069, -0.012] | +0.001 [-0.007, +0.009] | -0.0054 [-0.0088, -0.0020] | -0.020 [-0.078, +0.029] |
| A attack w = 0.5 | -0.041 [-0.078, -0.006] | -0.047 [-0.084, -0.013] | -0.011 [-0.021, -0.002] | -0.011 [-0.021, -0.001] | +0.003 [+0.001, +0.005] | 0 | -0.021 [-0.051, +0.004] |
| A attack w = 1 | -0.048 [-0.120, +0.023] | -0.061 [-0.135, +0.006] | -0.013 [-0.033, +0.006] | -0.012 [-0.032, +0.007] | +0.007 [+0.003, +0.011] | 0 | -0.020 [-0.078, +0.029] |
| A defence w = 0.5 | -0.071 [-0.109, -0.037] | -0.068 [-0.105, -0.036] | -0.020 [-0.030, -0.010] | -0.020 [-0.030, -0.012] | -0.002 [-0.005, +0.001] | -0.0032 [-0.0046, -0.0017] | 0 |
| A defence w = 1 | -0.107 [-0.188, -0.033] | -0.106 [-0.183, -0.037] | -0.029 [-0.052, -0.009] | -0.033 [-0.054, -0.015] | -0.005 [-0.014, +0.003] | -0.0054 [-0.0088, -0.0020] | 0 |
| B b = 0.5 | -0.044 [-0.060, -0.029] | -0.043 [-0.059, -0.029] | -0.028 [-0.040, -0.018] | -0.028 [-0.039, -0.018] | -0.023 [-0.034, -0.012] | -0.0014 [-0.0019, -0.0008] | -0.007 [-0.013, -0.002] |
| B b = 1 | -0.069 [-0.097, -0.043] | -0.068 [-0.094, -0.044] | -0.044 [-0.063, -0.026] | -0.044 [-0.062, -0.027] | -0.035 [-0.053, -0.017] | -0.0022 [-0.0032, -0.0013] | -0.011 [-0.020, -0.003] |
| B b = 2 | -0.096 [-0.139, -0.057] | -0.094 [-0.134, -0.058] | -0.059 [-0.089, -0.031] | -0.060 [-0.086, -0.034] | -0.047 [-0.074, -0.020] | -0.0032 [-0.0046, -0.0017] | -0.015 [-0.029, -0.004] |
| B b = 4 | -0.117 [-0.176, -0.065] | -0.115 [-0.169, -0.065] | -0.069 [-0.111, -0.031] | -0.071 [-0.107, -0.036] | -0.055 [-0.091, -0.018] | -0.0041 [-0.0061, -0.0020] | -0.019 [-0.037, -0.004] |
| A 0.5 + B 1 | -0.124 [-0.189, -0.065] | -0.126 [-0.189, -0.069] | -0.059 [-0.088, -0.033] | -0.059 [-0.086, -0.034] | -0.034 [-0.052, -0.016] | -0.0041 [-0.0061, -0.0020] | -0.022 [-0.052, +0.002] |
| closing: A w = 0.5 | -0.124 [-0.184, -0.069] | -0.128 [-0.185, -0.075] | -0.034 [-0.050, -0.019] | -0.035 [-0.050, -0.020] | +0.001 [-0.001, +0.003] | -0.0040 [-0.0056, -0.0024] | -0.025 [-0.058, +0.003] |
| closing: A w = 1 | -0.171 [-0.288, -0.060] | -0.185 [-0.300, -0.080] | -0.047 [-0.079, -0.016] | -0.051 [-0.082, -0.022] | +0.000 [-0.006, +0.006] | -0.0072 [-0.0110, -0.0034] | -0.028 [-0.092, +0.026] |

(A changes rounds 2-5 only through the walk-forward calibration factors, which are refitted on rows that include
anchored next-round rows.) Time split (fit target rounds <= 6, test > 6, calibrated): off 2.8253, A 0.5 2.8258
(+0.003 [-0.010, +0.015] squared error), B 1 2.8225 (-0.016 [-0.033, +0.002]), A 0.5 + B 1 2.8234 (-0.011 [-0.035,
+0.015]). Bias (all rows, in-sample calibrated): off +0.032, A 0.5 +0.033, A 1 +0.039, B 1 +0.036, A 0.5 + B 1
+0.037; walk-forward +0.144 -> +0.143 for A 0.5.

Readings:
- **The odds help, at team and player level, out of sample.** The pre-match odds beat the model's next-round team
  goals on every measure, and blending them in improves next-round player RMSE uncalibrated, calibrated and
  walk-forward, with bootstrap intervals clear of zero, without hurting the other rows.
- **Defence benefits more than attack.** On next-round rows the defensive side alone (cs, gc, saves) gives about
  two thirds of the gain of both sides (-0.068 vs -0.109 at w = 0.5) and is significant at every weight; the
  attacking side alone gives -0.047 (significant at w = 0.5, not at w = 1), with the MID+FWD goal-component error
  improving only within noise. Both sides help, so both are anchored.
- **Weight:** the team-level and player-level gains rise up to w = 0.75-1 but the intervals widen and the
  calibrated bias and the time split drift up slightly from w = 0.75; w = 0.5 is the conservative choice.
- **B also works**, and is the only variant that improves rounds 2-5 ahead (-0.035 [-0.053, -0.017] at b = 1,
  growing with b). On top of A 0.5, B 1 adds -0.016 [-0.030, -0.004] on next-round rows and -0.035 [-0.053, -0.017]
  on rounds 2-5 (walk-forward, by player).
- **Closing odds are better still** (upper bound): A at w = 1 with closing prices gives -0.185 on next-round rows,
  vs -0.145 with the pre-match prices. Odds fetched closer to kickoff should help more.

**Decision: shipped on with A, both sides, w = 0.5** (`odds_weight = 0.5`, `odds_side = "both"`): the simplest variant
that is better out of sample on the next-round rows without being worse overall (the decision rule set before the
test). B was first implemented and tested but shipped off because it is the more complex change; the numbers above
show it adds a significant further gain (A 0.5 + B 1: all rows walk-forward 2.9457 vs 2.9508), and it was then
**switched on at b = 1** (`odds_ratings_weight = 1.0`). The shipped `fplxpts backtest` now gives 2.954 / 2.934 / 2.946
(uncalibrated / in-sample / walk-forward), time split 2.837 -> 2.823, top-12 4.71 / 4.87 / 4.72, matching the A 0.5 + B 1 row. Calibration factors were not refitted (bias unchanged).
`fplxpts backtest` now uses the historical odds by default (walk-forward RMSE 2.946 vs 2.956 without); `--no-odds`
reproduces the old lines and `--closing-odds` the upper bound.

Live projections use The Odds API (UK bookmakers, h2h and totals markets, each bookmaker de-vigged then averaged;
every half-goal totals line is converted to a Poisson total and averaged, quarter and whole lines are skipped).
Only the next gameweek's fixtures are anchored, matching what was tested. Limitations: 100 matches (GW1-10), one
season; the pre-match average is a proxy for "a few days before", and the live fetch happens whenever the daily
build runs (1-7 days before kickoff); the w grid was looked at in-sample on these rows (w = 0.5 is not the
best-scoring weight, which limits the selection effect). Re-test at 20+ gameweeks.

## Limitations

- Only 10 gameweeks. The shipped calibration factors are fitted on the whole window, so the in-sample line
  flatters them; the walk-forward line is the honest number (it includes uncalibrated cutoff 1). The shrinkage
  strength is only identified by the early cutoffs. Refit as the season grows.
- The backtest uses raw histories. Per-match penalty data is not available for past gameweeks, so
  penalties are stripped only in live projections.
- Last-season priors include penalty xG and cannot see club changes.
- Goal and assist calibration was tested for dependence on shot volume (bucketed ratios); it did not improve
  the time-split error, so flat per-position factors are used.
