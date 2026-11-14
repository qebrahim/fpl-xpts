# fplxpts

An expected-points model for Fantasy Premier League, with a **walk-forward backtest** that measures how
well it actually predicts, and a lineup / transfer optimiser built on top.

Most FPL tools just show projections. This one checks itself: it replays the season week by week using only
the data available at the time, compares predictions with what happened, and fits correction factors from
the errors it finds.

> Hobby project. Not affiliated with the Premier League or Fantasy Premier League. Uses the public,
> unofficial FPL API; please keep the on-disk cache enabled and don't hammer it.

## What it does

- **Team ratings** from per-fixture xG (derived from goalkeeper xGC), venue-normalised, adjusted for strength of
  schedule (each game's xG is divided by the opponent's defence or attack rating, iterated to a fixed point),
  recency-weighted and shrunk towards the league average.
- **Bookmaker odds:** for the next gameweek, each team's expected goals for and against are blended 50/50 with the
  goals implied by bookmaker 1X2 and over/under prices (de-vigged, converted to Poisson goals), which feeds clean
  sheets, goals conceded, saves and the attacking multiplier. In the walk-forward backtest with pre-match odds this
  improved next-round player RMSE significantly (walk-forward 2.935 -> 2.916 on those rows). Falls back to the
  model's own numbers when there is no API key or no odds; `--no-odds` turns it off.
- **Bonus by how it is earned:** projected from the goals, assists, clean sheet and saves expected in each
  fixture (marginal bonus per event by position) plus a player baseline, not a flat rate.
- **Player rates** for xG, xA, bonus baseline, saves, cards, minutes and defensive contribution, shrunk towards a
  position prior and a small last-season prior. The minutes model skips games an established starter missed
  through (inferred) injury or suspension once he is back in the side; current availability comes from FPL's flags.
- **Penalties handled explicitly:** taken penalties are stripped from history and each club's primary taker
  gets a normal forward-looking share, so a lucky run of penalties is not extrapolated.
- **Expected points by component** (appearance, goals, assists, clean sheet, goals conceded, defensive
  contribution, bonus, saves, cards), each calibrated by a per-position factor (actual/predicted ratio from the
  backtest, shrunk towards 1).
- **Lineup picker** (best XI, formation, captain) and a **single-transfer search** scored by best-XI points
  over a window.
- **Backtest** with naive baselines, out-of-sample checks on the calibration (factors refitted at every cutoff, and
  a time split), and a calibration fitter.

## Quick start

```bash
pip install -e ".[dev]"
cp config/squad.example.toml config/squad.toml     # edit with your 15 players

fplxpts project --squad config/squad.toml --top 8                    # best players by position, next 5 GWs
fplxpts squad   --squad config/squad.toml --swap Schade:Rudoni       # per-GW XI and captain after a transfer
fplxpts moves   --squad config/squad.toml --max-cost 0.5             # best single transfers
fplxpts backtest --fit                                               # replay the season, print fitted factors
```

Example (`fplxpts squad --swap Schade:Rudoni --weeks 1 --no-odds`):

```
GW11  5-2-3  XI 50.9  (C Isak, VC Haaland)
   XI   : Raya 4.4, Van Hecke 4.9, Muharemović 4.4, De Cuyper 4.3, Thomas 4.2, Calafiori 4.0, Rudoni 5.2, Tavernier 3.8, Isak 5.6, Haaland 5.3, N.Jackson 4.8
   Bench: Mbeumo 3.5, Rogers 3.2, Barnes 3.1, Palmer 0.0
```

### Bookmaker odds (optional)

Live projections (`project`, `squad`, `moves`, `export`) use bookmaker odds from
[The Odds API](https://the-odds-api.com) when a key is available, and print one line saying how many next-gameweek
fixtures were anchored to odds and how many fell back to the model. Without a key everything still works.

- Get a free key at https://the-odds-api.com and put it in `.env` at the repo root (`cp .env.example .env`, then
  `ODDS_API_KEY=...`; `.env` is git-ignored), or export `ODDS_API_KEY` in the environment (a non-empty environment
  variable wins over `.env`). Never commit the key or put it in `web/`.
- For the scheduled site build, add a repository secret named `ODDS_API_KEY` (Settings -> Secrets and variables ->
  Actions). The workflow passes it to the export step; while the secret is missing the build runs on the model's own
  numbers.
