# Backtest: method and findings

Data: 2026/27 season, GW1-10 (finished), via the public FPL API; bookmaker odds from Football-Data.co.uk. Re-run
with `fplxpts backtest --fit` (`--no-odds` for the model without odds). Past seasons 2022/23-2025/26 (community
archive): see [Past seasons](#past-seasons) and `fplxpts backtest --season all`; the recency half-lives and prior
weights are now chosen on them (see [Longer half-lives](#longer-half-lives-and-a-stronger-last-season-prior-shipped)).

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
| Model, uncalibrated | 2.965 | +0.26 | 0.286 |
| Model, calibrated (in-sample: shipped factors, fitted on these rows) | 2.945 | +0.02 | 0.288 |
| Model, calibrated walk-forward (out-of-sample) | 2.958 | +0.12 | 0.284 |
| Naive: season PPG | 3.332 | | |
| Naive: last-four form | 3.365 | | |

The three model rows are without bookmaker odds (`fplxpts backtest --no-odds`). With the shipped odds anchoring
(next round only, pre-match odds, blend `odds_weight = 0.5` plus ratings nudge `odds_ratings_weight = 1`, see the section
below) they are 2.955 / 2.935 / 2.948 (bias +0.26 / +0.03 / +0.12, top-12 4.74 / 4.68 / 4.71), time split 2.843 -> 2.830.
(Before `prior_lambda` went back from 0.3 to 0.15 and the factors were refitted, see "prior_lambda kept at 0.15" below:
without odds 2.966 / 2.946 / 2.958, time split 2.850 -> 2.836; with odds 2.956 / 2.936 / 2.949, top-12 4.53 / 4.61 /
4.50, 2.846 -> 2.833. Before the longer half-lives and the 0.3 prior, see that section below: without odds 2.963 / 2.943 /
2.955, time split 2.840 -> 2.826; with odds 2.953 / 2.933 / 2.945, top-12 4.65 / 4.85 / 4.64, 2.837 -> 2.824.)
(Before save points were modelled as whole threes, see "Save points" below: 2.954 / 2.934 / 2.946, top-12 4.71 / 4.87 / 4.72, 2.837 -> 2.823;
the feature-test sections further down were run before that change and quote the older numbers.)
(With the blend alone, before the nudge was switched on: 2.959 / 2.939 / 2.951, top-12 4.68 / 4.68 / 4.58, 2.840 -> 2.826.)

Top-12 picks (average actual points of the 12 highest-projected players per cutoff and round), without odds:
uncalibrated 4.69, in-sample calibrated 4.58, walk-forward 4.58.

Time split (fit rounds <= 6, test rounds >= 7), without odds: RMSE 2.847 -> 2.833, bias +0.227 -> -0.006.

The walk-forward bias (+0.12) is much higher than in-sample because the first cutoffs have no or little data to fit
on: cutoff 1 is uncalibrated (bias +0.47 on its 660 rows), cutoffs 2-3 are mostly shrunk to 1. From cutoff 4 on
(6,212 rows) walk-forward calibration gives RMSE 2.820 vs 2.830 uncalibrated and bias +0.02 vs +0.20.
(The k comparison and the sections below it were run with earlier model versions and quote their numbers.)

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

## Hyper-parameter search (27 settings) (superseded)

**Superseded** for the half-lives and prior weights by the past-season study (see "Past seasons", c(iii), and
"Longer half-lives and a stronger last-season prior" and "prior_lambda kept at 0.15"): `form_halflife` is now 8,
`team_halflife` 8, `prior_min` 300; `prior_lambda` stays at 0.15. The original ten-week search, kept for the record:

Form half-life {season-long, 4, 6 games} x last-season prior weight {0, 0.15, 0.3} x prior pseudo-minutes
{180, 270, 450}. Best: half-life 4, prior weight 0.15, prior minutes 450 (RMSE 2.9622 vs 2.9703 for
season-long with no prior). The paired squared-error difference is -0.048 +/- 0.033 (bootstrap by player),
so the gain is consistent in direction but **not statistically significant**. The last-season prior in
particular adds very little; it is kept small as a stabiliser. (Superseded: over whole past seasons the last-season
prior helps significantly in every season that has one, and a weight of 0.3 is now shipped.)

## What the backtest found (calibration factors)

Shipped (shrunk, k = 160) factors, with the raw ratio in brackets (refitted after the longer half-lives, odds-on
rows):

| Position | Component | Factor | Reading |
|---|---|---|---|
| DEF | goal | 0.58 (0.51) | defender goal threat over-projected ~2x |
| MID | goal | 0.81 (0.79) | mid xG converted ~20% worse than projected |
| FWD | goal | 0.85 (0.83) | |
| FWD | assist | 1.51 (2.22) | forward assists under-projected (small sample: 114 expected points) |
| DEF | cs / gc | 1.09 / 0.78 (1.10 / 0.75) | clean sheets more likely than Poisson-on-xG says (not in past seasons) |
| MID | cs | 1.21 (1.26) | |
| GK | sav | 0.96 (0.94) | nearly unbiased since save points are whole threes (was 0.67 with saves / 3) |
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

## Save points as whole threes (fix, shipped)

FPL gives a goalkeeper one point per three *whole* saves. The model used `saves / 3`, which credits a third of a
point for every save; the past-season study showed the consequence, a GK saves calibration factor of 0.57-0.67 in
every season. The component is now `E[floor(k / 3)]` for `k ~ Poisson(expected saves)` (`points.save_points`, the
same form as the goals-conceded penalty). Three expected saves are worth 0.67 points, not 1.0.

Refitted with the shipped method, the GK saves factor moves from 0.668 to 0.959, i.e. the component is now nearly
unbiased on its own; only that factor was changed. Effect (walk-forward RMSE before -> after; uncalibrated bias):

| Season | Uncalibrated RMSE | Walk-forward RMSE | Uncalibrated bias |
|---|---|---|---|
| 2026/27 GW1-10 | 2.954 -> 2.953 | 2.946 -> 2.945 | +0.296 -> +0.269 |
| 2025/26 | 2.769 -> 2.764 | 2.748 -> 2.748 | +0.184 -> +0.165 |
| 2024/25 | 2.588 -> 2.582 | 2.564 -> 2.564 | +0.197 -> +0.177 |
| 2023/24 | 2.692 -> 2.685 | 2.662 -> 2.661 | +0.184 -> +0.165 |
| 2022/23 (GW16+) | 2.692 -> 2.687 | 2.672 -> 2.671 | +0.205 -> +0.185 |

The uncalibrated model improves in every season; once calibrated the gain is at most 0.001, because the old factor
was already absorbing the error on average. What changes is the shape: the points now curve upwards with the expected save count, so a keeper expected to make
two saves gets fewer save points than before (0.33 vs 0.45 after calibration) and one expected to make four or more
gets slightly more (0.96 vs 0.89). In the GW11-15 top 10, most keepers at strong teams drop 0.3-0.6 and Tzolakis
(HUL) rises 0.4. The expected-bonus term still uses the raw expected save count, and GK
bonus remains over-projected (roadmap). The "Past seasons" tables below were produced before this fix; its effect
on them is within 0.001 walk-forward RMSE.

## Longer half-lives and a stronger last-season prior (half-lives and prior_min shipped; the stronger prior reverted)

The past-season study below (c(iii)) found that every past season prefers longer recency windows and a stronger
last-season prior than the values chosen on ten weeks. The owner adopted its recommended combination: `form_halflife`
4 -> 8, `team_halflife` 3 -> 8, `prior_min` 450 -> 300, `prior_lambda` 0.15 -> 0.3. **Of these, `prior_lambda` was
later put back to 0.15** (see "prior_lambda kept at 0.15" below); the half-lives and `prior_min` are shipped. The
table and numbers in this section are for the four-value combination as first shipped. Every calibration factor was
refitted with the shipped method (`fplxpts backtest --fit`, k = 160, rows with the historical odds on, as the command
runs; the factors before this were fitted on odds-off rows except GK saves). Re-run after the saves fix (fresh rows,
walk-forward calibration, odds on; dMSE = squared error new minus old, 95% CI from a paired bootstrap by player,
2,000 reps):

| season | n | uncalibrated RMSE old -> new | walk-forward RMSE old -> new | WF bias old -> new | top-12 WF old -> new | WF minus PPG old -> new | dMSE WF new - old [CI] |
|---|---|---|---|---|---|---|---|
| 2026/27 GW1-10 | 9,267 | 2.953 -> 2.956 | 2.945 -> 2.949 | +0.124 -> +0.116 | 4.64 -> 4.50 | -0.387 -> -0.384 | +0.020 [-0.012, +0.052] |
| 2025/26 | 69,197 | 2.764 -> 2.764 | 2.748 -> 2.745 | +0.005 -> -0.000 | 4.58 -> 4.62 | -0.080 -> -0.082 | -0.013 [-0.027, +0.000] |
| 2024/25 | 70,128 | 2.582 -> 2.575 | 2.564 -> 2.557 | -0.034 -> -0.043 | 5.36 -> 5.37 | -0.090 -> -0.096 | -0.033 [-0.054, -0.016] |
| 2023/24 | 70,664 | 2.685 -> 2.675 | 2.661 -> 2.653 | -0.042 -> -0.044 | 5.13 -> 5.30 | -0.090 -> -0.097 | -0.042 [-0.060, -0.024] |
| 2022/23 (GW16+) | 39,314 | 2.687 -> 2.684 | 2.671 -> 2.667 | +0.003 -> +0.003 | 5.33 -> 5.44 | -0.120 -> -0.124 | -0.020 [-0.036, -0.006] |

Without odds the picture is the same (dMSE +0.018 [-0.014, +0.052] on 2026/27; -0.023, -0.038, -0.055, -0.028 on
2025/26 .. 2022/23, all significant). By phase (odds on): on 2026/27 cutoffs 1-5 +0.007 [-0.031, +0.044] and
cutoffs 6-10 +0.042 [+0.003, +0.084]; in past seasons the gain is largest from GW11 on (e.g. GW20-29 -0.028 to
-0.043, significant in all four), mixed at cutoffs 1-5 (2025/26 +0.035 [-0.008, +0.078], 2023/24 -0.080 [-0.129,
-0.035]).

Current-season backtest lines (shipped factors refitted): without odds 2.963 / 2.943 / 2.955 -> 2.966 / 2.946 /
2.958 (uncalibrated / in-sample / walk-forward), time split 2.840 -> 2.826 became 2.850 -> 2.836; with odds 2.953 /
2.933 / 2.945 -> 2.956 / 2.936 / 2.949, top-12 4.65 / 4.85 / 4.64 -> 4.53 / 4.61 / 4.50. Past seasons, shipped
(2026/27-fitted) factors applied out of sample: 2.745 -> 2.743, 2.570 -> 2.562, 2.672 -> 2.663, 2.672 -> 2.668.

Reading: this is the study's result reproduced after the saves fix: better in all four past seasons (significant in
three, borderline in 2025/26), slightly worse on the ten weeks of 2026/27 (not significant overall, significant at
cutoffs 6-10), and fewer top-12 points on 2026/27 (-0.15 per pick). Note that the four past seasons now both chose
these four values and report them, so their improvement is in sample for this choice. Re-test on 2026/27 at GW20.
Effect on GW11-15 projections: attackers with a strong last season or a cold recent run rise (Haaland +1.8,
Mbeumo +1.8, B.Fernandes +1.6, Isak +1.5, Palmer +1.5), keepers and defenders of teams whose recent defensive
record was better than their season average fall (Verbruggen -1.2, Kinsky -1.0).

### prior_lambda kept at 0.15

The owner felt that last season was now weighted too heavily, and an isolated sweep of `prior_lambda` (everything else
as shipped: half-lives 8 and 8, `prior_min` 300, odds on, walk-forward calibration, uncalibrated rows refitted at each
cutoff; script kept outside the repo) confirmed that 0.3 is not better than 0.15. `prior_lambda` is back at 0.15; the
two half-lives and `prior_min` stay at their new values, and every calibration factor was refitted
(`fplxpts backtest --fit`).

Walk-forward RMSE by `prior_lambda`:

| season | n | 0 | 0.075 | 0.15 | 0.3 | 0.45 | squared error 0.15 minus 0.3 [95% CI by player], all cutoffs | cutoffs 1-5 | cutoffs 6-10 |
|---|---|---|---|---|---|---|---|---|---|
| 2026/27 GW1-10 | 9,267 | 2.9516 | 2.9484 | 2.9478 | 2.9485 | 2.9496 | -0.0042 [-0.0198, +0.0104] | +0.004 [-0.014, +0.022] (n 5,915) | -0.019 [-0.040, +0.000] (n 3,352) |
| 2025/26 | 69,197 | 2.7476 | 2.7458 | 2.7454 | 2.7454 | 2.7458 | -0.0004 [-0.0079, +0.0058] | -0.043 [-0.072, -0.020] (n 6,245) | -0.001 [-0.017, +0.012] (n 8,980) |
| 2024/25 | 70,128 | 2.5616 | 2.5590 | 2.5579 | 2.5574 | 2.5574 | +0.0029 [-0.0030, +0.0090] | +0.013 [-0.032, +0.063] (n 6,095) | +0.006 [-0.010, +0.026] (n 8,761) |
| 2023/24 | 70,664 | 2.6563 | 2.6547 | 2.6539 | 2.6533 | 2.6533 | +0.0032 [-0.0020, +0.0081] | +0.023 [-0.002, +0.052] (n 6,043) | +0.002 [-0.009, +0.013] (n 8,853) |

(2022/23 has no prior.) Negative favours 0.15. The reasons:

1. **No evidence that 0.3 is better.** No season separates 0.15 from 0.3 overall (all four intervals contain zero,
   differences of at most 0.004 in squared error, under 0.001 in RMSE). 0.15 is significantly better at cutoffs 1-5 of
   2025/26 and borderline better at cutoffs 6-10 of 2026/27, the two places where a heavy prior could hurt (players who
   changed role or club, and the current season); 0.3-0.45 are marginally better only in the other seasons' early
   weeks, within noise. Removing the prior altogether (0) is significantly worse in 2024/25 and 2023/24, so the prior
   itself stays.
2. **Penalty xG is double-counted.** Last season's xG still includes penalties (they are not stripped from the prior as
   they are from the current-season history), while each club's primary taker also gets the flat `pen_share_xg`. A
   heavier prior counts a taker's penalties twice with a bigger weight. Stripping them from last season's rates is an
   open item (docs/ROADMAP.md, P1 item 7); a stronger prior can be re-tested once that is done.

Effect of the revert on the current-season backtest (calibration refitted): without odds 2.966 / 2.946 / 2.958 ->
2.965 / 2.945 / 2.958 (uncalibrated / in-sample / walk-forward), top-12 4.53 / 4.50 / 4.48 -> 4.69 / 4.58 / 4.58, time
split 2.850 -> 2.836 became 2.847 -> 2.833; with odds 2.956 / 2.936 / 2.949 -> 2.955 / 2.935 / 2.948, top-12 4.53 / 4.61 /
4.50 -> 4.74 / 4.68 / 4.71, time split 2.846 -> 2.833 became 2.843 -> 2.830. Past seasons, walk-forward (odds on):
2.745 / 2.557 / 2.653 / 2.667 -> 2.745 / 2.558 / 2.654 / 2.667 (2025/26 .. 2022/23); top-12 4.62 / 5.37 / 5.30 / 5.44 ->
4.57 / 5.37 / 5.27 / 5.44.

### Calibration shrunk towards last season's factors (previewed, not shipped)

Option, off by default: `fit_calibration` / `walk_forward_calibration(..., prior=...)` shrink each factor towards a
prior factor instead of 1.0, `(sum actual + k * prior) / (sum predicted + k)` (k pseudo-points of "actual = prior x
predicted", sign-matched for gc/yc; a cell missing from the prior counts as 1.0, a cell with nothing predicted gets
the prior). `fplxpts backtest --prior-season 2025-26` (or `previous`) fits the prior on that past season's full
season with the current settings (the same factors `fplxpts backtest --season 2025-26 --fit` prints) and applies it
to the walk-forward line and `--fit`. Walk-forward, odds on, settings after the half-life change, the prior season
fitted in full (k = 160 towards 1); dMSE = prior-centred minus shipped (towards 1), both k = 160, by player:

| season | cutoffs | RMSE towards 1 | RMSE towards prev | bias towards 1 | bias towards prev | dMSE [95% CI] |
|---|---|---|---|---|---|---|
| 2026/27 (prior 2025/26) | all | 2.9485 | 2.9447 | +0.116 | +0.042 | -0.023 [-0.058, +0.014] |
| | 1-5 | 3.0605 | 3.0539 | +0.227 | +0.120 | -0.041 [-0.093, +0.012] |
| | 6-10 | 2.7397 | 2.7413 | -0.080 | -0.095 | +0.009 [-0.007, +0.026] |
| 2025/26 (prior 2024/25) | all | 2.7454 | 2.7432 | -0.000 | -0.014 | -0.012 [-0.018, -0.006] |
| | 1-5 | 3.0167 | 2.9961 | +0.299 | +0.183 | -0.124 [-0.190, -0.057] |
| | 6-10 / 11-19 / 20+ | | | | | -0.002 / -0.002 / -0.000 (all n.s.) |
| 2024/25 (prior 2023/24) | all | 2.5574 | 2.5563 | -0.043 | -0.051 | -0.006 [-0.012, +0.000] |
| | 1-5 | 2.8734 | 2.8617 | +0.239 | +0.155 | -0.067 [-0.125, -0.011] |
| | 6-10 / 11-19 / 20+ | | | | | -0.006 / -0.001 / +0.002 [+0.001, +0.004] |
| 2023/24 (prior 2022/23 GW16+) | all | 2.6533 | 2.6518 | -0.044 | -0.056 | -0.008 [-0.014, -0.003] |
| | 1-5 | 2.9102 | 2.8990 | +0.281 | +0.170 | -0.065 [-0.121, -0.009] |
| | 6-10 / 11-19 / 20+ | | | | | -0.012 [-0.022, -0.003] / -0.004 [-0.008, -0.001] / -0.000 |

k for the prior-centred version (dMSE vs shipped, all cutoffs; 2026/27, 2025/26, 2024/25, 2023/24): k = 40 -0.010,
-0.006, -0.001, -0.006; k = 160 -0.023, -0.012, -0.006, -0.008; k = 640 -0.022, -0.018, -0.010, -0.011; k = 2560
-0.019, -0.024, -0.011, -0.010. The past seasons keep improving slowly up to k = 1280-2560 (they are full seasons
whose factors are stable year to year); 2026/27 is flat from 160 to 640. Top-12 picks move by -0.09 (2026/27),
-0.05, +0.02, +0.03.

Reading: the study's result holds with the new settings: better overall in all four seasons (significant in two,
borderline in 2024/25, not significant on the ten weeks of 2026/27), almost all of it at cutoffs 1-5 where it removes
about 40% of the season-start bias; from GW11 on the two are the same. k = 640 would be the pick if adopted (most
of the gain of larger k on past seasons, flat on 2026/27, still lets ten weeks move a large cell); the preview
uses the code's k = 160. The factors it would ship today (2026/27 GW1-10 shrunk towards 2025/26) differ from the
shipped ones mainly in the small cells: GK bonus 0.908 -> 0.760, FWD assist 1.505 -> 1.992, FWD dc 0.716 -> 0.408,
GK yc 0.959 -> 0.885; the large cells (clean sheets, goals conceded) barely move at k = 160, because ten weeks
already carry hundreds of expected points there. Effect on GW11-15 top 10s: goalkeepers -0.4 to -0.9 (GK bonus),
defenders -0.1 to -0.2, midfielders and forwards within +-0.25; no entrants or leavers.

