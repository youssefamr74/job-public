/**
 * Made-up sample data for the demo. Every company, person and address is invented; email domains
 * use .example. Dates are relative to the moment the page loads, so the demo always looks current.
 */
import type { EmailContent, Notification, Opportunity, SyncRun } from '../api/types';
import { DAY, type DemoApp, type HistoryEvent } from './model';

const COMPANIES = [
  'Larkspur Analytics', 'Quillfield', 'Harborline Logistics', 'Oakmere Health', 'Tessellate', 'Bramblecode',
  'Fernhollow Energy', 'Kestrel Systems', 'Marrowbank', 'Copperleaf Studio', 'Driftwood Labs', 'Silverpine Insurance',
  'Lumenward', 'Juniper Row', 'Saltmarsh Media', 'Halcyon Freight', 'Veldt Robotics', 'Orchard Lane Retail',
  'Pebblestone Finance', 'Wrenfield', 'Ashgrove Clinics', 'Cobaltline', 'Tidepool Software', 'Granite & Fig',
  'Northdeck', 'Emberly', 'Ridgeback Security', 'Quietwater Bank', 'Lanternfish Games', 'Foxglove Bio',
  'Ironbark Construction', 'Meadowlark Travel', 'Thistle Data', 'Wavecrest Telecom', 'Hollowbrook Foods',
  'Starling Mobility', 'Cindervale', 'Bluecairn', 'Otterly Pay', 'Parchment & Co', 'Sablewood', 'Glasshouse Analytics',
  'Riverbend Logistics', 'Solace Health', 'Umberfield', 'Westmoor Capital', 'Yarrow Labs', 'Zephyrine', 'Aldergate',
  'Brackenridge', 'Cloudberry', 'Dunmore Systems', 'Elmstead', 'Fairhaven Labs', 'Gullwing', 'Heronsgate',
  'Inkwell Media', 'Jetty Data', 'Kingfisher Grid', 'Loamworks',
];

// Titles as employers write them. Analytics groups them by core title, so "Senior Data Analyst (m/w/d)" counts
// as Data Analyst. "BI Developer" and "Business Intelligence Developer" stay apart until the user merges them.
const ROLES = [
  'Data Analyst', 'Senior Data Analyst (m/w/d)', 'Data Engineer', 'Analytics Engineer', 'Junior Data Analyst',
  'Data Engineer - Remote', 'Position: Product Analyst', 'Analytics Engineer | Hybrid', 'BI Developer', 'Data Scientist',
  'Data Analyst, Berlin', 'Business Intelligence Developer', 'Data-Engineer (w/m/d)',
];
const LOCATIONS = ['Berlin', 'Remote', 'Hamburg', 'Munich', 'Amsterdam', 'Remote (EU)', 'Cologne', null];

const NEEDS_REVIEW = [2, 7, 13, 21, 30, 44];
const UPCOMING: Record<number, number> = { 5: 1, 11: 3, 18: 6 };
const HELD: Record<number, number> = { 16: 2, 25: 5, 33: 9 };
const INTERVIEW_NO_DATE = [27];
const OFFER = [38, 47];
const ASSESSMENT = [4, 9, 15, 23, 36, 52];
const REJECTED = [8, 12, 19, 22, 26, 29, 31, 35, 40, 43, 46, 50, 54, 57, 59];
const MANUAL = [14, 41, 55];

