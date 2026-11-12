import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { mockApi, renderWithProviders } from '../../test/utils';
import { Layout } from '../../components/Layout';
import { SetupPage } from '../setup/SetupPage';
import { SettingsPage } from './SettingsPage';

vi.mock('../../lib/demo', () => ({
  DEMO: true,
  NOT_IN_DEMO: 'Not available in the demo',
  REPO_URL: 'https://github.com/youssefamr74/job-public',
}));

const NOT_IN_DEMO = 'Not available in the demo';

function api() {
  return mockApi({
    'GET /mail/status': { status: 'connected', source: 'imap', email: 'demo@example.com' },
    'GET /setup/status': { mail: 'connected', ai_configured: false, first_sync_done: true, sync_running: false },
    'GET /settings/sync': { interval_minutes: 30 },
    'GET /sync/status': { running_run: null, last_run: null },
    'GET /sync/runs': [],
    'GET /debug/dropped': { total: 0, by_reason: {}, items: [] },
    'GET /health': { status: 'ok', version: '0.1.0' },
    'GET /notifications/unread-count': { unread: 0 },
  });
}

describe('demo mode', () => {
  it('shows Mail, AI and export as not available, without asking the API about them', async () => {
    const { calls } = api();
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    expect(await within(screen.getByRole('region', { name: 'Mail' })).findByText(NOT_IN_DEMO)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'AI' })).getByText(NOT_IN_DEMO)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Data' })).getByText(NOT_IN_DEMO)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'API docs' })).not.toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith('/ai/'))).toBe(false);
  });

  it('replaces the setup wizard', () => {
    api();
    renderWithProviders(<SetupPage />, { route: '/setup' });
    expect(screen.getByText(/Not available in the demo/)).toBeInTheDocument();
    expect(screen.queryByText('Connect your Gmail')).not.toBeInTheDocument();
  });

  it('shows the demo banner with a link to the repository', async () => {
    api();
    renderWithProviders(<Layout />, { route: '/applications' });
    const link = await screen.findByRole('link', { name: 'Install Jōb to use your own Gmail' });
    expect(link).toHaveAttribute('href', 'https://github.com/youssefamr74/job-public');
    expect(link.parentElement).toHaveTextContent('Demo with sample data · Install Jōb to use your own Gmail');
  });
});