## Past seasons

Every hyper-parameter and design choice above was made on ten gameweeks of one season (the recency half-lives and
prior weights have since been changed on this section's evidence; **the tables in this section were produced with
the earlier values**, `form_halflife` 4, `team_halflife` 3, `prior_min` 450, `prior_lambda` 0.15, and before the
saves fix). This section replays four earlier seasons with the then-shipped hyper-parameters **frozen**, each season treated as its own world: its own teams
(promoted and relegated sides), players, previous-season priors, scoring rules and odds file. Re-run with
`fplxpts backtest --season all` (or `--season 2024-25`, repeatable; about 45 s for all four).

### Data and what differs from the live API

Source: the community archive [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
(MIT licence; the data belongs to the Premier League / FPL; cited and linked as the repository asks), files
`gws/merged_gw.csv`, `fixtures.csv`, `teams.csv`, `players_raw.csv` per season, each downloaded once into `.cache/`
(`archive.py`). Odds: that season's Football-Data.co.uk `E0.csv` (`2223` .. `2526`; all have the pre-match `Avg*`
columns, 380 fixtures matched each season), same loader as the current season. `archive.load_archive_season` builds
the same `Season` structure as the live loader, so `build_players`, `team_state` and `backtest.evaluate` run on it.
Handled:

- **Ids are per season.** Element and team ids are re-keyed every season; players are linked across seasons by
  the stable `code` (for priors), teams by short name.
