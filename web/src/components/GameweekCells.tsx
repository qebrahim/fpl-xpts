import type { CSSProperties } from 'react';
import { formatFixture, formatFixtureLabel, formatPoints } from '../format';
import type { GameweekProjection } from '../types';

interface GameweekCellsProps {
  weeks: GameweekProjection[];
  /** Best single-gameweek xPts in the position; cells are tinted relative to it. */
  scaleMax: number;
}

/** Squared so that ordinary weeks stay pale and only genuinely strong weeks stand out. */
function tintStrength(xpts: number, scaleMax: number): number {
  if (scaleMax <= 0) return 0;
  const ratio = Math.min(Math.max(xpts / scaleMax, 0), 1);
  return ratio * ratio;
}

export function GameweekCells({ weeks, scaleMax }: GameweekCellsProps) {
  return (
    <ul className="gw-cells">
      {weeks.map((week) => {
        const strength = tintStrength(week.xpts, scaleMax);
        const blank = week.fixtures.length === 0;
        return (
          <li
            key={week.gw}
            className={`gw-cell${blank ? ' gw-cell--blank' : ''}`}
            style={{ '--strength': strength.toFixed(3) } as CSSProperties}
          >
            <span className="gw-cell__gw">GW{week.gw}</span>
            <span className="gw-cell__fixtures">
              {blank ? (
                <>
                  <span aria-hidden>—</span>
                  <span className="gw-cell__blank">Blank</span>
                </>
              ) : (
                week.fixtures.map((fixture, i) => (
                  <span key={`${fixture.opp}-${i}`} title={formatFixtureLabel(fixture)}>
                    {formatFixture(fixture)}
                  </span>
                ))
              )}
            </span>
            <span className="gw-cell__xpts">
              {formatPoints(week.xpts)}
              <span className="visually-hidden"> xPts</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
