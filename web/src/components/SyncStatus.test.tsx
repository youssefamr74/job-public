import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockApi, renderWithProviders } from '../test/utils';
import { SyncStatus } from './SyncStatus';

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const run = {
  id: 'r1',
  trigger: 'manual',
  status: 'running',
  started_at: minutesAgo(1),
  stage: 'fetching',
  progress_done: 34,
  progress_total: null,
  cancel_requested: false,
};

describe('SyncStatus', () => {
  it('shows when the last sync succeeded', async () => {
    mockApi({ 'GET /sync/status': { running_run: null, last_success_at: minutesAgo(12) } });
    renderWithProviders(<SyncStatus onError={vi.fn()} />);
    expect(await screen.findByText('Synced 12 min ago')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeEnabled();
  });

  it('shows progress while a sync runs', async () => {
    mockApi({ 'GET /sync/status': { running_run: run, last_run: run } });
    renderWithProviders(<SyncStatus onError={vi.fn()} />);
    expect(await screen.findByText('Syncing… fetched 34')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Syncing' })).toBeDisabled();
  });

  it('treats 409 as "already running" and refreshes the status', async () => {
    const onError = vi.fn();
    let statusCalls = 0;
    mockApi({
      'GET /sync/status': () => {
        statusCalls += 1;
        return { body: statusCalls === 1 ? { running_run: null, last_success_at: minutesAgo(3) } : { running_run: run } };
      },
      'POST /applications/sync': { status: 409, body: { detail: 'A sync is already running' } },
    });
    renderWithProviders(<SyncStatus onError={onError} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(await screen.findByText('Syncing… fetched 34')).toBeInTheDocument();
    expect(onError).not.toHaveBeenCalledWith(expect.any(String));
  });

  it('reports other errors, such as no mail account', async () => {
    const onError = vi.fn();
    mockApi({
      'GET /sync/status': { running_run: null },
      'POST /applications/sync': { status: 400, body: { detail: 'No mail account connected.' } },
    });
    renderWithProviders(<SyncStatus onError={onError} />);
    expect(await screen.findByText('Not synced yet')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('No mail account connected.'));
  });
});