- **Positions** are fixed within a season (no player changes position in any archive season; all agree with
  `players_raw.csv`). Between seasons 9-12 players a year change position; the last-season prior is per-minute
  xG/xA and does not depend on position, so it carries over and the player is shrunk towards his new position's pool.
- **Mid-season transfers.** Live match rows have no team; the model used `elements[pid]["team"]` (the current club)
  for every row, which is right for the live season (no transfers between PL clubs so far) but would put a player
  who moved in January at his end-of-season club in his old matches (even "against himself"). Archive rows get a
  `team` field from the fixture and `was_home`; `players.current_team` uses the club of the latest row before the
  cutoff and `backtest.at_club` the club of the predicted match. Both fall back to the old behaviour when rows have
  no team, so live output is unchanged. 11-27 players a season moved; the effect on their rows is within noise
  (dMSE end-of-season club minus per-match club: -0.006 [-0.022, +0.008], +0.003 [-0.002, +0.008], +0.007 [+0.001,
  +0.014], -0.010 [-0.042, +0.019] for 2025/26 .. 2022/23), but the per-match club is the correct input.
- **Double and blank gameweeks.** A player gets one row per match, so a double gameweek is two rows in one round
  (two predictions, each against its own opponent, each scored against its own match); a blank is no row. The
  round is the fixture's `event` (the round a postponed match was actually played in). `top_k_actual` now sums a
  player's matches within a round before ranking, and the live `Projector` now adds both fixtures of a double
  gameweek (it used to keep only the last one; the live season has had no double gameweek, so its output is
  unchanged). 2022/23 GW7 had no matches (postponed after the Queen's death); cutoffs are only taken at rounds with
  matches (`backtest.played_rounds`), so that round does not repeat cutoff 6.
- **Priors.** `history_past` is rebuilt from the archive's earlier seasons (minutes, xG, xA summed by `code`, FPL
  season names "2024/25"), and `prior_seasons` is shifted with the season (`archive.shift_prior_seasons`): the
  shipped `{"2025/26": 1, "2024/25": 0.5}` (last season 1, the one before 0.5) becomes `{"2023/24": 1, "2022/23":
  0.5}` for 2024/25. The shipped default for the live season is unchanged.
- **Expected goals only from 2022/23 GW16.** FPL published xG from GW16 of 2022/23; earlier rows in the archive have
  zeros. Rounds before the first round with xG are dropped (`archive.xg_rounds_only`), so **2022/23 starts at GW16
  (cutoffs 16-37) and has no prior** (2021/22 has no xG), 2023/24's prior comes from 2022/23 GW16-38 only (no
  second season), and 2024/25's second prior season is that partial one. Only 2025/26 has the full two-season prior
  the live model has.
- **Scoring rules.** Defensive-contribution points exist only from 2025/26 (`archive.scoring_rules`): earlier seasons
  get `defensive_contribution = 0`, so projected and actual dc are both zero (and `dc_opp_k` has no effect). A
  goalkeeper goal was 6 points before 2025/26 (10 since); there were no goalkeeper goals in these seasons. Check:
  for every row of all four seasons `total_points` equals the model's actual components plus penalties saved (+5),
  missed (-2), red cards (-3) and own goals (-2) exactly (0 mismatches in 113,260 rows), so no other scoring change
  affects the components (bonus is taken as awarded).
- **Data glitches.** 2025/26 has 10 exact duplicate (player, fixture) rows (dropped); 2024/25 "assistant manager"
  rows (position `AM`) are dropped.
- **Not handled (same limitations as the current backtest):** no historical availability flags (every player is
  available; injured players are projected and score 0), penalties are not stripped, and the backtest knows which
  players will appear for which club in a future round (a row exists only while a player is at a PL club).

### What is and is not comparable

