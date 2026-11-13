import type { Fixture } from './types';

export function formatPoints(value: number): string {
  return value.toFixed(1);
}

export function formatPrice(price: number): string {
  return `£${price.toFixed(1)}m`;
}

/** "BOU (H)" for home, "bou (A)" for away. */
export function formatFixture({ opp, home }: Fixture): string {
  return home ? `${opp.toUpperCase()} (H)` : `${opp.toLowerCase()} (A)`;
}

export function formatFixtureLabel({ opp, home }: Fixture): string {
  return `${opp.toUpperCase()} ${home ? 'at home' : 'away'}`;
}

/** "GW11–15", or "GW11" for a single week. */
export function formatGameweekRange(gameweeks: readonly number[]): string {
  const first = gameweeks[0];
  const last = gameweeks[gameweeks.length - 1];
  if (first === undefined || last === undefined) return '';
  return first === last ? `GW${first}` : `GW${first}–${last}`;
}

const UNITS: ReadonlyArray<[Intl.RelativeTimeFormatUnit, number]> = [
  ['day', 86_400_000],
  ['hour', 3_600_000],
  ['minute', 60_000],
];

/** "3h ago", "2d ago", "just now". */
export function formatRelativeTime(then: Date, now: Date = new Date()): string {
  const diff = now.getTime() - then.getTime();
  if (diff < 60_000) return 'just now';
  for (const [unit, ms] of UNITS) {
    if (diff >= ms) return `${Math.floor(diff / ms)}${unit[0]} ago`;
  }
  return 'just now';
}

export function formatAbsoluteTime(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}
