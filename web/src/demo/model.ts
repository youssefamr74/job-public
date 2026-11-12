/**
 * The demo's in-memory records and the fields the backend works out from them (no-reply days,
 * progress, timeline, Today, Analytics). Kept close to backend/applications/schemas.py,
 * backend/applications/today.py and backend/analytics/overview.py.
 */
import type { AnalyticsOverview, AnalyticsRange, Application, RoleGroupRow, RoleGroups, TimelineEvent, Today } from '../api/types';
import { effectiveGroup, groupLabels, labelFor, roleGroup } from './roleGroups';

export const DAY = 24 * 60 * 60 * 1000;

export interface HistoryEvent {
  date: string;
  status: string;
  subject: string;
  message_id: string;
}

export interface EditEvent {
  date: string;
  field: string;
  from: string | null;
  to: string | null;
}

export interface Meta {
  history: HistoryEvent[];
  edits: EditEvent[];
  sender?: string;
  subject?: string;
  snippet?: string;
  classifier_result?: { status: string };
  followup_snoozed_until?: string;
  [key: string]: unknown;
}

export interface DemoApp {
  id: string;
  company: string | null;
  role: string | null;
  status: string;
  applied_date: string | null;
  source: string;
  notes: string | null;
  interview_date: string | null;
  location: string | null;
  raw_metadata: Meta;
  action_needed: boolean;
  manually_modified: boolean;
  role_group_override?: string | null;
}

const NO_REPLY_STATUSES = new Set(['Applied', 'Assessment']);
const RESPONSE_STATUSES = new Set(['Assessment', 'Interview', 'Offer', 'Rejected']);
const PROGRESS_STEP: Record<string, number> = { Applied: 1, 'Needs Review': 1, Assessment: 2, Interview: 3, Offer: 4 };

const time = (value: string | null | undefined): number | null => {
  if (!value) return null;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? null : t;
};

const days = (from: number, to: number) => Math.floor((to - from) / DAY);

export function present(app: DemoApp, now = Date.now()): Application {
  const { history, edits } = app.raw_metadata;
  const dates = [...history, ...edits].map((e) => time(e.date)).filter((t): t is number => t !== null);
  const applied = time(app.applied_date);
  if (applied !== null) dates.push(applied);
  const lastActivity = dates.length ? Math.max(...dates) : null;

  const quiet = lastActivity === null ? 0 : days(lastActivity, now);
  const noReply = NO_REPLY_STATUSES.has(app.status) && lastActivity !== null && quiet >= 14 ? quiet : null;

  const interview = time(app.interview_date);
  const held = app.status === 'Interview' && interview !== null && interview < now;
  const since = Math.max(interview ?? 0, ...history.map((e) => time(e.date) ?? 0));
  const noNews = held ? Math.max(days(since, now), 0) : null;
  const snoozed = time(app.raw_metadata.followup_snoozed_until);

  const statuses = [app.status, ...history.map((e) => e.status)];
  for (const edit of edits) if (edit.field === 'status') statuses.push(edit.from ?? '', edit.to ?? '');
  let step = Math.max(...statuses.map((s) => PROGRESS_STEP[s] ?? 1));
  if (app.interview_date) step = Math.max(step, 3);

  return {
    ...app,
    role_group: roleGroup(app.role, app.company),
    role_group_override: app.role_group_override ?? null,
    email_count: history.length,
    last_activity_at: lastActivity === null ? null : new Date(lastActivity).toISOString(),
    no_reply_days: noReply,
    interview_held: held,
    no_news_days: noNews,
    followup_snoozed_until: app.raw_metadata.followup_snoozed_until ?? null,
    needs_followup: held && !(snoozed !== null && snoozed > now),
    progress_step: step,
    timeline: timeline(app),
  };
}

function timeline(app: DemoApp): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  let previous: string | null = null;
  for (const event of app.raw_metadata.history) {
    const change = previous === null ? event.status : event.status !== previous ? `${previous} to ${event.status}` : null;
    previous = event.status;
    events.push({ date: event.date, kind: 'email', subject: event.subject, change });
  }
  for (const edit of app.raw_metadata.edits) {
    if (edit.field === 'interview') {
      events.push({ date: edit.date, kind: 'edit', subject: 'Interview went on to a next round' });
      continue;
    }
    const label = edit.field === 'status' ? 'Status changed by you' : `${edit.field[0]?.toUpperCase()}${edit.field.slice(1)} edited by you`;
    events.push({ date: edit.date, kind: 'edit', subject: label, change: `${edit.from || 'empty'} to ${edit.to || 'empty'}` });
  }
  return events.sort((a, b) => (time(a.date) ?? 0) - (time(b.date) ?? 0));
}

