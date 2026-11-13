import { useState } from 'react';
import { STALE_AFTER_MS } from '../config';
import { POSITIONS, type Position, type Projections } from '../types';
import { PositionCard } from './PositionCard';
import { PositionSwitcher } from './PositionSwitcher';
import { StaleBanner } from './States';

export function TopPlayers({ data }: { data: Projections }) {
  const [position, setPosition] = useState<Position>('GK');
  const stale = Date.now() - Date.parse(data.generated_at) > STALE_AFTER_MS;

  return (
    <>
      {stale && <StaleBanner />}
      <PositionSwitcher value={position} onChange={setPosition} />
      <div className="grid">
        {POSITIONS.map((pos) => (
          <PositionCard key={pos} position={pos} players={data.positions[pos]} active={pos === position} />
        ))}
      </div>
    </>
  );
}
