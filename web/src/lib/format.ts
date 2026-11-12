const DAY_MS = 24 * 60 * 60 * 1000;

const monthDay = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const monthDayYear = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'short' });
const dayMonth = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });

export function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function daysBetween(earlier: Date, later: Date): number {
  return Math.round((startOfDay(later) - startOfDay(earlier)) / DAY_MS);
}

/** "Oct 21", or "Oct 21, 2025" outside the current year. */
export function shortDate(value: string | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) return '—';
  return date.getFullYear() === now.getFullYear() ? monthDay.format(date) : monthDayYear.format(date);
}

/** "Today", "Yesterday", or a short date. */
export function relativeDay(value: string | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) return '—';
  const days = daysBetween(date, now);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  return shortDate(value, now);
}

/** "just now", "12 min ago", "3 h ago", "2 days ago". */
export function timeAgo(value: string | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) return '';
  const minutes = Math.floor((now.getTime() - date.getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}

/** "Thu 13 Nov, 14:00"; the time is left out at midnight, which means no time was given. */
export function interviewDate(value: string | null | undefined): string {
  const date = toDate(value);
  if (!date) return '';
  const day = `${weekday.format(date)} ${dayMonth.format(date)}`;
  const hasTime = date.getHours() !== 0 || date.getMinutes() !== 0;
  return hasTime ? `${day}, ${time.format(date)}` : day;
}

/** "Nov 9, 13:15", with the year outside the current one. */
export function emailDate(value: string | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) return '';
  return `${shortDate(value, now)}, ${time.format(date)}`;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export type DateGroup = 'Today' | 'Yesterday' | 'This week' | 'Earlier';

/** Section for a date: Today, Yesterday, This week (from Monday), or Earlier. */
export function dateGroup(value: string | null | undefined, now: Date = new Date()): DateGroup {
  const date = toDate(value);
  if (!date) return 'Earlier';
  const days = daysBetween(date, now);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  const sinceMonday = (now.getDay() + 6) % 7;
  return days <= sinceMonday ? 'This week' : 'Earlier';
}
