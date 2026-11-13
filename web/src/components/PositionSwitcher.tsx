import { POSITION_LABELS } from '../config';
import { POSITIONS, type Position } from '../types';

interface PositionSwitcherProps {
  value: Position;
  onChange: (position: Position) => void;
}

/** Segmented control shown only on narrow screens, where one card is visible at a time. */
export function PositionSwitcher({ value, onChange }: PositionSwitcherProps) {
  return (
    <div className="switcher">
      <div className="segmented" role="group" aria-label="Position">
        {POSITIONS.map((pos) => (
          <button
            key={pos}
            type="button"
            className="segmented__item"
            aria-pressed={pos === value}
            title={POSITION_LABELS[pos].title}
            onClick={() => onChange(pos)}
          >
            {POSITION_LABELS[pos].short}
          </button>
        ))}
      </div>
    </div>
  );
}