RMSE **levels** differ between seasons because points are more or less spread (mean points per player-game fall
from ~2.6 at the start of a season to ~1.8 at the end, and differ by season); compare the margin over the
baselines and the deltas, not the levels. The current season's numbers cover cutoffs 1-9 only, where every season's
errors are largest (compare with the cutoffs 1-5 / 6-10 rows of the phase table). 2022/23 is truncated (GW16+, no
prior). Defensive contributions exist only in 2025/26 and 2026/27. Each season has ~70,000 player-games but only
~600 players and one set of 20 teams: intervals are from paired bootstraps **by player** (2,000 reps) and do not
cover season-to-season variation, which is what the four seasons are for. Many comparisons are made below; isolated
"significant" cells should be read with that in mind.

### a. Headline: walk-forward over each whole season

Cutoffs GW1-37 (2022/23: 16-37), next 5 rounds; calibration refitted inside the season at each cutoff
(`walk_forward_metrics`), so every model number is out of sample; shipped hyper-parameters.

| season | player-games | RMSE uncal, odds off / on | RMSE WF, odds off / on | bias WF (on) | corr WF (on) | top-12 WF (on) / by PPG | PPG | form-4 | WF - PPG, odds off / on | dMSE WF (on) vs PPG [95% CI] |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026/27 GW1-10 (current) | 9,267 | 2.964 / 2.954 | 2.956 / 2.946 | +0.141 | 0.294 | 4.72 / 4.04 | 3.332 | 3.365 | -0.376 / -0.387 | -2.43 [-3.09, -1.79] |
| 2025/26 | 69,197 | 2.775 / 2.769 | 2.752 / 2.748 | +0.008 | 0.336 | 4.57 / 4.33 | 2.828 | 2.999 | -0.075 / -0.079 | -0.44 [-0.59, -0.30] |
| 2024/25 | 70,128 | 2.593 / 2.588 | 2.566 / 2.564 | -0.030 | 0.390 | 5.34 / 4.67 | 2.654 | 2.806 | -0.088 / -0.089 | -0.47 [-0.61, -0.34] |
| 2023/24 | 70,664 | 2.696 / 2.692 | 2.667 / 2.662 | -0.038 | 0.362 | 5.12 / 4.77 | 2.751 | 2.893 | -0.084 / -0.089 | -0.48 [-0.63, -0.34] |
| 2022/23 (GW16+) | 39,314 | 2.695 / 2.692 | 2.676 / 2.672 | +0.008 | 0.322 | 5.31 / 5.83 | 2.791 | 2.906 | -0.116 / -0.119 | -0.65 [-0.85, -0.46] |

PPG (season points per game so far) is the better baseline in every season. The model beats it in every season,
with intervals far from zero, and its weekly correlation with actual points is 0.32-0.39 over a whole season (0.29
on the first ten weeks). Top-12 picks beat PPG-ranked picks in every full season (+0.24 to +0.67 points per pick)
but not in truncated 2022/23 (5.31 vs 5.83; no prior, data only from GW16). Calibration fitted within the season
removes the uncalibrated +0.14 to +0.20 bias.

Odds on minus odds off (WF squared error, paired bootstrap by player; negative = odds help):

| season | all rows | next round | rounds 2-5 ahead |
|---|---|---|---|
| 2026/27 | -0.059 [-0.086, -0.034] | -0.126 [-0.189, -0.069] | -0.034 [-0.052, -0.016] |
| 2025/26 | -0.022 [-0.028, -0.016] | -0.048 [-0.065, -0.032] | -0.015 [-0.020, -0.011] |
| 2024/25 | -0.009 [-0.015, -0.003] | -0.025 [-0.045, -0.006] | -0.004 [-0.009, +0.001] |
| 2023/24 | -0.027 [-0.034, -0.020] | -0.065 [-0.084, -0.045] | -0.017 [-0.022, -0.012] |
| 2022/23 | -0.020 [-0.029, -0.012] | -0.039 [-0.063, -0.014] | -0.015 [-0.021, -0.009] |

The odds help in every season, but by only 15-45% of what the first ten weeks of 2026/27 showed (the gain is
largest where the model knows least).

### b. Within a season

Odds on, shipped; WF = walk-forward calibrated; dMSE against the better baseline (always PPG except where noted).

| season | cutoffs | n | RMSE WF | bias WF | corr WF | PPG | form-4 | WF - PPG | dMSE vs PPG [CI] | top-12 WF / PPG | mean pts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026/27 | 1-5 | 5,915 | 3.060 | +0.26 | 0.250 | 3.541 | 3.550 | -0.481 | -3.18 [-4.08, -2.29] | 4.57 / 3.90 | 2.79 |
| 2026/27 | 6-10 | 3,352 | 2.732 | -0.07 | 0.362 | 2.927 | 3.012 | -0.195 | -1.11 [-1.58, -0.66] | 5.09 / 4.38 | 2.43 |
| 2025/26 | 1-5 | 6,245 | 3.018 | +0.31 | 0.235 | 3.381 | 3.390 | -0.363 | -2.32 [-3.16, -1.62] | 4.51 / 4.23 | 2.63 |
| 2025/26 | 6-10 | 8,980 | 2.898 | -0.13 | 0.317 | 3.029 | 3.134 | -0.131 | -0.78 [-1.13, -0.45] | 4.39 / 3.43 | 2.38 |
| 2025/26 | 11-19 | 18,050 | 2.819 | -0.03 | 0.306 | 2.882 | 3.104 | -0.063 | -0.36 [-0.58, -0.15] | 3.86 / 3.97 | 2.16 |
| 2025/26 | 20-29 | 22,076 | 2.653 | +0.02 | 0.349 | 2.665 | 2.867 | -0.012 | -0.07 [-0.28, +0.15] | 4.87 / 4.63 | 1.97 |
| 2025/26 | 30-37 | 13,846 | 2.572 | +0.00 | 0.382 | 2.588 | 2.781 | -0.017 | -0.09 [-0.32, +0.12] | 5.32 / 5.18 | 1.90 |
| 2024/25 | 1-5 | 6,095 | 2.883 | +0.26 | 0.303 | 3.259 | 3.275 | -0.376 | -2.31 [-3.04, -1.64] | 5.07 / 4.65 | 2.39 |
| 2024/25 | 6-10 | 8,761 | 2.678 | -0.11 | 0.351 | 2.788 | 2.916 | -0.110 | -0.60 [-0.97, -0.20] | 5.10 / 4.72 | 2.10 |
| 2024/25 | 11-19 | 18,032 | 2.660 | -0.08 | 0.388 | 2.706 | 2.865 | -0.046 | -0.25 [-0.46, -0.03] | 5.77 / 5.04 | 1.97 |
| 2024/25 | 20-29 | 22,760 | 2.467 | -0.02 | 0.400 | 2.486 | 2.704 | -0.019 | -0.10 [-0.26, +0.05] | 5.34 / 4.68 | 1.75 |
| 2024/25 | 30-37 | 14,480 | 2.372 | -0.05 | 0.419 | 2.469 | 2.598 | -0.096 | -0.47 [-0.70, -0.25] | 5.10 / 4.07 | 1.69 |
| 2023/24 | 1-5 | 6,043 | 2.928 | +0.32 | 0.320 | 3.295 | 3.300 | -0.366 | -2.28 [-3.17, -1.47] | 4.96 / 4.21 | 2.40 |
| 2023/24 | 6-10 | 8,853 | 2.759 | -0.06 | 0.302 | 2.852 | 2.971 | -0.093 | -0.52 [-0.79, -0.23] | 4.57 / 4.83 | 2.05 |
| 2023/24 | 11-19 | 18,109 | 2.683 | -0.08 | 0.312 | 2.769 | 2.922 | -0.086 | -0.47 [-0.70, -0.24] | 4.13 / 3.82 | 1.89 |
| 2023/24 | 20-29 | 21,735 | 2.577 | -0.05 | 0.375 | 2.604 | 2.821 | -0.027 | -0.14 [-0.33, +0.03] | 5.36 / 4.93 | 1.74 |
| 2023/24 | 30-37 | 15,924 | 2.590 | -0.09 | 0.424 | 2.640 | 2.745 | -0.050 | -0.26 [-0.49, -0.04] | 6.78 / 6.37 | 1.74 |
| 2022/23 | 16-19 | 5,057 | 2.887 | +0.24 | 0.232 | 3.305 | 3.308 | -0.418 | -2.59 [-3.68, -1.67] | 5.04 / 5.31 | 2.52 |
| 2022/23 | 20-29 | 20,209 | 2.656 | +0.00 | 0.302 | 2.732 | 2.861 | -0.076 | -0.41 [-0.62, -0.20] | 5.35 / 6.08 | 1.97 |
| 2022/23 | 30-37 | 14,048 | 2.613 | -0.07 | 0.358 | 2.671 | 2.815 | -0.058 | -0.31 [-0.54, -0.09] | 5.41 / 5.75 | 1.85 |

