export const POSITIONS = ['GK', 'DEF', 'MID', 'FWD'] as const;
export type Position = (typeof POSITIONS)[number];

export interface Fixture {
  opp: string;
  home: boolean;
}

export interface GameweekProjection {
  gw: number;
  xpts: number;
  fixtures: Fixture[];
}

export interface Player {
  id: number;
  name: string;
  team: string;
  price: number;
  total: number;
  by_gw: GameweekProjection[];
}

export interface Projections {
  schema: 1;
  generated_at: string;
  data_through_gw: number;
  gameweeks: number[];
  positions: Record<Position, Player[]>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** Light structural check: enough to fail loudly on a wrong or stale file, not a full validator. */
export function parseProjections(value: unknown): Projections {
  if (!isRecord(value)) throw new Error('Projection file is not a JSON object.');
  if (value.schema !== 1) throw new Error(`Unsupported schema version: ${String(value.schema)}.`);
  const { positions, gameweeks, generated_at } = value;
  if (!isRecord(positions)) throw new Error('Projection file has no positions.');
  if (!Array.isArray(gameweeks)) throw new Error('Projection file has no gameweeks.');
  if (typeof generated_at !== 'string' || Number.isNaN(Date.parse(generated_at))) {
    throw new Error('Projection file has an invalid generated_at timestamp.');
  }
  for (const pos of POSITIONS) {
    if (!Array.isArray(positions[pos])) throw new Error(`Projection file is missing ${pos}.`);
  }
  return value as unknown as Projections;
}
