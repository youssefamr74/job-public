import type { Application } from '../api/types';
import { BOARD_STATUSES, NEEDS_REVIEW } from '../api/types';
import { plural, shortDate, toDate } from './format';

const MISSING = new Set(['', 'unknown', 'n/a', 'none']);

export function isMissing(value: string | null | undefined): boolean {
  return value == null || MISSING.has(value.trim().toLowerCase());
}

export function statusClass(status: string): string {
  return `status-${status.replace(/\s+/g, '-')}`;
}

export const STATUS_ORDER: Record<string, number> = {
  Applied: 0,
  Assessment: 1,
  Interview: 2,
  Offer: 3,
  Rejected: 4,
  [NEEDS_REVIEW]: 5,
};

export function isTracked(app: Application): boolean {
  return app.status !== NEEDS_REVIEW;
}

export type DateRange = '30' | '60' | '90' | 'all';

export const DATE_RANGES: { value: DateRange; label: string }[] = [
  { value: '30', label: 'Last 30 days' },
  { value: '60', label: 'Last 60 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

export interface Filters {
  status: string | null;
  range: DateRange;
  noReply: boolean;
  query: string;
}

export function matchesQuery(app: Application, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [app.company, app.role, app.location].some((field) => field?.toLowerCase().includes(q));
}

export function applyFilters(apps: Application[], filters: Filters, now: Date = new Date()): Application[] {
  const since = filters.range === 'all' ? null : now.getTime() - Number(filters.range) * 24 * 60 * 60 * 1000;
  return apps.filter((app) => {
    if (filters.status && app.status !== filters.status) return false;
    if (filters.noReply && app.no_reply_days == null) return false;
    if (since !== null) {
      const applied = toDate(app.applied_date);
      if (!applied || applied.getTime() < since) return false;
    }
    return matchesQuery(app, filters.query);
  });
}

export function statusSummary(apps: Application[]): string {
  const counts = new Map<string, number>();
  for (const app of apps) counts.set(app.status, (counts.get(app.status) ?? 0) + 1);
  return BOARD_STATUSES.filter((status) => (counts.get(status) ?? 0) > 0)
    .map((status) => `${counts.get(status)} ${status.toLowerCase()}`)
    .join(' · ');
}

export function heldText(app: Pick<Application, 'interview_date' | 'no_news_days'>): string {
  return `Interview held ${shortDate(app.interview_date)} · no news for ${plural(app.no_news_days ?? 0, 'day')}`;
}