Pooled over the three full past seasons:

| cutoffs | n | RMSE WF | PPG | form-4 | WF - PPG | WF / PPG |
|---|---|---|---|---|---|---|
| 1-5 | 18,383 | 2.944 | 3.312 | 3.322 | -0.368 | 0.889 |
| 6-10 | 26,594 | 2.781 | 2.892 | 3.009 | -0.111 | 0.961 |
| 11-19 | 54,191 | 2.722 | 2.787 | 2.966 | -0.065 | 0.977 |
| 20-29 | 66,571 | 2.565 | 2.585 | 2.797 | -0.019 | 0.992 |
| 30-37 | 44,250 | 2.515 | 2.569 | 2.709 | -0.054 | 0.979 |

Readings:
- **The first ten weeks are the easy case for beating the baselines, not representative of a season.** The margin
  over PPG is -0.37 RMSE at cutoffs 1-5 (PPG on a handful of games is very noisy), -0.11 at 6-10 and only -0.02 to
  -0.06 from GW11 on. The current season's GW1-10 margins (-0.48 / -0.20) are in line with past seasons' first ten
  weeks, so they say little about the rest of the season.
- **The point-estimate edge nearly vanishes in mid-season** (GW20-29: -0.01 to -0.03, interval includes zero in all
  three seasons), while the ranking edge does not: top-12 picks beat PPG picks in all three seasons there (+0.24,
  +0.66, +0.43 points per pick).
- **No end-of-season breakdown.** GW30-37 has the lowest RMSE and the highest correlation (0.38-0.42) of any phase,
  the margin over PPG widens again (significant in 2024/25 and 2023/24) and the bias stays small (-0.09 to +0.00).
  Rotation and dead rubbers do not visibly hurt the model more than the baselines (no availability flags in either).
- **Season-start bias.** The walk-forward bias is +0.26 to +0.32 at cutoffs 1-5 in every season (cutoff 1: +0.6 to
  +1.0), then slightly negative. Within-season calibration has nothing to fit on yet (see c(i)).

### c(i). Calibration factors across seasons

Factors fitted on all of each season's rows (odds on, k = 160), next to the shipped ones (2026/27 GW1-10).
"Unstable": range over the past seasons > 0.15; "outside": the shipped factor is more than 0.05 outside the
past-season range.

| pos | comp | shipped | 2025/26 | 2024/25 | 2023/24 | 2022/23 | flag |
|---|---|---|---|---|---|---|---|
| GK | app | 0.937 | 0.904 | 0.874 | 0.884 | 0.902 | |
| GK | cs | 1.135 | 0.862 | 0.818 | 0.766 | 0.961 | unstable, outside |
| GK | gc | 0.865 | 0.907 | 0.912 | 0.992 | 0.910 | |
| GK | bonus | 0.862 | 0.543 | 0.537 | 0.574 | 0.589 | outside |
| GK | sav | 0.668 | 0.611 | 0.565 | 0.629 | 0.589 | |
| GK | yc | 0.963 | 0.911 | 0.980 | 0.860 | 0.903 | |
| DEF | app | 0.852 | 0.907 | 0.895 | 0.896 | 0.869 | |
| DEF | goal | 0.567 | 0.760 | 0.767 | 0.888 | 0.695 | unstable, outside |
| DEF | assist | 0.972 | 1.185 | 1.011 | 1.112 | 0.845 | unstable |
| DEF | cs | 1.100 | 0.913 | 0.857 | 0.822 | 0.944 | outside |
| DEF | gc | 0.772 | 0.911 | 0.952 | 1.033 | 0.912 | outside |
| DEF | dc | 0.987 | 0.931 | - | - | - | (one season) |
| DEF | bonus | 0.927 | 0.840 | 0.890 | 0.830 | 0.824 | |
| DEF | yc | 0.999 | 0.934 | 0.868 | 0.858 | 0.895 | outside |
| MID | app | 0.885 | 0.927 | 0.933 | 0.930 | 0.918 | |
| MID | goal | 0.796 | 0.887 | 0.913 | 0.979 | 0.893 | outside |
| MID | assist | 1.037 | 1.211 | 1.211 | 1.289 | 1.298 | outside |
| MID | cs | 1.212 | 1.010 | 1.037 | 1.018 | 1.043 | outside |
| MID | dc | 0.989 | 1.095 | - | - | - | (one season) |
| MID | bonus | 0.835 | 0.967 | 0.891 | 0.967 | 0.920 | outside |
| MID | yc | 1.004 | 0.953 | 0.859 | 0.898 | 0.865 | outside |
| FWD | app | 0.938 | 0.955 | 0.929 | 0.920 | 0.923 | |
| FWD | goal | 0.846 | 0.898 | 0.895 | 0.895 | 0.911 | |
| FWD | assist | 1.502 | 1.882 | 1.730 | 1.927 | 1.774 | unstable, outside |
| FWD | dc | 0.716 | 0.554 | - | - | - | (one season) |
| FWD | bonus | 1.037 | 0.881 | 0.939 | 0.899 | 0.915 | outside |
| FWD | yc | 0.853 | 1.018 | 0.917 | 0.924 | 0.944 | |

Readings: most factors are **stable across past seasons** (range <= 0.1: appearance, goals for MID/FWD, saves, GK
bonus, MID assists/cs/bonus), which is what makes cross-season calibration work. But **many shipped factors sit
outside the range of every past season**, and in a consistent direction: 2026/27 GW1-10 had more clean sheets and
fewer goals conceded than the xG implied (cs > 1, gc < 1, where past seasons have cs < 1, gc ~ 0.9-1.0), fewer
defender and midfielder goals per xG, and fewer midfielder assists. Those look like ten-week luck in the outcomes,
not stable properties of the model. Stable across all seasons, i.e. real model biases: saves over-projected
(0.57-0.67; the saves component is `saves / 3`, but FPL scores `floor(saves / 3)`, which alone is about a third of
a point per match), GK bonus over-projected (0.54-0.59 past; it rides on the over-projected saves and clean sheets),
forward and midfielder assists under-projected (1.7-1.9 and 1.2-1.3), defender goals over-projected (0.7-0.9),
appearance points over-projected (0.87-0.96).

Which factors to apply (WF = refitted within the season at each cutoff; prev = fitted on all of season S-1 and
applied from GW1; WF->prev = walk-forward but shrunk towards the previous season's factors instead of towards 1,
k = 160; dMSE vs WF, by player):

| season | rows | none | WF | prev | shipped 2026/27 | WF->prev | none - WF | prev - WF | WF->prev - WF |
|---|---|---|---|---|---|---|---|---|---|
| 2026/27 | all | 2.954 | 2.946 | 2.943 | (in-sample) | 2.942 | +0.048 [-0.011, +0.107] | -0.015 [-0.075, +0.045] | -0.022 [-0.071, +0.027] |
| 2026/27 | cutoffs 1-5 | 3.069 | 3.060 | 3.054 | | 3.054 | +0.052 [+0.012, +0.091] | -0.039 [-0.123, +0.044] | -0.042 [-0.113, +0.029] |
| 2025/26 | all | 2.769 | 2.748 | 2.742 | 2.746 | 2.746 | +0.113 [+0.084, +0.141] | -0.037 [-0.052, -0.023] | -0.015 [-0.024, -0.006] |
| 2025/26 | cutoffs 1-5 | 3.026 | 3.018 | 2.982 | 2.996 | 2.991 | +0.050 [-0.006, +0.107] | -0.218 [-0.341, -0.095] | -0.162 [-0.255, -0.072] |
| 2024/25 | all | 2.588 | 2.564 | 2.562 | 2.570 | 2.562 | +0.123 [+0.081, +0.164] | -0.010 [-0.037, +0.012] | -0.009 [-0.017, -0.001] |
| 2024/25 | cutoffs 1-5 | 2.903 | 2.883 | 2.868 | 2.869 | 2.867 | +0.120 [+0.016, +0.223] | -0.082 [-0.208, +0.042] | -0.091 [-0.174, -0.017] |
| 2023/24 | all | 2.692 | 2.662 | 2.662 | 2.672 | 2.659 | +0.159 [+0.118, +0.200] | +0.000 [-0.013, +0.014] | -0.013 [-0.020, -0.006] |
| 2023/24 | cutoffs 1-5 | 2.948 | 2.928 | 2.910 | 2.910 | 2.911 | +0.117 [+0.015, +0.209] | -0.109 [-0.180, -0.040] | -0.100 [-0.170, -0.031] |

