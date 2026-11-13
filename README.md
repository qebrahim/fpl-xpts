# fplxpts

An expected-points model for Fantasy Premier League, with a **walk-forward backtest** that measures how
well it actually predicts, and a lineup / transfer optimiser built on top.

Most FPL tools just show projections. This one checks itself: it replays the season week by week using only
the data available at the time, compares predictions with what happened, and fits correction factors from
the errors it finds.

> Hobby project. Not affiliated with the Premier League or Fantasy Premier League. Uses the public,
> unofficial FPL API; please keep the on-disk cache enabled and don't hammer it.

## What it does

- **Team ratings** from per-fixture xG (derived from goalkeeper xGC), venue-normalised, recency-weighted and
  shrunk towards the league average.
- **Bonus by how it is earned:** projected from the goals, assists, clean sheet and saves expected in each
  fixture (marginal bonus per event by position) plus a player baseline, not a flat rate.
- **Player rates** for xG, xA, bonus baseline, saves, cards, minutes and defensive contribution, shrunk towards a
  position prior and a small last-season prior.
- **Penalties handled explicitly:** taken penalties are stripped from history and each club's primary taker
  gets a normal forward-looking share, so a lucky run of penalties is not extrapolated.
- **Expected points by component** (appearance, goals, assists, clean sheet, goals conceded, defensive
  contribution, bonus, saves, cards), each calibrated by a per-position factor.
- **Lineup picker** (best XI, formation, captain) and a **single-transfer search** scored by best-XI points
  over a window.
- **Backtest** with naive baselines, a time-split check on the calibration, and a calibration fitter.

## Quick start

```bash
pip install -e ".[dev]"
cp config/squad.example.toml config/squad.toml     # edit with your 15 players

fplxpts project --squad config/squad.toml --top 8                    # best players by position, next 5 GWs
fplxpts squad   --squad config/squad.toml --swap Schade:Rudoni       # per-GW XI and captain after a transfer
fplxpts moves   --squad config/squad.toml --max-cost 0.5             # best single transfers
fplxpts backtest --fit                                               # replay the season, print fitted factors
```

Example (`fplxpts squad --swap Schade:Rudoni --weeks 1`):

```
GW11  5-2-3  XI 51.9  (C Isak, VC N.Jackson)
   XI   : Raya 4.5, Van Hecke 5.0, Muharemović 4.5, De Cuyper 4.3, Thomas 4.2, Calafiori 4.0, Rudoni 4.9, Tavernier 3.7, Isak 5.8, N.Jackson 5.5, Haaland 5.4
   Bench: Mbeumo 3.5, Rogers 3.4, Barnes 3.2, Palmer 0.0
```

## How well does it work?

Walk-forward over GW1-9 starts, predicting the next 5 rounds (9,267 player-games, 2026/27 season):

| Predictor | RMSE |
|---|---|
| Model, calibrated (in-sample) | 2.945 |
| Model, uncalibrated | 2.964 |
| Season points-per-game so far | 3.332 |
| Last-four-games form | 3.365 |

Calibration factors fitted on early rounds and tested on later ones: RMSE 2.835 -> 2.826 and bias
+0.23 -> -0.05. Weekly FPL points are mostly noise: correlation between predicted and actual is about 0.29.
See [docs/BACKTEST.md](docs/BACKTEST.md) for the method and what the backtest found (for example, defender
goal threat was over-projected by roughly 2x, and past finishing under-performance did not persist).

## Layout

```
src/fplxpts/
  api.py        FPL API client + disk cache
  data.py       Season loader (team xG from keeper xGC, finished-match histories, past seasons)
  teams.py      team attack/defence ratings
  players.py    player rates with position + last-season priors
  pens.py       penalty stripping and primary-taker shares
  points.py     expected points by component; calibration
  model.py      Projector: rates + fixtures -> expected points per gameweek
  optimize.py   best XI, captain, single-transfer search
  backtest.py   walk-forward backtest, baselines, calibration fit
  cli.py        fplxpts {project,squad,moves,backtest}
  default.toml  hyper-parameters and calibration factors
config/squad.example.toml   example squad, overrides and penalty counts
docs/                       ROADMAP.md (planned work), BACKTEST.md (method and findings)
app/streamlit_app.py        UI stub
legacy/                     the original exploratory scripts, kept as a parity reference
```

## Web front end

`fplxpts export --out web/public/data/projections.json` writes the top 10 players per position by expected
points over the next 5 gameweeks (with per-gameweek fixtures) as JSON; penalty counts come from
`data/pens.toml` if present. The static site in `web/` reads that file, and a scheduled GitHub Action
(`.github/workflows/publish.yml`) re-runs the export and rebuilds the GitHub Pages site daily.

## Development

```bash
pytest          # offline unit tests
ruff check .
```

See [docs/ROADMAP.md](docs/ROADMAP.md) for what's planned and [CLAUDE.md](CLAUDE.md) for notes aimed at
AI coding assistants working in this repo.
