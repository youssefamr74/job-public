import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { AnalyticsOverview, Application, RoleGroups, SyncStatus } from '../api/types';
import { handlers, resetDemo } from './handlers';
import { roleMinimum } from './model';
import { coreTitle, notARole, roleGroup, tidyRole } from './roleGroups';
import synonyms from './role_synonyms.json';
import words from './role_words.json';
import { seed } from './seed';

const server = setupServer(...handlers);
const url = (path: string) => `${location.origin}${path}`;

async function call<T = unknown>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  const response = await fetch(url(path), {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  });
  const text = await response.text();
  return { status: response.status, body: (text ? JSON.parse(text) : undefined) as T };
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  vi.useRealTimers();
  resetDemo();
});
afterAll(() => server.close());

describe('sample data', () => {
  const data = seed();

  it('has about 60 applications in every status', () => {
    expect(data.apps).toHaveLength(60);
    for (const status of ['Applied', 'Assessment', 'Interview', 'Offer', 'Rejected', 'Needs Review']) {
      expect(data.apps.filter((app) => app.status === status).length).toBeGreaterThan(1);
    }
  });

  it('has upcoming and past interviews', () => {
    const now = Date.now();
    const dates = data.apps.flatMap((app) => (app.interview_date ? [new Date(app.interview_date).getTime()] : []));
    expect(dates.filter((d) => d > now).length).toBeGreaterThanOrEqual(3);
    expect(dates.filter((d) => d < now).length).toBeGreaterThanOrEqual(3);
  });

  it('has an email body behind every email, and only made-up addresses', () => {
    const ids = [
      ...data.apps.flatMap((app) => app.raw_metadata.history.map((e) => e.message_id)),
      ...data.opportunities.map((o) => o.message_id),
    ];
    for (const id of ids) expect(data.messages.get(id ?? '')?.body).toBeTruthy();
    for (const message of data.messages.values()) expect(message.sender).toMatch(/@[a-z.]+\.example>$/);
  });

  it('has no event in the future', () => {
    const now = Date.now();
    for (const app of data.apps) {
      for (const event of app.raw_metadata.history) expect(new Date(event.date).getTime()).toBeLessThanOrEqual(now);
    }
  });
});

