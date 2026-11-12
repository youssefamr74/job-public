/**
 * The demo's API, answered in the browser by MSW. Changes live in memory and are gone on reload.
 * Anything the demo doesn't cover answers 404, so no request leaves the page.
 */
import { delay, http, HttpResponse, type JsonBodyType } from 'msw';
import type { ApplicationCreate, ApplicationMetadataUpdate, ApplicationUpdate, InterviewOutcome, Opportunity, SyncRun } from '../api/types';
import { NOT_IN_DEMO } from '../lib/demo';
import { DAY, overview, present, roleGroups, today, type DemoApp } from './model';
import { groupKey, resolve } from './roleGroups';
import { seed } from './seed';

const VERSION = '0.1.0';
const SYNC_MS = 4200;

let data = seed();
let sync: { run: SyncRun; startedAt: number } | null = null;
let lastSuccess = data.runs[0]?.finished_at ?? null;
let created = 0;
let syncs = 0;
let interval = 30;
let dropped = 37;
// Role group merges: source group -> target group.
let merges = new Map<string, string>();

const NEW_FROM_SYNC = [
  ['Moorhen Analytics', 'Data Analyst'],
  ['Pinecrest Labs', 'Analytics Engineer'],
  ['Quarry Street', 'Data Engineer'],
] as const;

const json = (body: JsonBodyType, status = 200) => HttpResponse.json(body, { status });
const notFound = (detail = 'Not found') => json({ detail }, 404);
const newId = () => {
  created += 1;
  return `00000000-0000-4000-c000-${String(created).padStart(12, '0')}`;
};
const find = (id: unknown) => data.apps.find((app) => app.id === id);
const apps = () => data.apps.map((app) => present(app));

function edit(app: DemoApp, field: string, from: string | null, to: string | null) {
  app.raw_metadata.edits.push({ date: new Date().toISOString(), field, from, to });
  app.manually_modified = true;
}

/** Advances the simulated sync; returns the run while it's still going. */
function runningSync(): SyncRun | null {
  if (!sync) return null;
  const elapsed = Date.now() - sync.startedAt;
  const run = sync.run;
  if (elapsed < SYNC_MS * 0.35) {
    Object.assign(run, { stage: 'fetching', progress_done: Math.round((elapsed / (SYNC_MS * 0.35)) * 6), progress_total: null });
  } else if (elapsed < SYNC_MS * 0.8) {
    Object.assign(run, { stage: 'classifying', progress_done: Math.min(6, Math.round(((elapsed - SYNC_MS * 0.35) / (SYNC_MS * 0.45)) * 6)), progress_total: 6 });
  } else if (elapsed < SYNC_MS) {
    Object.assign(run, { stage: 'saving', progress_done: 6, progress_total: 6 });
  } else {
    finishSync(run);
    return null;
  }
  return { ...run };
}

function finishSync(run: SyncRun) {
  const next = NEW_FROM_SYNC[syncs];
  syncs += 1;
  const finished = new Date().toISOString();
  if (next) {
    const [company, role] = next;
    const messageId = (0x19a000000 + created * 31).toString(16);
    const subject = `Thank you for applying – ${role}`;
    const sender = `${company} Recruiting <careers@${company.toLowerCase().replace(/[^a-z]+/g, '')}.example>`;
    data.messages.set(messageId, {
      id: messageId, subject, sender, date: finished,
      body: `Hi,\n\nThank you for applying for the ${role} position at ${company}. We've received your application and will be in touch within two weeks.\n\nBest regards,\n${company} Recruiting`,
    });
    data.apps.unshift({
      id: newId(), company, role, status: 'Applied', applied_date: finished, source: 'gmail', notes: null,
      interview_date: null, location: 'Remote', action_needed: false, manually_modified: false,
      raw_metadata: { history: [{ date: finished, status: 'Applied', subject, message_id: messageId }], edits: [] },
    });
  }
  Object.assign(run, {
    status: 'succeeded', finished_at: finished, stage: null, progress_done: 0, progress_total: null,
    funnel: { fetched: 6, saved_new: next ? 1 : 0, updated_existing: 1, needs_review: 0 },
  });
  data.runs.unshift(run);
  lastSuccess = finished;
  sync = null;
}

