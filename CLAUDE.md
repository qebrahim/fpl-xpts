# Notes for AI coding assistants

## What this is
`fplxpts`: expected-points model for Fantasy Premier League + walk-forward backtest + lineup/transfer
optimiser. Pure Python (>=3.11), only dependency is numpy (backtest). Data comes from the public FPL API, plus
bookmaker odds (Football-Data.co.uk CSV for the backtest, The Odds API for live projections; `odds.py`), plus past
seasons from the community archive github.com/vaastav/Fantasy-Premier-League (MIT; cite and link back; `archive.py`).

## Commands
```bash
pip install -e ".[dev]"
pytest                      # offline unit tests (140)
ruff check .
fplxpts backtest            # needs network (cached in .cache/); uses historical odds, --no-odds for the odds-off lines
fplxpts squad --squad config/squad.example.toml --swap Schade:Rudoni
fplxpts export --out web/public/data/projections.json   # JSON for the web front end (live odds if ODDS_API_KEY is set)
# parity / golden numbers are defined with odds OFF (live odds change daily):
fplxpts --ttl 999999999 squad --no-odds --squad config/squad.example.toml
fplxpts --ttl 999999999 export --no-odds --out /tmp/p.json
fplxpts --ttl 999999999 backtest --no-odds
fplxpts --ttl 999999999 backtest --season all   # past seasons 2025-26..2022-23 from the cached archive (~45 s)
fplxpts --ttl 999999999 backtest --fit --prior-season 2025-26   # calibration shrunk towards last season's factors (option, off by default)
```
In a sandbox with a proxy set `SSL_CERT_FILE` to the CA bundle before running anything that hits the API.

## Architecture (data flows top to bottom)
`api.py` -> `data.py` (Season) -> `teams.py` (ratings) + `players.py` (rates) -> `points.py` (components)
-> `model.py` (Projector: fixtures -> expected points per GW) -> `optimize.py` / `backtest.py` / `export.py` (JSON for `web/`) -> `cli.py`.
`archive.py` builds the same `Season` for a past season from the community archive (`backtest --season`); its match
rows carry `team` (the club in that match), which `players.current_team` / `backtest.at_club` use (live rows have
none, so the live path is unchanged). `pens.py` adjusts history before `players.py`. `odds.py` turns bookmaker prices into Poisson team goals per fixture
(`MatchOdds`); `teams.team_state(..., odds)` blends them into the next round's fixtures (`TeamState.fixture_xg`, read
by `points.components`) and, if `odds_ratings_weight > 0`, into the ratings. Config lives in `default.toml` (hyper-parameters and the
calibration factors) and the user's squad TOML.

## Things that are easy to get wrong
- **Do not change the model without checking parity.** Golden numbers are in `docs/ROADMAP.md`, defined with
  `--no-odds`. If a change is meant to move them, say so and update the numbers.
- Leakage: anything used to predict round r must only use rounds < r. `build_players(season, cut, ...)`
  and `team_state(season, cut, ...)` enforce this with `cut`. Odds: at cutoff c the backtest may only pass the odds
  for round c+1 (`odds.available_at`), using the pre-match columns, not the closing ones.
- TOML: top-level keys must come before the first `[[table]]`, or they attach to that table.
- FPL exposes `penalties_missed` but not penalties scored; scored penalties come from the squad TOML.
- Calibration factors were refitted on GW1-10 of 2026/27 (2026-11, current default model, pseudo-point shrinkage
  k = 160 = `backtest.CAL_K`, chosen by walk-forward calibration). The in-sample backtest line grades them on the
  rows they were fitted on; the walk-forward line is the honest one. Refit with `fplxpts backtest --fit` (rows with
  the historical odds on) and paste into `default.toml`; refit after any change to the hyper-parameters. The recency
  half-lives and prior weights (`form_halflife`, `team_halflife`, `prior_min`, `prior_lambda`) were chosen on the four
  past seasons, not on 2026/27; `ModelCfg` dataclass defaults are the older/off values, `default.toml` is the shipped config.
- Be polite to the API: use the cache, don't add per-request fetch loops without caching.
- Past seasons are their own world: ids are per season (link players by `code`), `prior_seasons` is written for
  2026/27 and shifted per season (`archive.shift_prior_seasons`), dc points only exist from 2025/26
  (`archive.scoring_rules`), 2022/23 has no xG before GW16 (dropped), and double gameweeks are two rows in one round.
  Archive files are downloaded once into `.cache/vaastav_<season>_<name>.csv` and never re-fetched.
- **The Odds API key (`ODDS_API_KEY`, from the environment or `.env`) is a secret.** Never print, log or commit it;
  never put it in a file, cache filename or cached payload, test, doc or error message (`odds.fetch_odds_api`
  re-raises failures sanitized). The free plan has a small monthly quota (2 credits per call): rely on the 12-hour
  cache, never add live calls in loops or tests. Odds must never make a run fail: no key or a failed request means
  the model's own numbers plus one status line.
- Don't scrape sites that disallow it; penalty data sources must be documented and respect their terms.
- Do not commit `.cache/` or `config/squad.toml`.

## Conventions
- Small pure functions with type hints; no hidden globals (the legacy scripts used globals, don't copy that).
- Add a unit test for every new formula; add a golden test for model-level changes.
- Keep `docs/BACKTEST.md` in sync when results change.

## First tasks
See `docs/ROADMAP.md`, section P0.