- **Calibration is clearly worth having over a full season** (none vs WF +0.11 to +0.16, significant in every past
  season; on 2026/27 GW1-10 it was not significant).
- **Last season's factors beat within-season calibration at the start of a season** (cutoffs 1-5: -0.08 to -0.22,
  significant in two of three seasons) and are as good afterwards.
  Walk-forward calibration shrunk towards last season's factors (instead of towards 1) is significantly better than
  the shipped walk-forward in all three seasons overall (-0.009 to -0.015) and at cutoffs 1-5 (-0.09 to -0.16), and
  points the same way on 2026/27 (-0.022, not significant). This is the most consistent calibration result.
- The shipped 2026/27 factors applied to past seasons beat no calibration and beat within-season walk-forward at
  cutoffs 1-5, but over the season they are worse than walk-forward in 2024/25 and 2023/24 (2.570 vs 2.564, 2.672 vs
  2.662) and about equal in 2025/26.

### c(ii). This week's changes, each switched off on each season

Base: shipped config with odds. dMSE = squared error with the feature **off** minus shipped, walk-forward
calibrated, 95% CI by player (positive = the feature helps); dRMSE in brackets. Pooled = the four past seasons,
resampling (season, player).

| feature switched off | 2026/27 GW1-10 (where it was chosen) | 2025/26 | 2024/25 | 2023/24 | 2022/23 | pooled past |
|---|---|---|---|---|---|---|
| opponent DC factor (`dc_opp_k` 40 -> 0) | +0.008 [+0.002, +0.016] (+0.0014) | -0.001 [-0.005, +0.003] (-0.0002) | n/a | n/a | n/a | -0.0011 [-0.0046, +0.0025] |
| strength of schedule (`team_sos_iters` 20 -> 0) | +0.009 [-0.008, +0.026] (+0.0015) | +0.002 [-0.004, +0.008] (+0.0004) | +0.012 [+0.005, +0.019] (+0.0024) | +0.007 [+0.000, +0.012] (+0.0012) | +0.023 [+0.012, +0.034] (+0.0043) | +0.0096 [+0.0060, +0.0131] |
| minutes skip injury absences (`absence_starts_before` 2 -> 0) | -0.002 [-0.028, +0.022] (-0.0003) | +0.047 [+0.021, +0.076] (+0.0086) | +0.008 [-0.015, +0.032] (+0.0015) | +0.019 [-0.014, +0.050] (+0.0036) | -0.010 [-0.043, +0.021] (-0.0019) | +0.0191 [+0.0041, +0.0340] |
| calibration shrinkage k 160 -> 20 | +0.025 [+0.004, +0.048] (+0.0043) | +0.001 [-0.004, +0.007] (+0.0003) | +0.003 [-0.004, +0.012] (+0.0006) | -0.005 [-0.011, +0.002] (-0.0009) | -0.002 [-0.011, +0.006] (-0.0005) | -0.0004 [-0.0037, +0.0032] |
| odds blend (`odds_weight` 0.5 -> 0) | +0.015 [+0.006, +0.026] (+0.0026) | +0.005 [+0.003, +0.007] (+0.0008) | +0.001 [-0.001, +0.004] (+0.0002) | +0.007 [+0.005, +0.010] (+0.0014) | +0.003 [-0.000, +0.006] (+0.0006) | +0.0042 [+0.0029, +0.0054] |
| odds ratings nudge (`odds_ratings_weight` 1 -> 0) | +0.030 [+0.015, +0.045] (+0.0051) | +0.014 [+0.010, +0.017] (+0.0025) | +0.003 [-0.001, +0.008] (+0.0007) | +0.014 [+0.010, +0.018] (+0.0026) | +0.013 [+0.008, +0.018] (+0.0024) | +0.0106 [+0.0085, +0.0127] |

Next-round rows only (where the blend acts): blend off +0.022 [+0.012, +0.032], +0.006 [-0.007, +0.019], +0.031
[+0.019, +0.042], +0.008 [-0.007, +0.023] (2025/26 .. 2022/23); nudge off +0.006, +0.001, +0.006, +0.008 (three of
four significant).

What held up and what did not:
- **Odds ratings nudge: holds up** (helps in all four seasons, significant in three, pooled clearly positive). The
  biggest of the week's gains, at a third to a half of its 2026/27 size.
- **Odds blend: holds up, smaller** (positive everywhere, significant in two of four and pooled).
- **Strength-of-schedule ratings: holds up** (positive in every season, significant in two of four, borderline in a
  third, and pooled),
  better supported on past seasons than on the ten weeks it was chosen on.
- **Minutes model skipping injury absences: holds up on balance** (pooled +0.019 [+0.004, +0.034], significant only
  in 2025/26, slightly negative in 2022/23 and 2026/27).
- **Calibration shrinkage k = 160 vs 20: no difference over a full season** (the shrinkage only matters while the
  training set is small); harmless, keep.
- **Opponent DC factor: does not hold up.** On the only other season with defensive contributions it does nothing
  (-0.001 [-0.005, +0.003], top-12 -0.03). This was the decision taken against the evidence of the component itself;
  the roadmap's switch-off condition is met on 2025/26, though not yet re-tested at 20+ weeks of 2026/27.

### c(iii). Hyper-parameter sensitivity

One parameter at a time on top of the shipped config (odds on), walk-forward RMSE; `*` = the dMSE vs shipped has a
95% CI excluding zero; shipped value in bold. Pooled = dMSE vs shipped over the four past seasons.

| parameter | value | 2026/27 GW1-10 | 2025/26 | 2024/25 | 2023/24 | 2022/23 | pooled past dMSE [CI] |
|---|---|---|---|---|---|---|---|
| form_halflife | 2 | 2.9461 | 2.7510* | 2.5685* | 2.6657* | 2.6750* | +0.0188 [+0.0142, +0.0240] |
| | 3 | 2.9458 | 2.7493* | 2.5657* | 2.6633* | 2.6730* | +0.0069 [+0.0049, +0.0090] |
| | **4** | **2.9457** | **2.7484** | **2.5641** | **2.6618** | **2.6719** | |
| | 6 | 2.9459 | 2.7474* | 2.5625* | 2.6601* | 2.6708* | -0.0072 [-0.0098, -0.0048] |
| | 8 | 2.9460 | 2.7470* | 2.5619* | 2.6592* | 2.6702* | -0.0107 [-0.0148, -0.0069] |
| | season-long | 2.9467 | 2.7465 | 2.5616 | 2.6568* | 2.6691 | -0.0165 [-0.0262, -0.0071] |
| team_halflife | 2 | 2.9452 | 2.7496* | 2.5661* | 2.6640* | 2.6732* | +0.0091 [+0.0074, +0.0108] |
| | **3** | **2.9457** | **2.7484** | **2.5641** | **2.6618** | **2.6719** | |
| | 5 | 2.9466 | 2.7474* | 2.5626* | 2.6600* | 2.6710* | -0.0072 [-0.0091, -0.0052] |
| | 8 | 2.9472 | 2.7469* | 2.5622* | 2.6592* | 2.6705* | -0.0101 [-0.0136, -0.0067] |
| | season-long | 2.9486* | 2.7465 | 2.5631 | 2.6586* | 2.6704 | -0.0104 [-0.0166, -0.0039] |
| team_shrink_k | 1 | 2.9490 | 2.7499* | 2.5654* | 2.6624 | 2.6766* | +0.0091 [+0.0059, +0.0123] |
| | 2 | 2.9461 | 2.7489* | 2.5643 | 2.6619 | 2.6738* | +0.0027 [+0.0014, +0.0040] |
| | **3** | **2.9457** | **2.7484** | **2.5641** | **2.6618** | **2.6719** | |
| | 5 | 2.9469 | 2.7480 | 2.5644 | 2.6621 | 2.6696* | -0.0017 [-0.0036, +0.0001] |
| | 8 | 2.9491 | 2.7480 | 2.5652 | 2.6627 | 2.6678* | -0.0010 [-0.0049, +0.0028] |
| prior_min | 200 | 2.9475 | 2.7493 | 2.5605* | 2.6584* | 2.6710 | -0.0098 [-0.0178, -0.0022] |
| | 300 | 2.9461 | 2.7485 | 2.5618* | 2.6596* | 2.6709 | -0.0072 [-0.0116, -0.0032] |
| | **450** | **2.9457** | **2.7484** | **2.5641** | **2.6618** | **2.6719** | |
| | 700 | 2.9466 | 2.7490 | 2.5677* | 2.6652* | 2.6741* | +0.0131 [+0.0083, +0.0184] |
| | 1000 | 2.9479 | 2.7501 | 2.5714* | 2.6684* | 2.6762* | +0.0267 [+0.0178, +0.0364] |
| prior_lambda | 0 | 2.9487 | 2.7511* | 2.5693* | 2.6647* | 2.6719 | +0.0159 [+0.0098, +0.0228] |
| | **0.15** | **2.9457** | **2.7484** | **2.5641** | **2.6618** | **2.6719** | |
| | 0.3 | 2.9462 | 2.7483 | 2.5628 | 2.6609 | 2.6719 | -0.0036 [-0.0071, +0.0001] |
| | 0.6 | 2.9480 | 2.7490 | 2.5623 | 2.6605 | 2.6719 | -0.0037 [-0.0111, +0.0040] |
| | 1 | 2.9498 | 2.7498 | 2.5626 | 2.6608 | 2.6719 | -0.0017 [-0.0118, +0.0089] |

