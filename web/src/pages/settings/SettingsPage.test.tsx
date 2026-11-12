import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { daysAgo, mockApi, renderWithProviders } from '../../test/utils';
import { SettingsPage } from './SettingsPage';

const providers = [
  { id: 'anthropic', name: 'Anthropic', default_base_url: 'https://api.anthropic.com/v1', needs_api_key: true, supports_batch: true },
  { id: 'ollama', name: 'Ollama (local)', default_base_url: 'http://localhost:11434/v1', needs_api_key: false, supports_batch: false },
];

const run = {
  id: 'r1', trigger: 'manual', status: 'failed', started_at: daysAgo(0), finished_at: daysAgo(0), stage: 'fetching',
  progress_done: 0, progress_total: null, funnel: { fetched: 12, saved_new: 3, updated_existing: 2, needs_review: 1 },
  summary: null, error_code: 'mail_unreachable', error_message: 'Couldn’t reach Gmail.', cancel_requested: false,
};

function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    'GET /mail/status': { status: 'connected', source: 'imap', email: 'me@gmail.com', connected_at: daysAgo(10) },
    'GET /ai/status': { configured: false, pending_batches: 0, has_api_key: false },
    'GET /ai/providers': providers,
    'GET /settings/sync': { interval_minutes: 60 },
    'GET /sync/status': { running_run: null, last_run: run },
    'GET /sync/runs': [run],
    'GET /debug/dropped': { total: 42, by_reason: {}, items: [] },
    'GET /health': { status: 'ok', version: '0.1.0' },
    ...extra,
  });
}

function section(name: string) {
  return screen.getByRole('region', { name });
}

describe('SettingsPage', () => {
  it('shows mail status and tests the connection', async () => {
    const { calls } = api({ 'POST /mail/test': { ok: true, email: 'me@gmail.com' } });
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    const mail = section('Mail');
    expect(await within(mail).findByText('me@gmail.com')).toBeInTheDocument();
    expect(within(mail).getByText('App password')).toBeInTheDocument();
    expect(within(mail).getByText('Connected')).toBeInTheDocument();
    await userEvent.click(within(mail).getByRole('button', { name: 'Test connection' }));
    expect(await within(mail).findByText('Works. Signed in as me@gmail.com.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.url === '/mail/test')).toBe(true);
  });

  it('switches method by showing the other connection form', async () => {
    api();
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    const mail = section('Mail');
    await userEvent.click(await within(mail).findByRole('button', { name: 'Switch to your own Google Cloud client' }));
    expect(within(mail).getByLabelText('Client ID')).toBeInTheDocument();
    expect(within(mail).queryByLabelText('App password')).not.toBeInTheDocument();
  });

  it('disconnects after confirming', async () => {
    const { calls } = api({ 'DELETE /mail': { disconnected: true, revoked: null } });
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    await userEvent.click(await within(section('Mail')).findByRole('button', { name: 'Disconnect' }));
    const dialog = await screen.findByRole('dialog', { name: 'Disconnect Gmail?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url === '/mail')).toBe(true));
  });

  it('says plainly that AI is not configured, then loads models and saves', async () => {
    const { calls } = api({
      'POST /ai/models': { models: [{ id: 'model-a', name: 'Model A' }] },
      'POST /ai/config': { configured: true, provider: 'anthropic', model: 'model-a', has_api_key: true, pending_batches: 0 },
    });
    renderWithProviders(<SettingsPage />, { route: '/settings#ai' });
    const ai = section('AI');
    expect(await within(ai).findByText('Not configured.')).toBeInTheDocument();
    await userEvent.type(within(ai).getByLabelText('API key'), 'sk-test');
    await userEvent.click(within(ai).getByRole('button', { name: 'Load models' }));
    await waitFor(() => expect(within(ai).getByLabelText('Model')).toHaveValue('model-a'));
    await userEvent.click(within(ai).getByRole('radio', { name: /Subject, sender and the start/ }));
    await userEvent.click(within(ai).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/ai/config')).toBe(true));
    expect(calls.find((c) => c.url === '/ai/config')?.body).toMatchObject({
      provider: 'anthropic', model: 'model-a', api_key: 'sk-test', privacy_mode: 'with_body', use_batch: true,
    });
    expect(calls.find((c) => c.url === '/ai/models')?.body).toEqual({ provider: 'anthropic', api_key: 'sk-test' });
  });

  it('lists the last sync runs with their numbers and error', async () => {
    const { calls } = api({ 'PUT /settings/sync': { interval_minutes: 360 } });
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    const sync = section('Sync');
    const table = await within(sync).findByRole('table');
    const row = within(table).getAllByRole('row')[1] as HTMLElement;
    expect(within(row).getByText('Failed')).toBeInTheDocument();
    expect(within(row).getByText('12')).toBeInTheDocument();
    expect(within(row).getByText('Couldn’t reach Gmail.')).toBeInTheDocument();
    expect(calls.find((c) => c.url.startsWith('/sync/runs'))?.url).toBe('/sync/runs?limit=10');
    await waitFor(() => expect(within(sync).getByLabelText('Sync automatically')).toHaveValue('60'));
    await userEvent.selectOptions(within(sync).getByLabelText('Sync automatically'), '360');
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ interval_minutes: 360 }));
  });

  it('offers exports and deletes everything only after typing DELETE', async () => {
    const { calls } = api({ 'POST /data/delete-all': { deleted: true } });
    const { router } = renderWithProviders(<SettingsPage />, { route: '/settings' });
    const data = section('Data');
    expect(within(data).getByRole('link', { name: 'Download CSV' })).toHaveAttribute('href', '/data/export/applications.csv');
    expect(within(data).getByRole('link', { name: 'Download JSON' })).toHaveAttribute('href', '/data/export/applications.json');
    expect(await within(data).findByText(/42 emails logged/)).toBeInTheDocument();

    await userEvent.click(within(data).getByRole('button', { name: 'Delete all data' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete all data?' });
    const confirm = within(dialog).getByRole('button', { name: 'Delete everything' });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/to confirm/), 'delete');
    expect(confirm).toBeDisabled();
    await userEvent.clear(within(dialog).getByLabelText(/to confirm/));
    await userEvent.type(within(dialog).getByLabelText(/to confirm/), 'DELETE');
    await userEvent.click(confirm);
    await waitFor(() => expect(router.state.location.pathname).toBe('/setup'));
    expect(calls.find((c) => c.url === '/data/delete-all')?.body).toEqual({ confirm: 'DELETE' });
  });

  it('shows the version and links', async () => {
    api();
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    const about = section('About');
    expect(await within(about).findByText('0.1.0')).toBeInTheDocument();
    expect(within(about).getByRole('link', { name: 'GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/youssefamr74/job-public',
    );
  });
});
