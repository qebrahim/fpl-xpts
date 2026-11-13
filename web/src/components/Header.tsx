import { GITHUB_URL } from '../config';
import { formatAbsoluteTime, formatGameweekRange, formatRelativeTime } from '../format';
import type { Theme } from '../hooks/useTheme';
import type { Projections } from '../types';
import { GitHubIcon, MoonIcon, SunIcon } from './Icons';

interface HeaderProps {
  data: Projections | null;
  loading: boolean;
  theme: Theme;
  onToggleTheme: () => void;
}

export function Header({ data, loading, theme, onToggleTheme }: HeaderProps) {
  const next: Theme = theme === 'dark' ? 'light' : 'dark';
  return (
    <header className="header">
      <div className="header__top">
        <p className="wordmark">
          fpl<span className="wordmark__accent">xpts</span>
        </p>
        <div className="header__actions">
          <button
            type="button"
            className="icon-button"
            onClick={onToggleTheme}
            aria-label={`Switch to ${next} theme`}
            title={`Switch to ${next} theme`}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
          <a className="icon-button" href={GITHUB_URL} aria-label="Source on GitHub" title="Source on GitHub">
            <GitHubIcon />
          </a>
        </div>
      </div>
      <h1 className="header__title">
        Top Fantasy Premier League players by expected points (xPts) over the next five gameweeks.
      </h1>
      <div className="header__meta" aria-live="polite">
        {data ? <Freshness data={data} /> : loading && <span className="skeleton skeleton--meta" aria-hidden />}
      </div>
    </header>
  );
}

function Freshness({ data }: { data: Projections }) {
  const generated = new Date(data.generated_at);
  return (
    <>
      <span className="chip">{formatGameweekRange(data.gameweeks)}</span>
      <span className="header__fresh">
        Updated{' '}
        <time dateTime={data.generated_at} title={formatAbsoluteTime(generated)}>
          {formatRelativeTime(generated)}
        </time>{' '}
        · data through GW{data.data_through_gw}
      </span>
    </>
  );
}
