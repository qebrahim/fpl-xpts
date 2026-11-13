import { POSITION_LABELS } from '../config';
import type { Player, Position } from '../types';
import { PlayerRow } from './PlayerRow';

interface PositionCardProps {
  position: Position;
  players: Player[];
  active: boolean;
}

export function PositionCard({ position, players, active }: PositionCardProps) {
  const headingId = `heading-${position}`;
  const leaderTotal = players[0]?.total ?? 0;
  const bestWeek = Math.max(0, ...players.flatMap((p) => p.by_gw.map((w) => w.xpts)));

  return (
    <section className="card" aria-labelledby={headingId} data-active={active}>
      <div className="card__head">
        <h2 id={headingId} className="card__title">
          {POSITION_LABELS[position].title}
        </h2>
        <span className="card__unit" aria-hidden>
          xPts
        </span>
      </div>
      {players.length === 0 ? (
        <p className="card__empty">No projections for this position.</p>
      ) : (
        <ol className="players">
          {players.map((player, i) => (
            <PlayerRow
              key={player.id}
              player={player}
              rank={i + 1}
              leaderTotal={leaderTotal}
              bestWeek={bestWeek}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
