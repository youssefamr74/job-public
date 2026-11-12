import type { AnalyticsRange } from '../api/types';
import { plural } from './format';

export const RANGES: { value: AnalyticsRange; label: string }[] = [
  { value: '30', label: '30 days' },
  { value: '60', label: '60 days' },
  { value: 'all', label: 'All time' },
];

const monthDay = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });

/** A calendar day from the API ("2026-09-08") read as a local date, not UTC midnight. */
export function calendarDay(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}

export function dayLabel(value: string): string {
  return monthDay.format(calendarDay(value));
}

export function percent(rate: number | null | undefined): string {
  return rate == null ? '—' : `${Math.round(rate)}%`;
}

export function replyTime(days: number | null | undefined): string {
  if (days == null) return '—';
  if (days < 1) return 'Under a day';
  return plural(Math.round(days), 'day');
}

/** "about 18 a week" */
export function perWeek(value: number): string {
  if (value === 0) return 'none in this range';
  if (value < 1) return 'less than 1 a week';
  return `about ${Math.round(value)} a week`;
}

/** Bar length in percent of the track, with a sliver for small non-zero values so they stay visible. */
export function barWidth(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  return Math.max((value / max) * 100, 1.5);
}