function startSync() {
  if (runningSync()) return json({ detail: 'A sync is already running' }, 409);
  const run: SyncRun = {
    id: newId(), trigger: 'manual', status: 'running', started_at: new Date().toISOString(), finished_at: null,
    stage: 'fetching', progress_done: 0, progress_total: null, funnel: null, summary: null,
    error_code: null, error_message: null, cancel_requested: false,
  };
  sync = { run, startedAt: Date.now() };
  return json({ run_id: run.id });
}

function opportunityFrom(app: DemoApp): Opportunity {
  const meta = app.raw_metadata;
  const last = meta.history.at(-1);
  return {
    id: newId(), company: app.company, role: app.role, sender: meta.sender ?? null, subject: meta.subject ?? last?.subject ?? null,
    date: last?.date ?? app.applied_date, thread_id: null, message_id: last?.message_id ?? null, status: 'open', application_id: null,
  };
}

const notAvailable = () => json({ detail: NOT_IN_DEMO }, 400);

export const handlers = [
  http.all('*', async ({ request }) => {
    // A small pause, so the demo feels like a real app; page files pass through untouched.
    if (new URL(request.url).origin === location.origin && !request.url.includes('/demo/')) await delay(120);
  }),

  http.get('/health', () => json({ status: 'ok', version: VERSION })),
  http.get('/setup/status', () =>
    json({ mail: 'connected', mail_source: 'imap', mail_email: 'demo@example.com', ai_configured: false, first_sync_done: true, sync_running: Boolean(runningSync()), last_sync_at: lastSuccess }),
  ),
  http.get('/mail/status', () =>
    json({ status: 'connected', source: 'imap', email: 'demo@example.com', last_error: null, connected_at: new Date(Date.now() - 80 * DAY).toISOString(), updated_at: lastSuccess }),
  ),
  http.get('/mail/messages/:id', ({ params }) => {
    const message = data.messages.get(String(params.id));
    return message ? json({ ...message }) : json({ detail: { code: 'message_gone', message: 'This email is no longer in your mailbox.' } }, 404);
  }),
  http.get('/ai/status', () => json({ configured: false, has_api_key: false, pending_batches: 0 })),
  http.get('/ai/providers', () => json([])),
  http.post('/applications/ai-review', notAvailable),
  http.post('/analytics/role-groups/suggest', notAvailable),

  http.get('/applications/', () => json(apps())),
  http.get('/applications/today', () => json(today(apps()))),
  http.post('/applications/sync', startSync),
  http.post('/applications/', async ({ request }) => {
    const body = (await request.json()) as ApplicationCreate;
    const app: DemoApp = {
      id: newId(), company: body.company, role: body.role, status: body.status,
      applied_date: body.applied_date ?? new Date().toISOString(), source: 'manual', notes: null, interview_date: null,
      location: null, raw_metadata: { history: [], edits: [] }, action_needed: false, manually_modified: true,
    };
    data.apps.unshift(app);
    return json(present(app), 201);
  }),
  http.get('/applications/:id', ({ params }) => {
    const app = find(params.id);
    return app ? json(present(app)) : notFound('Application not found');
  }),
  http.patch('/applications/:id', async ({ params, request }) => {
    const app = find(params.id);
    if (!app) return notFound('Application not found');
    const body = (await request.json()) as ApplicationUpdate;
    if (body.status && body.status !== app.status) {
      edit(app, 'status', app.status, body.status);
      app.status = body.status;
    }
    if (body.notes !== undefined && body.notes !== null) app.notes = body.notes || null;
    if (body.action_needed !== undefined && body.action_needed !== null) app.action_needed = body.action_needed;
    return json(present(app));
  }),
  http.patch('/applications/:id/metadata', async ({ params, request }) => {
    const app = find(params.id);
    if (!app) return notFound('Application not found');
    const body = (await request.json()) as ApplicationMetadataUpdate;
    for (const field of ['company', 'role'] as const) {
      const value = body[field];
      if (value !== undefined && value !== null && value !== app[field]) {
        edit(app, field, app[field], value);
        app[field] = value;
      }
    }
    if (body.interview_date !== undefined) app.interview_date = body.interview_date;
    if (body.role_group_override !== undefined) {
      app.role_group_override = (body.role_group_override ?? '').split(/\s+/).filter(Boolean).join(' ') || null;
    }
    if (body.raw_metadata) Object.assign(app.raw_metadata, body.raw_metadata);
    return json(present(app));
  }),
  http.delete('/applications/:id', ({ params }) => {
    data.apps = data.apps.filter((app) => app.id !== params.id);
    return json({ deleted: true });
  }),
  http.post('/applications/:id/interview-outcome', async ({ params, request }) => {
    const app = find(params.id);
    if (!app) return notFound('Application not found');
    const { outcome } = (await request.json()) as { outcome: InterviewOutcome };
    if (outcome === 'rejected' || outcome === 'offer') {
      const status = outcome === 'rejected' ? 'Rejected' : 'Offer';
      edit(app, 'status', app.status, status);
      app.status = status;
    } else if (outcome === 'next_round') {
      edit(app, 'interview', app.interview_date, null);
      app.interview_date = null;
    } else {
      app.raw_metadata.followup_snoozed_until = new Date(Date.now() + 7 * DAY).toISOString();
    }
    return json(present(app));
  }),
  http.post('/applications/:id/not-job', ({ params }) => {
    data.apps = data.apps.filter((app) => app.id !== params.id);
    return new HttpResponse(null, { status: 204 });
  }),
  http.post('/applications/:id/to-opportunity', ({ params }) => {
    const app = find(params.id);
    if (!app) return notFound('Application not found');
    const opportunity = opportunityFrom(app);
    data.opportunities.unshift(opportunity);
    data.apps = data.apps.filter((a) => a.id !== app.id);
    return json(opportunity);
  }),

  http.get('/opportunities/', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status');
    return json(data.opportunities.filter((o) => !status || o.status === status));
  }),
  http.post('/opportunities/:id/convert', ({ params }) => {
    const opportunity = data.opportunities.find((o) => o.id === params.id);
    if (!opportunity) return notFound('Opportunity not found');
    const history = opportunity.message_id
      ? [{ date: opportunity.date ?? new Date().toISOString(), status: 'Applied', subject: opportunity.subject ?? '', message_id: opportunity.message_id }]
      : [];
    const app: DemoApp = {
      id: newId(), company: opportunity.company, role: opportunity.role ?? 'Unknown', status: 'Applied',
      applied_date: new Date().toISOString(), source: 'gmail', notes: null, interview_date: null, location: null,
      raw_metadata: { history, edits: [] }, action_needed: false, manually_modified: true,
    };
    data.apps.unshift(app);
    Object.assign(opportunity, { status: 'converted', application_id: app.id });
    return json(present(app));
  }),
  http.post('/opportunities/:id/dismiss', ({ params }) => {
    const opportunity = data.opportunities.find((o) => o.id === params.id);
    if (!opportunity) return notFound('Opportunity not found');
    opportunity.status = 'dismissed';
    return json(opportunity);
  }),

  http.get('/analytics/overview', ({ request }) => {
    const range = new URL(request.url).searchParams.get('range');
    return json(overview(apps(), range === '60' || range === 'all' ? range : '30', Date.now(), merges));
  }),
  http.get('/analytics/role-groups', () => json(roleGroups(apps(), merges))),
  http.post('/analytics/role-groups/merge', async ({ request }) => {
    const body = (await request.json()) as { source: string; target: string };
    const source = groupKey(body.source);
    const target = groupKey(body.target);
    if (!source || !target || source === target) return json({ detail: 'Pick two different groups' }, 422);
    if (resolve(target, merges) === source) return json({ detail: 'That group is already merged into this one' }, 409);
    merges.set(source, target);
    return new HttpResponse(null, { status: 204 });
  }),
  http.delete('/analytics/role-groups/merge', ({ request }) => {
    const source = groupKey(new URL(request.url).searchParams.get('source'));
    if (!source || !merges.delete(source)) return notFound("That group isn't merged");
    return new HttpResponse(null, { status: 204 });
  }),
  http.get('/analytics/weekly-review', () => {
    const t = today(apps());
    const monday = new Date();
    monday.setHours(0, 0, 0, 0);
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    const day = (d: Date) => d.toISOString().slice(0, 10);
    return json({
      week_start: day(monday), week_end: day(new Date(monday.getTime() + 6 * DAY)),
      applications_this_week: t.this_week.applied, applications_last_week: 6, responses_this_week: t.this_week.replies,
      interviews_this_week: t.this_week.interviews, ai_configured: false, goals_met_this_week: 3, streak: 4,
    });
  }),

  http.get('/notifications/', ({ request }) => {
    const limit = Number(new URL(request.url).searchParams.get('limit') ?? 50);
    return json(data.notifications.slice(0, limit));
  }),
  http.get('/notifications/unread-count', () => json({ unread: data.notifications.filter((n) => !n.read_at).length })),
  http.post('/notifications/read-all', () => {
    const unread = data.notifications.filter((n) => !n.read_at);
    unread.forEach((n) => (n.read_at = new Date().toISOString()));
    return json({ marked: unread.length });
  }),
  http.post('/notifications/:id/read', ({ params }) => {
    const notification = data.notifications.find((n) => n.id === params.id);
    if (!notification) return notFound('Notification not found');
    notification.read_at ??= new Date().toISOString();
    return json(notification);
  }),

  http.get('/sync/status', () => {
    const running = runningSync();
    return json({ running_run: running, last_run: data.runs[0] ?? null, last_success_at: lastSuccess, next_scheduled_at: new Date(Date.now() + 18 * 60_000).toISOString() });
  }),
  http.get('/sync/runs', ({ request }) => {
    const limit = Number(new URL(request.url).searchParams.get('limit') ?? 10);
    const running = runningSync();
    return json([...(running ? [running] : []), ...data.runs].slice(0, limit));
  }),
  http.get('/settings/sync', () => json({ interval_minutes: interval })),
  http.put('/settings/sync', async ({ request }) => {
    interval = ((await request.json()) as { interval_minutes: number }).interval_minutes;
    return json({ interval_minutes: interval });
  }),

  http.get('/debug/dropped', () => json({ total: dropped, by_reason: dropped ? { job_alert: 21, social: 9, filtered_out: 7 } : {}, items: [] })),
  http.delete('/debug/dropped', () => {
    const deleted = dropped;
    dropped = 0;
    return json({ deleted });
  }),
  http.post('/data/delete-all', () => {
    data = { apps: [], messages: new Map(), opportunities: [], notifications: [], runs: [] };
    merges = new Map();
    lastSuccess = null;
    return json({ deleted: true });
  }),

  // Mail, AI and everything else need the real app.
  http.all(
    new RegExp(`^${location.origin}/(mail|ai|setup|users|companion|goals|cv|debug|data|settings|sync|applications|opportunities|notifications|analytics|docs|openapi[.]json)([/?]|$)`),
    notAvailable,
  ),
];

/** Back to the sample data, as after a reload. Used by tests. */
export function resetDemo() {
  data = seed();
  sync = null;
  syncs = 0;
  lastSuccess = data.runs[0]?.finished_at ?? null;
  interval = 30;
  dropped = 37;
  merges = new Map();
}