describe('demo API', () => {
  it('serves the applications with the derived fields', async () => {
    const { body } = await call<Application[]>('/applications/');
    expect(body).toHaveLength(60);
    expect(body.some((app) => app.no_reply_days !== null)).toBe(true);
    expect(body.some((app) => app.needs_followup)).toBe(true);
    expect(body.every((app) => Array.isArray(app.timeline))).toBe(true);
  });

  it('keeps changes in memory until reset', async () => {
    const [first] = (await call<Application[]>('/applications/')).body;
    const changed = await call<Application>(`/applications/${first?.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'Offer' }) });
    expect(changed.body.status).toBe('Offer');
    expect(changed.body.timeline.at(-1)?.subject).toBe('Status changed by you');
    expect((await call<Application>(`/applications/${first?.id}`)).body.status).toBe('Offer');
    resetDemo();
    expect((await call<Application>(`/applications/${first?.id}`)).body.status).not.toBe('Offer');
  });

  it('simulates a short sync that adds an application', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    expect((await call('/applications/sync', { method: 'POST' })).status).toBe(200);
    expect((await call('/applications/sync', { method: 'POST' })).status).toBe(409);
    expect((await call<SyncStatus>('/sync/status')).body.running_run?.stage).toBe('fetching');
    vi.setSystemTime(Date.now() + 10_000);
    const status = (await call<SyncStatus>('/sync/status')).body;
    expect(status.running_run).toBeNull();
    expect(status.last_run?.status).toBe('succeeded');
    expect((await call<Application[]>('/applications/')).body).toHaveLength(61);
  });

  it('answers the email for a review item', async () => {
    const apps = (await call<Application[]>('/applications/')).body;
    const review = apps.find((app) => app.status === 'Needs Review');
    const history = review?.raw_metadata?.history as { message_id: string }[];
    const message = await call<{ body: string }>(`/mail/messages/${history[0]?.message_id}`);
    expect(message.body.body).toContain('Hi');
  });

  it('refuses mail and AI changes, and anything it doesn’t know', async () => {
    for (const [path, method] of [['/mail/imap', 'POST'], ['/ai/config', 'POST'], ['/applications/ai-review', 'POST'], ['/companion/chat', 'POST']]) {
      const response = await call<{ detail: string }>(path ?? '', { method, body: '{}' });
      expect(response.status).toBe(400);
      expect(response.body.detail).toBe('Not available in the demo');
    }
  });
});

describe('role groups', () => {
  it('uses the same role words as the backend', () => {
    const files = import.meta.glob<{ default: unknown }>('../../../backend/constants/role_words.json', { eager: true });
    const backend = Object.values(files)[0];
    expect(backend).toBeDefined();
    expect(words).toEqual(backend?.default);
  });

  it('cleans roles and rejects text that is not a role, like the backend', () => {
    expect(tidyRole('Position: Registered Nurse')).toBe('Registered Nurse');
    expect(tidyRole('Role of Accountant:')).toBe('Accountant');
    expect(tidyRole('Programme Manager')).toBe('Programme Manager');
    expect(tidyRole('Sales_Marketing Coordinator')).toBe('Sales / Marketing Coordinator');
    for (const text of [
      'Please contact us if you have any questions', 'Bitte senden Sie uns Ihre Unterlagen', 'Working student', 'Werkstudent',
      'Digital', 'Master Data', 'Sprzedaż', 'Data and Analytics Center of Excellence',
    ]) {
      expect(notARole(text), text).toBe(true);
      expect(roleGroup(text), text).toBeNull();
    }
    for (const text of ['Nurse', 'Barista', 'Księgowa', 'Krankenpfleger', 'Marketing Internship', 'Marketing (Intern)', 'Head of Sales']) {
      expect(notARole(text), text).toBe(false);
    }
    expect(roleGroup('Brightwave', 'Brightwave')).toBeNull();
    expect(coreTitle('Programme: Graduate Civil Engineer - London')).toBe('Civil Engineer');
    expect([0, 150, 151, 1000].map(roleMinimum)).toEqual([3, 3, 4, 20]);
  });

  it('uses the same synonyms as the backend', () => {
    // A glob, so the web app still type-checks where the backend folder isn't there (the Docker build).
    const files = import.meta.glob<{ default: unknown }>('../../../backend/constants/role_synonyms.json', { eager: true });
    const backend = Object.values(files)[0];
    expect(backend).toBeDefined();
    expect(synonyms).toEqual(backend?.default);
  });

  it('groups titles of one job the way the backend does', () => {
    const same = [
      ['Registered Nurse', 'Senior Registered Nurse (Night Shift)', 'RN', 'Registered Nurse - Remote'],
      ['Accountant', 'Lead Accountant - London', 'Accountant #REQ-48213', 'Accountant II'],
      ['Full-Stack Developer', 'Fullstack Developer', 'Senior full stack developer'],
      ['Księgowy', 'Księgowa', 'Młodszy Księgowy / Młodsza Księgowa'],
      ['Softwareentwickler', 'Softwareentwickler*in', 'Software-Entwickler (m/w/d) Vollzeit'],
      ['Marketing Intern', 'Werkstudent Marketing (w/m/d)', 'Praktykant - Marketing'],
      ['Infirmier', 'Infirmière', 'Infirmier H/F'],
    ];
    for (const titles of same) {
      const groups = new Set(titles.map((title) => roleGroup(title)));
      expect(groups.size, titles.join(' / ')).toBe(1);
      expect(groups.has(null)).toBe(false);
    }
    expect(roleGroup('Team Lead')).not.toBe(roleGroup('Accountant'));
    expect(roleGroup('Mid-Market Account Executive')).not.toBe(roleGroup('Account Executive'));
    expect(coreTitle('Senior Nurse (m/w/d) - Berlin')).toBe('Nurse');
    expect(roleGroup('Unknown')).toBeNull();
  });

  it('merges groups, counts single applications elsewhere and undoes merges', async () => {
    const before = (await call<RoleGroups>('/analytics/role-groups')).body;
    expect(before.groups.map((g) => g.key)).toEqual(expect.arrayContaining(['bi developer', 'business intelligence developer', 'data analyst']));

    const merged = await call('/analytics/role-groups/merge', {
      method: 'POST', body: JSON.stringify({ source: 'business intelligence developer', target: 'bi developer' }),
    });
    expect(merged.status).toBe(204);
    const rows = (await call<AnalyticsOverview>('/analytics/overview?range=all')).body.by_role;
    const bi = rows.find((row) => row.key === 'bi developer');
    expect(bi?.merged).toEqual([{ key: 'business intelligence developer', label: 'Business Intelligence Developer' }]);
    expect(rows.some((row) => row.key === 'business intelligence developer')).toBe(false);

    const [first] = (await call<Application[]>('/applications/')).body.filter((a) => a.status !== 'Needs Review');
    const counted = await call<Application>(`/applications/${first?.id}/metadata`, {
      method: 'PATCH', body: JSON.stringify({ role_group_override: 'Data Analyst' }),
    });
    expect(counted.body.role_group_override).toBe('Data Analyst');
    expect(counted.body.manually_modified).toBe(false);

    expect((await call(`/analytics/role-groups/merge?source=${encodeURIComponent('business intelligence developer')}`, { method: 'DELETE' })).status).toBe(204);
    const after = (await call<AnalyticsOverview>('/analytics/overview?range=all')).body.by_role;
    expect(after.some((row) => row.key === 'business intelligence developer')).toBe(true);
  });

  it('groups the sample roles by core title, most applications first', async () => {
    const overview = (await call<AnalyticsOverview>('/analytics/overview?range=all')).body;
    const rows = overview.by_role;
    expect(overview.role_min_applications).toBe(3);
    expect(rows.map((row) => row.applied)).toEqual([...rows.map((row) => row.applied)].sort((a, b) => b - a));
    expect(rows.find((row) => row.titles.some((t) => t.title === 'Position: Product Analyst'))?.key).toBe('product analyst');
    const analyst = rows.find((row) => row.key === 'data analyst');
    expect(analyst?.enough).toBe(true);
    expect(analyst?.titles.map((t) => t.title)).toEqual(expect.arrayContaining(['Senior Data Analyst (m/w/d)', 'Data Analyst, Berlin']));
    expect(rows.find((row) => row.key === 'data engineer')?.titles.map((t) => t.title)).toContain('Data-Engineer (w/m/d)');
  });
});
