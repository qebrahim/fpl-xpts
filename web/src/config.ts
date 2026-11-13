import type { Position } from './types';

// TODO: replace with the public repository URL before deploying.
export const GITHUB_URL = 'https://github.com/';

export const DATA_URL = `${import.meta.env.BASE_URL}data/projections.json`;

/** Projections older than this get an "out of date" banner. */
export const STALE_AFTER_MS = 48 * 60 * 60 * 1000;

/** Backtest RMSE per player-game, quoted in the footer. */
export const BACKTEST_RMSE = 2.9;

export const POSITION_LABELS: Record<Position, { title: string; short: string }> = {
  GK: { title: 'Goalkeepers', short: 'GK' },
  DEF: { title: 'Defenders', short: 'DEF' },
  MID: { title: 'Midfielders', short: 'MID' },
  FWD: { title: 'Forwards', short: 'FWD' },
};