(2022/23 has no prior, so prior_lambda does nothing there.) Joint check of the values the past seasons agree on
(not shipped): **combo** = form_halflife 8, team_halflife 8, prior_min 300, prior_lambda 0.3; combo_long = both
half-lives season-long, prior_min 300, prior_lambda 0.3.

| season | shipped WF RMSE | combo | dMSE combo [CI] | dTop-12 | combo_long | dMSE [CI] | dTop-12 |
|---|---|---|---|---|---|---|---|
| 2026/27 GW1-10 | 2.9457 | 2.9489 | +0.018 [-0.013, +0.051] | -0.22 | 2.9513 | +0.033 [-0.009, +0.077] | -0.25 |
| 2025/26 | 2.7484 | 2.7459 | -0.014 [-0.028, -0.001] | +0.04 | 2.7449 | -0.019 [-0.039, +0.000] | -0.10 |
| 2024/25 | 2.5641 | 2.5577 | -0.033 [-0.054, -0.017] | +0.02 | 2.5590 | -0.026 [-0.054, -0.002] | +0.01 |
| 2023/24 | 2.6618 | 2.6539 | -0.042 [-0.060, -0.024] | +0.17 | 2.6513 | -0.056 [-0.087, -0.027] | +0.22 |
| 2022/23 | 2.6719 | 2.6680 | -0.021 [-0.036, -0.006] | +0.17 | 2.6671 | -0.026 [-0.052, -0.001] | +0.27 |

combo minus shipped by phase, pooled over 2023/24-2025/26: cutoffs 1-5 -0.027 [-0.061, +0.003], 6-10 -0.025
[-0.047, -0.006], 11-19 -0.027 [-0.043, -0.011], 20-29 -0.038 [-0.053, -0.022], 30-37 -0.025 [-0.041, -0.008].

Readings:
- **Recency windows are too short.** Every past season prefers longer player-form and team-rating half-lives than
  the shipped 4 and 3 games, monotonically, nearly every step significant; the per-season optima agree (8 games to
  season-long). The ten-week choice was made where the window barely binds; even in past seasons' first ten weeks
  the longer windows are better (combo at cutoffs 6-10: -0.025 [-0.047, -0.006]).
- **Position prior a little too strong**: prior_min 200-300 is better in 2024/25 and 2023/24, flat in 2025/26 and
  2026/27.
- **The last-season prior earns its place**: switching it off (prior_lambda 0) is significantly worse in all three
  seasons that have a prior (the ten-week search had found it "adds very little"); 0.3-0.6 is marginally better than
  0.15, not significantly.
- **team_shrink_k = 3 is at or near the optimum** everywhere except truncated 2022/23 (no season start).
- **The current season does not (yet) agree**: on 2026/27 GW1-10 the combo is +0.018 [-0.013, +0.051] (worse, not
  significant). Recommendation: form_halflife 8 and team_halflife 8 (with prior_min 300, prior_lambda 0.3) improve
  walk-forward RMSE by 0.003-0.008 (dMSE -0.014 to -0.042) in all four past seasons; re-check on 2026/27 at GW20 and
  switch then if it does not reverse. Not changed in this study. (Since shipped by the owner's decision, except
  `prior_lambda`, which was kept at 0.15 after an isolated sweep, see "Longer half-lives and a stronger last-season
  prior" and "prior_lambda kept at 0.15"; the GW20 re-check remains.)

### d. Season start: promoted teams, summer movers, priors

Cutoffs 1-5 (2022/23 has no season start). Groups: players of the three promoted teams; "summer movers" (at a
different PL club at the end of last season, by player `code`); "new to PL" (no PL minutes last season, not
promoted); "stayers". dMSE columns are a variant minus shipped (negative = the variant is better). The team prior
(tested in a scratch script, not shipped) shrinks each team's attack/defence towards its previous-season
season-long rating, regressed halfway to 1, with 6 pseudo-games instead of 3 towards 1.0; promoted teams get the
mean of the three relegated teams' ratings.

| season | group | rows | players | WF RMSE | bias | PPG | WF - PPG | prior_lambda 0 | team prior (K 6, r 0.5) |
|---|---|---|---|---|---|---|---|---|---|
| 2025/26 | promoted (BUR, LEE, SUN) | 950 | 48 | 3.061 | +0.39 | 3.552 | -0.49 | +0.003 [-0.030, +0.034] | -0.097 [-0.264, +0.065] |
| 2025/26 | summer movers | 350 | 17 | 2.863 | +0.79 | 3.334 | -0.47 | -0.185 [-0.439, +0.037] | +0.050 [-0.096, +0.228] |
| 2025/26 | new to PL | 505 | 32 | 2.726 | +0.46 | 3.349 | -0.62 | +0.008 [-0.052, +0.056] | +0.042 [-0.012, +0.097] |
| 2025/26 | stayers | 4,440 | 227 | 3.052 | +0.24 | 3.350 | -0.30 | -0.042 [-0.092, +0.009] | +0.019 [-0.023, +0.063] |
| 2025/26 | all | 6,245 | 324 | 3.018 | +0.31 | 3.381 | -0.36 | -0.039 [-0.078, -0.002] | +0.005 [-0.036, +0.046] |
| 2024/25 | promoted (IPS, LEI, SOU) | 880 | 45 | 2.569 | +0.62 | 2.563 | +0.01 | -0.007 [-0.078, +0.053] | -0.115 [-0.196, -0.027] |
| 2024/25 | summer movers | 235 | 15 | 2.364 | +0.35 | 3.130 | -0.77 | +0.080 [-0.106, +0.269] | -0.105 [-0.231, +0.001] |
| 2024/25 | new to PL | 405 | 29 | 1.945 | +0.50 | 2.241 | -0.30 | +0.014 [-0.014, +0.052] | +0.050 [-0.026, +0.122] |
| 2024/25 | stayers | 4,575 | 229 | 3.030 | +0.16 | 3.455 | -0.43 | +0.128 [-0.024, +0.310] | -0.018 [-0.073, +0.034] |
| 2024/25 | all | 6,095 | 318 | 2.883 | +0.25 | 3.259 | -0.38 | +0.099 [-0.016, +0.237] | -0.031 [-0.075, +0.010] |
| 2023/24 | promoted (BUR, LUT, SHU) | 928 | 47 | 2.146 | +1.23 | 1.829 | +0.32 | -0.005 [-0.010, -0.001] | -0.102 [-0.178, -0.029] |
| 2023/24 | summer movers | 395 | 21 | 2.592 | +0.58 | 2.722 | -0.13 | +0.027 [-0.219, +0.226] | -0.103 [-0.238, +0.016] |
| 2023/24 | new to PL | 510 | 30 | 2.662 | +0.29 | 3.100 | -0.44 | -0.005 [-0.014, +0.000] | -0.029 [-0.131, +0.078] |
| 2023/24 | stayers | 4,210 | 210 | 3.131 | +0.09 | 3.603 | -0.47 | +0.104 [+0.042, +0.178] | -0.020 [-0.054, +0.014] |
| 2023/24 | all | 6,043 | 308 | 2.928 | +0.32 | 3.295 | -0.37 | +0.073 [+0.025, +0.129] | -0.038 [-0.068, -0.010] |

Over all cutoffs (all players): prior_lambda 0 minus shipped +0.015 [+0.004, +0.025], +0.027 [+0.011, +0.046],
+0.015 [+0.006, +0.025]; team prior (K 6, r 0.5) minus shipped -0.009 [-0.015, -0.004], -0.006 [-0.012, -0.001],
-0.005 [-0.009, -0.001] (2025/26, 2024/25, 2023/24). Other team-prior settings (K 3 or full weight r = 1) were
similar or noisier.

Readings:
- **Promoted teams' players are badly over-projected early** (bias +0.4 to +1.2 per game; in 2024/25 and 2023/24 the
  model does no better than PPG for them, while it beats PPG by 0.13-0.77 for every other group). The model starts every
  team at league average and promoted teams are usually well below it.