function random(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const slug = (company: string) => company.toLowerCase().replace(/&/g, 'and').replace(/[^a-z]+/g, '');

export interface DemoData {
  apps: DemoApp[];
  messages: Map<string, EmailContent>;
  opportunities: Opportunity[];
  notifications: Notification[];
  runs: SyncRun[];
}

export function seed(now = Date.now()): DemoData {
  const rand = random(20261111);
  const int = (min: number, max: number) => min + Math.floor(rand() * (max - min + 1));
  const messages = new Map<string, EmailContent>();
  let counter = 0;
  const iso = (t: number) => new Date(t).toISOString();
  const latest = now - 2 * 60 * 60 * 1000;
  const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

  function message(date: number, subject: string, sender: string, body: string): HistoryEvent & { at: number } {
    counter += 1;
    const messageId = (0x18c4a2b0000 + counter * 977).toString(16);
    messages.set(messageId, { id: messageId, subject, sender, date: iso(date), body });
    return { date: iso(date), status: '', subject, message_id: messageId, at: date };
  }

  const apps: DemoApp[] = COMPANIES.map((company, i) => {
    const role = ROLES[int(0, ROLES.length - 1)] ?? 'Data Analyst';
    const domain = `${slug(company)}.example`;
    const sender = `${company} Recruiting <careers@${domain}>`;
    const appliedDaysAgo = Math.min(1 + Math.floor(i * 1.25) + int(0, 1), 78);
    const applied = new Date(now - appliedDaysAgo * DAY);
    applied.setHours(int(8, 21), int(0, 59), 0, 0);
    const appliedAt = Math.min(applied.getTime(), latest);
    const history: HistoryEvent[] = [];
    const add = (offsetDays: number, status: string, subject: string, body: string) => {
      const previous = history.at(-1);
      const floor = previous ? new Date(previous.date).getTime() + DAY / 3 : appliedAt;
      const at = Math.min(Math.max(appliedAt + offsetDays * DAY + int(1, 8) * 3600_000, floor), latest);
      const event = message(at, subject, sender, body);
      history.push({ date: event.date, status, subject, message_id: event.message_id });
    };

    const app: DemoApp = {
      id: id(i + 1),
      company,
      role,
      status: 'Applied',
      applied_date: iso(appliedAt),
      source: MANUAL.includes(i) ? 'manual' : 'gmail',
      notes: null,
      interview_date: null,
      location: LOCATIONS[int(0, LOCATIONS.length - 1)] ?? null,
      raw_metadata: { history, edits: [] },
      action_needed: false,
      manually_modified: MANUAL.includes(i),
    };

    if (NEEDS_REVIEW.includes(i)) return reviewItem(app, i, appliedAt, message);

    if (app.source === 'gmail') {
      add(0, 'Applied', `Thank you for applying – ${role}`, applyBody(company, role));
    }

    const assessment = () =>
      add(int(3, 7), 'Assessment', `Next step: online assessment for ${role}`, assessmentBody(company, role));
    const invite = () => add(int(3, 6), 'Interview', `Interview invitation – ${role}`, inviteBody(company, role));

    if (ASSESSMENT.includes(i)) {
      app.status = 'Assessment';
      assessment();
      if (i === 9) {
        app.action_needed = true;
        app.notes = 'Take-home due Friday. Use the sample dataset they sent.';
      }
    } else if (i in UPCOMING) {
      app.status = 'Interview';
      if (i !== 5) assessment();
      invite();
      const at = new Date(now + (UPCOMING[i] ?? 1) * DAY);
      at.setHours([10, 14, 11][Object.keys(UPCOMING).indexOf(String(i))] ?? 10, 0, 0, 0);
      app.interview_date = iso(at.getTime());
    } else if (i in HELD) {
      app.status = 'Interview';
      assessment();
      invite();
      const at = new Date(now - (HELD[i] ?? 2) * DAY);
      at.setHours(15, 30, 0, 0);
      app.interview_date = iso(at.getTime());
    } else if (INTERVIEW_NO_DATE.includes(i)) {
      app.status = 'Interview';
      invite();
    } else if (OFFER.includes(i)) {
      app.status = 'Offer';
      assessment();
      invite();
      add(int(7, 12), 'Offer', `Your offer from ${company}`, offerBody(company, role));
      app.notes = i === 38 ? 'Offer call went well. Ask about the learning budget.' : null;
    } else if (REJECTED.includes(i)) {
      app.status = 'Rejected';
      if (i % 4 === 0) assessment();
      if (i % 6 === 1) invite();
      add(int(4, 16), 'Rejected', `Update on your application for ${role}`, rejectBody(company, role));
    }
    if (i === 3) app.notes = 'Referred by a former colleague.';
    return app;
  });

  const opportunities = outreach(now, message);
  const runs = syncRuns(now);
  return { apps, messages, opportunities, notifications: notifications(apps, now), runs };
}

type MakeMessage = (date: number, subject: string, sender: string, body: string) => HistoryEvent & { at: number };

const REVIEW_EMAILS = [
  {
    sender: (c: string) => `Mira Okafor <mira.okafor@${slug(c)}.example>`,
    subject: 'Quick question about your application',
    suggested: 'Interview',
    body: (c: string, r: string) =>
      `Hi,\n\nThanks for your interest in the ${r} role at ${c}. Before we move forward, would you have 20 minutes this week for a short call? I'd like to hear more about your recent projects.\n\nLet me know a few times that work for you.\n\nBest,\nMira`,
  },
  {
    sender: (c: string) => `${c} Talent <talent@${slug(c)}.example>`,
    subject: 'Your application status',
    suggested: 'Rejected',
    body: (c: string, r: string) =>
      `Hello,\n\nWe wanted to give you an update on the ${r} position. The role has changed in scope, and we are reviewing all open applications again. We'll be in touch if there is a match.\n\nKind regards,\nThe ${c} team`,
  },
  {
    sender: (c: string) => `Jonas Reiter <j.reiter@${slug(c)}.example>`,
    subject: 'Coffee chat next week?',
    suggested: 'Interview',
    body: (c: string) =>
      `Hi there,\n\nI saw you applied to ${c} and I'm on the hiring team. Would you like an informal coffee chat next week? No preparation needed.\n\nCheers,\nJonas`,
  },
  {
    sender: () => 'Hiring Team <jobs@talentmail.example>',
    subject: 'We received your documents',
    suggested: 'Applied',
    unknown: true,
    body: () =>
      `Dear applicant,\n\nThis confirms that we received your documents. Our client will review them and contact you if your profile fits.\n\nThis mailbox is not monitored.`,
  },
  {
    sender: (c: string) => `${c} Careers <no-reply@${slug(c)}.example>`,
    subject: 'Complete your candidate profile to continue',
    suggested: 'Assessment',
    body: (c: string, r: string) =>
      `Hello,\n\nTo continue with your application for ${r}, please complete your candidate profile and the short questionnaire within 5 days.\n\n${c} Careers`,
  },
  {
    sender: (c: string) => `Priya Lindqvist <priya@${slug(c)}.example>`,
    subject: 'Re: Data role',
    suggested: null,
    body: (c: string) =>
      `Hi,\n\nThanks for getting back to me. I've shared your CV with the team at ${c}. I'll let you know what they say.\n\nPriya`,
  },
];

function reviewItem(app: DemoApp, i: number, appliedAt: number, message: MakeMessage): DemoApp {
  const template = REVIEW_EMAILS[NEEDS_REVIEW.indexOf(i)];
  if (!template) return app;
  const company = app.company ?? '';
  const role = app.role ?? '';
  const sender = template.sender(company);
  const body = template.body(company, role);
  const event = message(appliedAt, template.subject, sender, body);
  return {
    ...app,
    status: 'Needs Review',
    company: template.unknown ? 'Unknown' : app.company,
    role: template.unknown || i === 44 ? 'Unknown' : app.role,
    location: null,
    raw_metadata: {
      history: [{ date: event.date, status: 'Needs Review', subject: template.subject, message_id: event.message_id }],
      edits: [],
      sender,
      subject: template.subject,
      snippet: body.replace(/\s+/g, ' ').slice(0, 140),
      ...(template.suggested ? { classifier_result: { status: template.suggested } } : {}),
    },
  };
}

const applyBody = (c: string, r: string) =>
  `Hi,\n\nThank you for applying for the ${r} position at ${c}. We have received your application and our team will review it carefully.\n\nIf your experience matches what we're looking for, we'll contact you about next steps. This usually takes one to two weeks.\n\nBest regards,\n${c} Recruiting`;
const assessmentBody = (c: string, r: string) =>
  `Hi,\n\nThanks again for your interest in ${c}. As the next step for the ${r} role, we'd like you to complete a short online assessment. It takes about 60 minutes and covers SQL and a small data case.\n\nPlease finish it within 7 days using the link in your candidate portal.\n\nGood luck!\n${c} Recruiting`;
const inviteBody = (c: string, r: string) =>
  `Hi,\n\nWe enjoyed reviewing your application and would like to invite you to an interview for the ${r} role. You'll meet two people from the team for about 45 minutes.\n\nPlease pick a time in the scheduling link. Let us know if you need any adjustments.\n\nBest,\n${c} Recruiting`;
const offerBody = (c: string, r: string) =>
  `Hi,\n\nWe're delighted to offer you the position of ${r} at ${c}! The written offer with salary and start date is attached to this email.\n\nPlease let us know if you have any questions. We'd love to have you on the team.\n\nWarm regards,\n${c} People Team`;
const rejectBody = (c: string, r: string) =>
  `Hi,\n\nThank you for your time and interest in the ${r} role at ${c}. After careful consideration, we've decided to move forward with other candidates whose experience more closely matches our needs.\n\nWe'll keep your details on file and wish you the best in your search.\n\nKind regards,\n${c} Recruiting`;

function outreach(now: number, message: MakeMessage): Opportunity[] {
  const items = [
    ['Selin Arda', 'Brightmoor Partners', 'Analytics Engineer opportunity – remote', 1, 'open'],
    ['Tomas Vela', 'Corvid Search', 'Senior Data Analyst role at a fintech scale-up', 3, 'open'],
    ['Hannah Ito', 'Palisade Health', 'Your profile caught my eye', 6, 'open'],
    ['Ruairi Byrne', 'Northgale Talent', 'Data Engineer (Python, dbt) – Hamburg', 9, 'open'],
    ['Lena Moritz', 'Fieldstone Robotics', 'Would you be open to a chat?', 15, 'open'],
    ['Oskar Wahl', 'Grayling Agency', 'Contract BI role, 6 months', 21, 'dismissed'],
  ] as const;
  return items.map(([person, company, subject, ago, status], index) => {
    const sender = `${person} <${person.split(' ')[0]?.toLowerCase()}@${slug(company)}.example>`;
    const event = message(
      now - ago * DAY - 3 * 3600_000,
      subject,
      sender,
      `Hi,\n\nI'm ${person.split(' ')[0]}, a recruiter at ${company}. I came across your profile and think you could be a great fit for a role we're hiring for. It's a hybrid position with a small, friendly data team.\n\nWould you be open to a 15-minute call this week?\n\nBest,\n${person}`,
    );
    return {
      id: `00000000-0000-4000-9000-${String(index + 1).padStart(12, '0')}`,
      company,
      role: subject.match(/(Analytics Engineer|Data Analyst|Data Engineer|BI)/)?.[0] ?? null,
      sender,
      subject,
      date: event.date,
      thread_id: `t-${event.message_id}`,
      message_id: event.message_id,
      status,
      application_id: null,
    };
  });
}

function notifications(apps: DemoApp[], now: number): Notification[] {
  const list: Notification[] = [];
  const kinds: Record<string, [string, string]> = {
    Rejected: ['rejection', 'Rejection from'],
    Interview: ['interview', 'Interview invite from'],
    Assessment: ['assessment', 'Assessment from'],
    Offer: ['offer', 'Offer from'],
  };
  for (const app of apps) {
    for (const event of app.raw_metadata.history) {
      const kind = kinds[event.status];
      if (!kind || now - new Date(event.date).getTime() > 12 * DAY) continue;
      list.push({
        id: '', kind: kind[0], title: `${kind[1]} ${app.company}`, body: app.role, link: `/applications?id=${app.id}`,
        application_id: app.id, created_at: event.date, read_at: null,
      });
    }
  }
  const tomorrow = apps.find((a) => a.id.endsWith('000000000006'));
  if (tomorrow) {
    list.push({
      id: '', kind: 'interview_tomorrow', title: `Interview with ${tomorrow.company} tomorrow at 10:00`, body: tomorrow.role,
      link: `/applications?id=${tomorrow.id}`, application_id: tomorrow.id, created_at: new Date(now - 3 * 3600_000).toISOString(), read_at: null,
    });
  }
  list.push(
    {
      id: '', kind: 'no_reply', title: '6 applications have had no reply for 14 days or more',
      body: 'A short follow-up can help, or let them go.', link: '/applications?noreply=1', application_id: null,
      created_at: new Date(now - 2 * DAY).toISOString(), read_at: null,
    },
    {
      id: '', kind: 'weekly_summary', title: 'Last week: 6 applied, 4 replies, 2 interviews', body: null, link: '/analytics',
      application_id: null, created_at: new Date(now - 4 * DAY).toISOString(), read_at: new Date(now - 4 * DAY).toISOString(),
    },
  );
  list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return list.map((n, index) => ({
    ...n,
    id: `00000000-0000-4000-a000-${String(index + 1).padStart(12, '0')}`,
    read_at: n.read_at ?? (index >= 5 ? n.created_at : null),
  }));
}

function syncRuns(now: number): SyncRun[] {
  return [12, 42, 72, 102, 132, 1440].map((minutes, index) => {
    const started = now - minutes * 60_000;
    return {
      id: `00000000-0000-4000-b000-${String(index + 1).padStart(12, '0')}`,
      trigger: index === 5 ? 'manual' : 'scheduled',
      status: 'succeeded',
      started_at: new Date(started).toISOString(),
      finished_at: new Date(started + 9_000 + index * 1_300).toISOString(),
      stage: null,
      progress_done: 0,
      progress_total: null,
      funnel: { fetched: [4, 2, 0, 7, 3, 41][index], saved_new: [1, 0, 0, 2, 0, 5][index], updated_existing: [1, 1, 0, 2, 1, 9][index], needs_review: [0, 0, 0, 1, 0, 2][index] },
      summary: null,
      error_code: null,
      error_message: null,
      cancel_requested: false,
    };
  });
}
