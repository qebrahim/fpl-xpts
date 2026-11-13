import { BACKTEST_RMSE } from '../config';

export function Footer() {
  return (
    <footer className="footer">
      <p>
        A hobby project, not affiliated with the Premier League or Fantasy Premier League. Data comes from the
        public, unofficial FPL API.
      </p>
      <p>
        Projections are model estimates with real error: in backtests the typical miss is about {BACKTEST_RMSE}{' '}
        points per player per game (RMSE).
      </p>
    </footer>
  );
}
