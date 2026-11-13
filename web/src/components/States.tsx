import { POSITION_LABELS } from '../config';
import { POSITIONS } from '../types';
import { AlertIcon } from './Icons';

const SKELETON_ROWS = 10;

export function LoadingState() {
  return (
    <div className="grid" aria-busy="true">
      <p className="visually-hidden" role="status">
        Loading projections…
      </p>
      {POSITIONS.map((pos, i) => (
        <div key={pos} className="card card--skeleton" data-active={i === 0} aria-hidden>
          <div className="card__head">
            <span className="card__title">{POSITION_LABELS[pos].title}</span>
          </div>
          <div className="players">
            {Array.from({ length: SKELETON_ROWS }, (_, row) => (
              <div key={row} className="skeleton-row">
                <span className="skeleton skeleton--rank" />
                <span className="skeleton-row__who">
                  <span className="skeleton skeleton--name" style={{ width: `${70 - row * 3}%` }} />
                  <span className="skeleton skeleton--sub" />
                </span>
                <span className="skeleton skeleton--total" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="error" role="alert">
      <AlertIcon size={20} />
      <div className="error__body">
        <h2 className="error__title">Projections couldn’t be loaded</h2>
        <p className="error__message">{message}</p>
        <button type="button" className="button" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}

export function StaleBanner() {
  return (
    <p className="banner">
      <AlertIcon />
      <span>Projections may be out of date: they were generated more than two days ago.</span>
    </p>
  );
}