- **A team-level prior from last season helps**, most for promoted teams (-0.10 to -0.12, significant in two of
  three seasons) and a little for everyone over the whole season (significant in all three). Cheap to add; listed
  in the roadmap, not implemented here.
- **The player prior** (last-season xG/xA) helps over a season in every season, at the very start it is mixed
  (helps in 2023/24, hurts in 2025/26 at cutoffs 1-5, mainly through summer movers, whose prior was earned in
  another team's system: -0.185 [-0.439, +0.037] without it in 2025/26).
- Summer movers and new players are over-projected early too (+0.3 to +0.8), but they are few.

### e. Double and blank gameweeks

Odds on, walk-forward. Per match:

| season | rows | n | WF RMSE | bias | corr | PPG RMSE | WF - PPG |
|---|---|---|---|---|---|---|---|
| 2025/26 | double-gameweek matches | 2,278 | 2.547 | -0.10 | 0.416 | 2.609 | -0.062 |
| | rounds with blanks | 3,413 | 2.583 | -0.05 | 0.394 | 2.603 | -0.020 |
| | normal | 63,506 | 2.764 | +0.02 | 0.330 | 2.847 | -0.083 |
| 2024/25 | double-gameweek matches | 2,144 | 2.944 | -0.34 | 0.389 | 2.947 | -0.003 |
| | rounds with blanks | 5,547 | 2.409 | -0.02 | 0.448 | 2.457 | -0.048 |
| | normal | 62,437 | 2.563 | -0.02 | 0.385 | 2.660 | -0.096 |
| 2023/24 | double-gameweek matches | 5,114 | 2.617 | -0.09 | 0.384 | 2.664 | -0.047 |
| | rounds with blanks | 6,567 | 2.624 | -0.04 | 0.328 | 2.709 | -0.085 |
| | normal | 58,983 | 2.670 | -0.03 | 0.364 | 2.763 | -0.093 |
| 2022/23 | double-gameweek matches | 7,522 | 2.621 | -0.02 | 0.335 | 2.756 | -0.136 |
| | rounds with blanks | 3,066 | 2.642 | +0.00 | 0.323 | 2.657 | -0.016 |
| | normal | 28,726 | 2.688 | +0.02 | 0.319 | 2.814 | -0.126 |

Per player and round (a double-gameweek player's two matches summed; PPG baseline = PPG x matches):

| season | DGW player-rounds | WF RMSE | WF bias | PPG RMSE | top-12 WF / PPG, DGW rounds | top-12 WF / PPG, other rounds | DGW rounds | rounds with blanks |
|---|---|---|---|---|---|---|---|---|
| 2025/26 | 1,139 | 3.864 | -0.21 | 3.996 | 6.96 / 6.67 | 4.35 / 4.11 | 26, 33, 36 | 31, 34 |
| 2024/25 | 1,072 | 4.687 | -0.68 | 4.736 | 7.92 / 6.15 | 5.00 / 4.48 | 24, 25, 32, 33 | 15, 29, 34 |
| 2023/24 | 2,557 | 4.096 | -0.18 | 4.211 | 6.94 / 6.03 | 4.74 / 4.51 | 7, 25, 28, 34, 35, 37 | 2, 17, 18, 26, 29 |
| 2022/23 | 3,761 | 4.026 | -0.03 | 4.356 | 6.50 / 7.01 | 4.44 / 4.97 | 19, 20, 22, 23, 27, 29, 34, 36, 37 | 8, 12, 28, 32 |

Double and blank gameweeks are handled correctly and the model is mostly no worse in them: per-match errors in
double gameweeks are smaller than in normal rounds in three seasons (they fall late in the season, where errors are
smaller), the summed double-gameweek projections beat 2 x PPG in every season, and the top-12 lift over PPG picks
is larger in double-gameweek rounds than in other rounds in three of four seasons. The exception is 2024/25, where
double-gameweek matches were harder (RMSE 2.94 vs 2.56) and only tied PPG. Double-gameweek players are slightly
under-projected (-0.03 to -0.68 per player-round, largest in 2024/25); appearance points are not the cause (they
are over-projected less than in normal rounds), so the shortfall is in the returns.

### Summary: what generalises and what to change

Generalises: the model beats both naive baselines in every season, over every phase, with correlation 0.32-0.39
over a full season; calibration is worth having and most factors are stable across seasons; the odds (blend and,
more so, the ratings nudge) and strength-of-schedule ratings help in every season; the absence rule helps on
balance; double and blank gameweeks need no special treatment beyond what was added here.

Does not generalise: the size of the gains seen on 2026/27 GW1-10 (the edge over PPG there is a start-of-season
effect; the odds gains are 2-6x smaller over a season); the opponent DC factor (no effect on 2025/26); the short
recency half-lives (4 and 3 games); the shipped calibration factors for clean sheets, goals conceded, GK bonus and
midfielder goals/assists (outside every past season's range); "the last-season prior adds very little" (it helps in
every season with one).

Ranked by the strength of the evidence (see docs/ROADMAP.md; 3 and 6 have since been shipped):
1. Keep the odds ratings nudge and blend, strength of schedule and the absence rule (positive in pooled and in most
   seasons).
2. Calibrate from last season's factors: shrink walk-forward factors towards last season's instead of towards 1
   (significant in all three seasons, -0.009 to -0.015 overall, -0.09 to -0.16 at cutoffs 1-5); for the live model,
   that means refitting with 2025/26 rows as the shrinkage target rather than trusting ten weeks.
3. Longer recency windows: form_halflife 8, team_halflife 8 (with prior_min 300, prior_lambda 0.3): -0.014 to
   -0.042 dMSE in all four past seasons; not yet supported by 2026/27 GW1-10; re-test at GW20. (Shipped, except
   prior_lambda, which stayed at 0.15: the isolated sweep found 0.3 no better.)
4. A team-level prior from last season (6 pseudo-games, halfway to last season's rating; promoted teams at the
   relegated teams' level): significant small gains in all three seasons, large for promoted teams early.
5. Switch the opponent DC factor off unless 2026/27 GW20+ shows a gain (no effect on the one other season with DC).
6. Model saves points as E[floor(saves / 3)] (stable 0.57-0.67 factor in every season), and revisit GK bonus.

`fplxpts backtest --season all` prints the headline lines per season; the tables above come from a scratch study
script over cached backtest rows (167 backtest runs, about 2 minutes on 7 cores).

## Limitations

- Only 10 gameweeks of the current season (past seasons are replayed in [Past seasons](#past-seasons)). The
  shipped calibration factors are fitted on the whole window, so the in-sample line flatters them; the walk-forward line is the honest number (it includes uncalibrated cutoff 1). The shrinkage
  strength is only identified by the early cutoffs. Refit as the season grows.
- The backtest uses raw histories. Per-match penalty data is not available for past gameweeks, so
  penalties are stripped only in live projections.
- Last-season priors include penalty xG and cannot see club changes.
- Goal and assist calibration was tested for dependence on shot volume (bucketed ratios); it did not improve
  the time-split error, so flat per-position factors are used.
