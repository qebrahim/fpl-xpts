import { useId, useState, type CSSProperties } from 'react';
import { formatPoints, formatPrice } from '../format';
import type { Player } from '../types';
import { GameweekCells } from './GameweekCells';
import { ChevronIcon } from './Icons';

interface PlayerRowProps {
  player: Player;
  rank: number;
  leaderTotal: number;
  bestWeek: number;
}

export function PlayerRow({ player, rank, leaderTotal, bestWeek }: PlayerRowProps) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const share = leaderTotal > 0 ? Math.min(player.total / leaderTotal, 1) : 0;

  return (
    <li className={`player${rank === 1 ? ' player--leader' : ''}`}>
      <button
        type="button"
        className="player__row"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="player__rank">{rank}</span>
        <span className="player__who">
          <span className="player__name">{player.name}</span>
          <span className="player__sub">
            {player.team} · {formatPrice(player.price)}
          </span>
        </span>
        <span className="player__total">
          {formatPoints(player.total)}
          <span className="visually-hidden"> expected points</span>
        </span>
        <span className="player__chevron">
          <ChevronIcon size={14} />
        </span>
        <span className="player__bar" aria-hidden style={{ '--share': share.toFixed(4) } as CSSProperties} />
      </button>
      <div id={panel} className="player__panel" hidden={!open}>
        {open && <GameweekCells weeks={player.by_gw} scaleMax={bestWeek} />}
      </div>
    </li>
  );
}