function weekStart(now: number): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.getTime();
}

export function today(apps: Application[], now = Date.now()): Today {
  const tracked = apps.filter((a) => a.status !== 'Needs Review');
  const start = weekStart(now);
  const end = start + 7 * DAY;
  const item = (a: Application) => ({ id: a.id, company: a.company, role: a.role });

  const upcoming = tracked
    .filter((a) => (time(a.interview_date) ?? -1) >= now && a.status !== 'Rejected' && a.status !== 'Offer')
    .sort((a, b) => (time(a.interview_date) ?? 0) - (time(b.interview_date) ?? 0));
  const held = tracked.filter((a) => a.needs_followup).sort((a, b) => (time(a.interview_date) ?? 0) - (time(b.interview_date) ?? 0));
  const waiting = tracked.filter((a) => a.no_reply_days != null).sort((a, b) => (b.no_reply_days ?? 0) - (a.no_reply_days ?? 0));
  const inWeek = (value: string | null | undefined) => {
    const t = time(value);
    return t !== null && t >= start && t < end;
  };

  return {
    coming_up: upcoming.slice(0, 5).map((a) => ({ ...item(a), date: a.interview_date })),
    attention: [
      ...held.map((a) => ({ ...item(a), reason: 'interview_held' as const, date: a.interview_date, days: a.no_news_days })),
      ...tracked.filter((a) => a.action_needed).map((a) => ({ ...item(a), reason: 'action_needed' as const, date: a.last_activity_at })),
      ...waiting.slice(0, 5).map((a) => ({ ...item(a), reason: 'no_reply' as const, date: a.last_activity_at, days: a.no_reply_days })),
    ],
    this_week: {
      applied: tracked.filter((a) => inWeek(a.applied_date)).length,
      replies: tracked.reduce((n, a) => n + history(a).filter((e) => RESPONSE_STATUSES.has(e.status) && inWeek(e.date)).length, 0),
      interviews: tracked.filter((a) => inWeek(a.interview_date)).length,
    },
  };
}

function history(app: Application): HistoryEvent[] {
  return ((app.raw_metadata as Meta | null)?.history ?? []) as HistoryEvent[];
}

function statusEvents(app: Application): { at: number; status: string }[] {
  const meta = app.raw_metadata as Meta | null;
  const events = (meta?.history ?? []).map((e) => ({ at: time(e.date) ?? 0, status: e.status }));
  for (const edit of meta?.edits ?? []) {
    if (edit.field === 'status') events.push({ at: time(edit.date) ?? 0, status: edit.to ?? '' });
  }
  return events.sort((a, b) => a.at - b.at);
}

const replied = (app: Application) =>
  RESPONSE_STATUSES.has(app.status) || app.progress_step >= 2 || statusEvents(app).some((e) => RESPONSE_STATUSES.has(e.status));

function daysToReply(app: Application): number | null {
  const applied = time(app.applied_date);
  if (applied === null) return null;
  let seenBefore = app.source === 'manual';
  for (const event of statusEvents(app)) {
    if (RESPONSE_STATUSES.has(event.status)) return seenBefore && event.at >= applied ? (event.at - applied) / DAY : null;
    seenBefore = true;
  }
  return null;
}

const rate = (part: number, whole: number) => (whole ? Math.round((part / whole) * 1000) / 10 : null);

const isoDay = (t: number) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? (sorted[mid] ?? 0) : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

/** Response rate per role group, like role_rows in backend/analytics/overview.py. */
/** Smaller groups fold into "Other roles": at least 3 applications, or 2% of them with more data. */
export const roleMinimum = (total: number) => Math.max(3, Math.ceil(total * 0.02));

export function roleRows(apps: Application[], merges: Map<string, string>, labels: Map<string, string>, minimum = 3): RoleGroupRow[] {
  const groups = new Map<string | null, Application[]>();
  for (const app of apps) {
    const key = effectiveGroup(app.role, app.role_group_override, merges, app.company);
    groups.set(key, [...(groups.get(key) ?? []), app]);
  }
  const rows: RoleGroupRow[] = [];
  for (const [key, members] of groups) {
    const titles = new Map<string, { title: string; apps: Application[] }>();
    for (const app of members) {
      const raw = (app.role ?? '').split(/\s+/).filter(Boolean).join(' ');
      const title = raw && raw.toLowerCase() !== 'unknown' ? raw : 'No role found';
      const entry = titles.get(title.toLowerCase()) ?? { title, apps: [] };
      entry.apps.push(app);
      titles.set(title.toLowerCase(), entry);
    }
    const count = members.filter(replied).length;
    rows.push({
      key,
      label: labelFor(key, labels),
      applied: members.length,
      replied: count,
      response_rate: rate(count, members.length),
      enough: members.length >= minimum,
      titles: [...titles.values()]
        .map(({ title, apps: list }) => ({ title, applied: list.length, replied: list.filter(replied).length }))
        .sort((a, b) => b.applied - a.applied || a.title.localeCompare(b.title)),
      merged:
        key === null
          ? []
          : [...merges].filter(([, target]) => target === key).map(([source]) => ({ key: source, label: labelFor(source, labels) }))
              .sort((a, b) => a.label.localeCompare(b.label)),
    });
  }
  return rows.sort(
    (a, b) => b.applied - a.applied || Number(a.key === null) - Number(b.key === null) || a.label.localeCompare(b.label),
  );
}

