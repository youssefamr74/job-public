import { afterEach, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { SetupStatus } from '../../api/types';
import { needsSetup, sinceDate } from '../../lib/setup';
import { mockApi, renderWithProviders } from '../../test/utils';
import { SetupPage } from './SetupPage';

const fresh: SetupStatus = { mail: 'none', ai_configured: false, first_sync_done: false, sync_running: false };
const connected: SetupStatus = { ...fresh, mail: 'connected', mail_source: 'imap', mail_email: 'me@gmail.com' };
const providers = [
  { id: 'anthropic', name: 'Anthropic', default_base_url: 'x', needs_api_key: true, supports_batch: true },
];

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe('needsSetup', () => {
  it('opens the wizard only on a first run', () => {
    expect(needsSetup(fresh)).toBe(true);
    expect(needsSetup(connected)).toBe(false);
    expect(needsSetup({ ...fresh, first_sync_done: true })).toBe(false);
    localStorage.setItem('job.setupDone', '1');
    expect(needsSetup(fresh)).toBe(false);
  });

  it('computes the first sync start date', () => {
    expect(sinceDate(30, new Date(2026, 10, 11))).toBe('2026-10-12');
  });
});

describe('SetupPage', () => {
  it('connects Gmail with an app password and moves to the AI step', async () => {
    const { calls } = mockApi({
      'GET /setup/status': fresh,
      'POST /mail/imap': { status: 'connected', source: 'imap', email: 'me@gmail.com' },
      'GET /ai/status': { configured: false, pending_batches: 0, has_api_key: false },
      'GET /ai/providers': providers,
    });
    const { router } = renderWithProviders(<SetupPage />, { route: '/setup' });
    expect(await screen.findByRole('heading', { name: 'Connect your Gmail' })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Gmail address'), 'me@gmail.com');
    await userEvent.type(screen.getByLabelText('App password'), 'abcd efgh ijkl mnop');
    await userEvent.click(screen.getByRole('button', { name: 'Test and continue' }));
    await waitFor(() => expect(router.state.location.search).toBe('?step=ai'));
    expect(calls.find((c) => c.url === '/mail/imap')?.body).toEqual({
      email: 'me@gmail.com',
      app_password: 'abcd efgh ijkl mnop',
    });
  });

  it('shows the OAuth form with a copyable redirect URI and starts the consent', async () => {
    mockApi({
      'GET /setup/status': fresh,
      'GET /mail/oauth/redirect-uri': { redirect_uri: 'http://127.0.0.1:8000/mail/oauth/callback' },
    });
    renderWithProviders(<SetupPage />, { route: '/setup' });
    await userEvent.click(await screen.findByRole('radio', { name: /Your own Google Cloud client/ }));
    expect(await screen.findByText('http://127.0.0.1:8000/mail/oauth/callback')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy' })).toBeEnabled();
    expect(screen.getByLabelText('Client ID')).toBeInTheDocument();
    expect(screen.getByLabelText('Client secret')).toBeInTheDocument();
  });

  it('handles the OAuth return: connected goes on, an error is explained', async () => {
    mockApi({
      'GET /setup/status': connected,
      'GET /ai/status': { configured: false, pending_batches: 0, has_api_key: false },
      'GET /ai/providers': providers,
    });
    const { router } = renderWithProviders(<SetupPage />, { route: '/setup?mail=connected' });
    await waitFor(() => expect(router.state.location.search).toBe('?step=ai'));
    expect(await screen.findByRole('heading', { name: 'Add AI (optional)' })).toBeInTheDocument();
  });

  it('explains an OAuth error on the Gmail step', async () => {
    mockApi({ 'GET /setup/status': fresh, 'GET /mail/oauth/redirect-uri': { redirect_uri: 'x' } });
    renderWithProviders(<SetupPage />, { route: '/setup?mail=error&reason=access_denied' });
    expect(await screen.findByText(/Access wasn’t granted in Google/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Your own Google Cloud client/ })).toBeChecked();
  });

  it('sends a return from Settings back to Settings', async () => {
    sessionStorage.setItem('job.oauthReturn', '/settings#mail');
    mockApi({ 'GET /setup/status': connected });
    const { router } = renderWithProviders(<SetupPage />, { route: '/setup?mail=connected' });
    await waitFor(() => expect(router.state.location.pathname).toBe('/settings'));
    expect(router.state.location.state).toEqual({ mailNotice: 'Gmail is connected.', mailError: false });
  });

  it('skips AI, estimates nothing without AI, and starts the first sync with the chosen range', async () => {
    const { calls } = mockApi({
      'GET /setup/status': connected,
      'GET /ai/status': { configured: false, pending_batches: 0, has_api_key: false },
      'GET /ai/providers': providers,
      'POST /applications/sync': { run_id: 'run-1' },
      'GET /sync/status': { running_run: null, last_run: null },
    });
    const { router } = renderWithProviders(<SetupPage />, { route: '/setup?step=ai' });
    await userEvent.click(await screen.findByRole('button', { name: 'Skip' }));
    expect(await screen.findByRole('heading', { name: 'Run the first sync' })).toBeInTheDocument();
    expect(screen.queryByText('AI cost')).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('How far back'), '90');
    await userEvent.clear(screen.getByLabelText('At most this many emails'));
    await userEvent.type(screen.getByLabelText('At most this many emails'), '500');
    await userEvent.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => expect(router.state.location.search).toBe('?step=progress&run=run-1'));
    expect(calls.find((c) => c.url === '/applications/sync')?.body).toEqual({
      since_date: sinceDate(90),
      max_messages: 500,
    });
  });

  it('shows the AI cost estimate when AI is configured', async () => {
    mockApi({
      'GET /setup/status': connected,
      'GET /ai/status': { configured: true, provider: 'anthropic', model: 'm', pending_batches: 0, has_api_key: true },
      'POST /ai/estimate': {
        estimate: true, note: '', emails_checked: 400, already_processed: 0, filtered_out: 250, settled_by_rules: 120,
        would_send_to_ai: 30, privacy_mode: 'subject_sender', input_tokens: 1, output_tokens: 1, would_use_batch: false,
        provider: 'anthropic', model: 'm', price_per_million: null, estimated_cost_usd: 0.12, prices_last_checked: null,
      },
    });
    renderWithProviders(<SetupPage />, { route: '/setup?step=sync' });
    await userEvent.click(await screen.findByRole('button', { name: 'Estimate the cost' }));
    expect(
      await screen.findByText('Of 400 emails, the rules settle 120 and filter 250; 30 emails would go to your AI. About $0.12.'),
    ).toBeInTheDocument();
  });

  it('follows the run and opens Applications when it is done', async () => {
    const running = {
      id: 'run-1', trigger: 'manual', status: 'running', started_at: '2026-11-11T10:00:00Z', stage: 'classifying',
      progress_done: 40, progress_total: 160,
    };
    let done = false;
    mockApi({
      'GET /setup/status': connected,
      'GET /sync/status': () => ({
        body: done
          ? { running_run: null, last_run: { ...running, status: 'succeeded', summary: { new_applications: 12 } } }
          : { running_run: running, last_run: running },
      }),
    });
    const { router, queryClient } = renderWithProviders(<SetupPage />, { route: '/setup?step=progress&run=run-1' });
    expect(await screen.findByText('Sorting the emails · 40 of 160')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25');
    done = true;
    await queryClient.invalidateQueries({ queryKey: ['sync', 'status'] });
    expect(await screen.findByText('Found 12 applications. Opening them now…')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Go to applications' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/applications'));
    expect(localStorage.getItem('job.setupDone')).toBe('1');
  });
});
