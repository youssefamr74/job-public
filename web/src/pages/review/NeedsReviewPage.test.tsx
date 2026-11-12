import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { daysAgo, makeApplication, mockApi, renderWithProviders } from '../../test/utils';
import { NeedsReviewPage } from './NeedsReviewPage';
import { aiReviewSummary } from '../../lib/review';

const tidewater = makeApplication({
  company: 'Tidewater',
  role: 'Master Data Intern',
  status: 'Needs Review',
  last_activity_at: daysAgo(1),
  raw_metadata: {
    subject: 'Thank you for taking part in our process',
    sender: 'Tidewater Recruiting <careers@tidewater.example>',
    classifier_result: { status: 'Assessment' },
    history: [{ message_id: '18c2a', date: daysAgo(1), subject: 'Thank you for taking part in our process' }],
  },
});
const quarry = makeApplication({
  company: 'Unknown',
  role: 'Data Engineer',
  status: 'Needs Review',
  last_activity_at: daysAgo(4),
  raw_metadata: {
    subject: 'An update about the Data Engineer role',
    sender: 'Quarry Data <talent@quarry.example>',
    history: [{ message_id: '18c2b', date: daysAgo(4) }],
  },
});
const tracked = makeApplication({ company: 'Northwind Labs', status: 'Applied' });

const email = {
  id: '18c2a',
  subject: 'Thank you for taking part in our process',
  sender: 'Tidewater Recruiting <careers@tidewater.example>',
  date: daysAgo(1),
  body: 'Hi Jordan,\n\nThank you for the time you spent with us.\n\nBest regards,\nTidewater Recruiting',
};

function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    'GET /applications/': [tidewater, quarry, tracked],
    'GET /mail/messages/18c2a': email,
    'GET /mail/messages/18c2b': { ...email, id: '18c2b', subject: 'An update about the Data Engineer role', body: 'Hello.' },
    'GET /ai/status': { configured: false },
    ...extra,
  });
}

describe('NeedsReviewPage', () => {
  it('lists the queue and shows the selected email with the rules’ guess', async () => {
    api();
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    const queue = await screen.findByRole('list', { name: 'Emails to review' });
    expect(within(queue).getAllByRole('button').map((b) => b.textContent)).toEqual([
      expect.stringContaining('Tidewater Recruiting'),
      expect.stringContaining('Quarry Data'),
    ]);
    expect(await screen.findByText('Thank you for the time you spent with us.')).toBeInTheDocument();
    expect(screen.getByText('Best regards,', { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText('Company')).toHaveValue('Tidewater');
    expect(screen.getByLabelText('Role')).toHaveValue('Master Data Intern');
    expect(screen.getByRole('button', { name: 'Assessment' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('saves with Enter after picking a status with a number key, then moves on', async () => {
    const { calls } = api({
      [`PATCH /applications/${tidewater.id}`]: { ...tidewater, status: 'Interview' },
    });
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    await screen.findByText('Thank you for the time you spent with us.');
    await userEvent.keyboard('3');
    expect(screen.getByRole('button', { name: 'Interview' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.keyboard('{Enter}');
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')).toMatchObject({ body: { status: 'Interview' } }),
    );
    expect(calls.some((c) => c.url.includes('/metadata'))).toBe(false);
    expect(await screen.findByLabelText('Company')).toHaveValue('');
    expect(screen.getByLabelText('Role')).toHaveValue('Data Engineer');
  });

  it('saves an edited company before the status', async () => {
    const { calls } = api({
      [`PATCH /applications/${quarry.id}/metadata`]: { ...quarry, company: 'Quarry Data' },
      [`PATCH /applications/${quarry.id}`]: { ...quarry, company: 'Quarry Data', status: 'Rejected' },
    });
    renderWithProviders(<NeedsReviewPage />, { route: `/review?id=${quarry.id}` });
    await userEvent.type(await screen.findByLabelText('Company'), 'Quarry Data');
    await userEvent.click(screen.getByRole('button', { name: 'Rejected' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save and next' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2));
    const [metadata, status] = calls.filter((c) => c.method === 'PATCH');
    expect(metadata).toMatchObject({ body: { company: 'Quarry Data' } });
    expect(status).toMatchObject({ body: { status: 'Rejected' } });
  });

  it('asks for a status before saving, and S skips', async () => {
    const { calls } = api();
    renderWithProviders(<NeedsReviewPage />, { route: `/review?id=${quarry.id}` });
    await screen.findByText('Hello.');
    await userEvent.click(screen.getByRole('button', { name: 'Save and next' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Pick what this email is first.');
    await userEvent.keyboard('s');
    expect(await screen.findByText('Thank you for the time you spent with us.')).toBeInTheDocument();
    expect(calls.some((c) => c.method !== 'GET')).toBe(false);
  });

  it('removes a non-job email and moves recruiter outreach to opportunities', async () => {
    const { calls } = api({
      [`POST /applications/${tidewater.id}/not-job`]: { status: 200 },
      [`POST /applications/${quarry.id}/to-opportunity`]: { id: 'o1', status: 'open' },
    });
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    await screen.findByText('Thank you for the time you spent with us.');
    await userEvent.click(screen.getByRole('button', { name: 'Not a job email' }));
    expect(await screen.findByText('Hello.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'It’s a recruiter reaching out' }));
    expect(await screen.findByText('Nothing to review.')).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url)).toEqual([
      `/applications/${tidewater.id}/not-job`,
      `/applications/${quarry.id}/to-opportunity`,
    ]);
  });

  it('explains how to set up AI when it isn’t configured', async () => {
    const { calls } = api();
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    await userEvent.click(await screen.findByRole('button', { name: 'Review all with AI' }));
    expect(screen.getByText(/AI isn’t set up/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings › AI' })).toHaveAttribute('href', '/settings#ai');
    expect(calls.some((c) => c.url.includes('ai-review'))).toBe(false);
  });

  it('runs the AI review when AI is configured', async () => {
    api({
      'GET /ai/status': { configured: true, provider: 'openai', model: 'gpt' },
      'POST /applications/ai-review': {
        checked: 2, updated: 1, unchanged: 0, not_job: 1, not_job_items: [], failed: 0,
        skipped_manual: 0, no_message: 0, queued_in_batch: 0,
      },
    });
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    const button = await screen.findByRole('button', { name: 'Review all with AI' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText('Checked 2 emails: 1 sorted out, 1 don’t look like job emails.')).toBeInTheDocument();
  });

  it('shows the email’s kept preview when the mailbox can’t be reached', async () => {
    api({ 'GET /mail/messages/18c2a': { status: 502, body: { detail: { code: 'network', message: 'Couldn’t reach Gmail.' } } } });
    renderWithProviders(<NeedsReviewPage />, { route: '/review' });
    expect(await screen.findByText('Couldn’t load the email. Couldn’t reach Gmail.')).toBeInTheDocument();
  });
});

describe('aiReviewSummary', () => {
  it('describes a batch', () => {
    expect(
      aiReviewSummary({
        checked: 40, updated: 0, unchanged: 0, not_job: 0, not_job_items: [], failed: 0,
        skipped_manual: 0, no_message: 0, queued_in_batch: 40,
      }),
    ).toBe('Sent 40 emails to your AI as a batch. The answers come in with a later sync.');
  });
});