- Quota: one request (`markets=h2h,totals`, `regions=uk`) costs 2 credits; the free plan has a small monthly quota
  (500 credits at the time of writing). Responses are cached in `.cache/odds-api_soccer_epl.json` for 12 hours, so
  the daily build uses about 60 credits a month.

## How well does it work?

Walk-forward over GW1-9 starts, predicting the next 5 rounds (9,267 player-games, 2026/27 season):

| Predictor | RMSE |
|---|---|
| Model, calibrated, walk-forward (out-of-sample) | 2.956 |
| Model, calibrated, in-sample (shipped factors) | 2.944 |
| Model, uncalibrated | 2.964 |
| Season points-per-game so far | 3.332 |
| Last-four-games form | 3.365 |

These are without bookmaker odds (`--no-odds`); with the shipped next-round odds anchoring (pre-match odds,
only those available before each round) they are 2.951 walk-forward, 2.939 in-sample, 2.959 uncalibrated.
The in-sample line uses factors fitted on the same rows; the walk-forward line refits them at each cutoff using
only outcomes known by then (cutoff 1 has nothing to fit on and stays uncalibrated). Factors fitted on early
rounds and tested on later ones: RMSE 2.840 -> 2.825 and bias +0.26 -> +0.01. Weekly FPL points are mostly noise: correlation between predicted and actual is about 0.29.
See [docs/BACKTEST.md](docs/BACKTEST.md) for the method and what the backtest found (for example, defender
goal threat was over-projected by roughly 2x, and past finishing under-performance did not persist).

## Data sources

- **Fantasy Premier League API** (public, unofficial, undocumented): players, fixtures, match histories. Cached in
  `.cache/` (`--ttl`, default 1 hour).
- **[Football-Data.co.uk](https://www.football-data.co.uk/)**: free results-and-odds CSVs, used by the backtest for
  historical bookmaker odds (`https://www.football-data.co.uk/mmz4281/2627/E0.csv`, column notes at
  https://www.football-data.co.uk/notes.txt). Downloaded once into `.cache/football-data_E0_<season>.csv` and
  re-read from disk (re-downloaded at most daily; works offline from the cached file).
- **[The Odds API](https://the-odds-api.com)** v4: live bookmaker odds for upcoming fixtures (needs `ODDS_API_KEY`,
  see above). Cached in `.cache/odds-api_soccer_epl.json` for 12 hours; the key is never written to disk or logs.

## Layout

```
src/fplxpts/
  api.py        FPL API client + disk cache
  data.py       Season loader (team xG from keeper xGC, finished-match histories, past seasons)
  teams.py      team attack/defence ratings
  players.py    player rates with position + last-season priors
  pens.py       penalty stripping and primary-taker shares
  points.py     expected points by component; calibration
  odds.py       bookmaker odds: de-vig, Poisson goals, Football-Data CSV and The Odds API loaders
  model.py      Projector: rates + fixtures -> expected points per gameweek
  optimize.py   best XI, captain, single-transfer search
  backtest.py   walk-forward backtest, baselines, calibration fit
  cli.py        fplxpts {project,squad,moves,backtest,export}
  default.toml  hyper-parameters and calibration factors
config/squad.example.toml   example squad, overrides and penalty counts
docs/                       ROADMAP.md (planned work), BACKTEST.md (method and findings)
app/streamlit_app.py        UI stub
legacy/                     the original exploratory scripts, kept as a parity reference
```

## Web front end

`fplxpts export --out web/public/data/projections.json` writes the top 10 players per position by expected
points over the next 5 gameweeks (with per-gameweek fixtures) as JSON; penalty counts come from
`data/pens.toml` if present. When bookmaker odds were used, an optional top-level `"odds"` field records the source,
fetch time and how many next-gameweek fixtures were anchored (`null` if none). The static site in `web/` reads that file, and a scheduled GitHub Action
(`.github/workflows/publish.yml`) re-runs the export and rebuilds the GitHub Pages site daily.

## Development

```bash
pytest          # offline unit tests
ruff check .
```

See [docs/ROADMAP.md](docs/ROADMAP.md) for what's planned and [CLAUDE.md](CLAUDE.md) for notes aimed at
AI coding assistants working in this repo.
