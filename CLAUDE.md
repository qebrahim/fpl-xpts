# Notes for AI coding assistants

## What this is
`fplxpts`: expected-points model for Fantasy Premier League + walk-forward backtest + lineup/transfer
optimiser. Pure Python (>=3.11), only dependency is numpy (backtest). Data comes from the public FPL API.

## Commands
```bash
pip install -e ".[dev]"
pytest                      # offline unit tests (58)
ruff check .
fplxpts backtest            # needs network (cached in .cache/)
fplxpts squad --squad config/squad.example.toml --swap Schade:Rudoni
fplxpts export --out web/public/data/projections.json   # JSON for the web front end
```
In a sandbox with a proxy set `SSL_CERT_FILE` to the CA bundle before running anything that hits the API.

## Architecture (data flows top to bottom)
`api.py` -> `data.py` (Season) -> `teams.py` (ratings) + `players.py` (rates) -> `points.py` (components)
-> `model.py` (Projector: fixtures -> expected points per GW) -> `optimize.py` / `backtest.py` / `export.py` (JSON for `web/`) -> `cli.py`.
`pens.py` adjusts history before `players.py`. Config lives in `default.toml` (hyper-parameters and the
calibration factors) and the user's squad TOML.

## Things that are easy to get wrong
- **Do not change the model without checking parity.** Golden numbers are in `docs/ROADMAP.md`. If a change
  is meant to move them, say so and update the numbers.
- Leakage: anything used to predict round r must only use rounds < r. `build_players(season, cut, ...)`
  and `team_state(season, cut, ...)` enforce this with `cut`.
- TOML: top-level keys must come before the first `[[table]]`, or they attach to that table.
- FPL exposes `penalties_missed` but not penalties scored; scored penalties come from the squad TOML.
- Calibration factors were refitted on GW1-10 of 2026/27 (2026-11, current default model, pseudo-point shrinkage
  k = 160 = `backtest.CAL_K`, chosen by walk-forward calibration). The in-sample backtest line grades them on the
  rows they were fitted on; the walk-forward line is the honest one. Refit with `fplxpts backtest --fit` and paste
  into `default.toml`.
- Be polite to the API: use the cache, don't add per-request fetch loops without caching.
- Don't scrape sites that disallow it; penalty data sources must be documented and respect their terms.
- Do not commit `.cache/` or `config/squad.toml`.

## Conventions
- Small pure functions with type hints; no hidden globals (the legacy scripts used globals, don't copy that).
- Add a unit test for every new formula; add a golden test for model-level changes.
- Keep `docs/BACKTEST.md` in sync when results change.

## First tasks
See `docs/ROADMAP.md`, section P0.