export function roleGroups(apps: Application[], merges: Map<string, string>): RoleGroups {
  const tracked = apps.filter((a) => a.status !== 'Needs Review');
  const labels = groupLabels(tracked);
  const counts = new Map<string, number>();
  for (const app of tracked) {
    const key = effectiveGroup(app.role, app.role_group_override, merges, app.company);
    if (key !== null) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return {
    groups: [...counts]
      .map(([key, applied]) => ({ key, label: labelFor(key, labels), applied }))
      .sort((a, b) => b.applied - a.applied || a.label.localeCompare(b.label)),
    merges: [...merges].map(([source, target]) => ({
      source, source_label: labelFor(source, labels), target, target_label: labelFor(target, labels),
    })),
  };
}

export function overview(apps: Application[], range: AnalyticsRange, now = Date.now(), merges = new Map<string, string>()): AnalyticsOverview {
  const midnight = new Date(now);
  midnight.setHours(0, 0, 0, 0);
  const todayStart = midnight.getTime();
  const since = range === 'all' ? null : todayStart - (Number(range) - 1) * DAY;
  const dayOf = (t: number) => {
    const d = new Date(t);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  };
  const tracked = apps
    .filter((a) => a.status !== 'Needs Review' && time(a.applied_date) !== null)
    .map((a) => ({ app: a, day: dayOf(time(a.applied_date) ?? 0) }))
    .filter(({ day }) => since === null || day >= since);

  const total = tracked.length;
  const firstDay = since ?? Math.min(todayStart, ...tracked.map((t) => t.day));
  const weeksSpan = Math.max((Math.round((todayStart - firstDay) / DAY) + 1) / 7, 1);
  const answered = tracked.filter(({ app }) => replied(app));
  const timings = answered.map(({ app }) => daysToReply(app)).filter((d): d is number => d !== null);

  const first = weekStart(firstDay);
  const last = weekStart(todayStart);
  const weeks = Math.min(Math.round((last - first) / (7 * DAY)) + 1, 52);
  const starts = Array.from({ length: weeks }, (_, i) => weekStart(last - (weeks - 1 - i) * 7 * DAY + DAY));
  const perWeek = starts.map((start) => ({
    week_start: isoDay(start),
    count: tracked.filter(({ day }) => weekStart(day) === start).length,
  }));

  const steps = [
    ['Applied', total],
    ['Got a reply', answered.length],
    ['Assessment', tracked.filter(({ app }) => app.progress_step >= 2).length],
    ['Interview', tracked.filter(({ app }) => app.progress_step >= 3).length],
    ['Offer', tracked.filter(({ app }) => app.progress_step >= 4).length],
  ] as const;

  const minimum = roleMinimum(total);
  const byRole = roleRows(tracked.map((t) => t.app), merges, groupLabels(apps), minimum);

  const byWeekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label, index) => {
    const members = tracked.filter(({ day }) => (new Date(day).getDay() + 6) % 7 === index).map((t) => t.app);
    const count = members.filter(replied).length;
    const enough = members.length >= 10;
    return { label, applied: members.length, replied: count, response_rate: enough ? rate(count, members.length) : null, enough };
  });

  return {
    range,
    since: since === null ? null : isoDay(since),
    headline: {
      applications: total,
      per_week: Math.round((total / weeksSpan) * 10) / 10,
      replied: answered.length,
      response_rate: rate(answered.length, total),
      median_days_to_reply: timings.length ? Math.round(median(timings) * 10) / 10 : null,
      replies_timed: timings.length,
      goal_days_met: 4,
      goal_days: 7,
      daily_goal: 3,
    },
    per_week: perWeek,
    funnel: steps.map(([step, count]) => ({ step, count, rate: rate(count, total) })),
    by_role: byRole,
    role_min_applications: minimum,
    by_weekday: byWeekday,
  };
}
