import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Notification } from '../api/types';
import { NotificationsPage } from '../pages/notifications/NotificationsPage';
import { daysAgo, mockApi, renderWithProviders } from '../test/utils';
import { Header } from './Header';

const rejection: Notification = {
  id: 'n1',
  kind: 'rejection',
  title: 'Rejection from Contoso',
  body: 'Data Engineer',
  link: '/applications?id=a1',
  application_id: 'a1',
  created_at: daysAgo(0),
  read_at: null,
};
const weekly: Notification = {
  ...rejection,
  id: 'n2',
  kind: 'weekly_summary',
  title: 'Last week: 14 applied, 6 replies, 1 interview',
  body: null,
  link: '/analytics',
  application_id: null,
  read_at: daysAgo(1),
};

const base = {
  'GET /applications/': [],
  'GET /opportunities/': [],
  'GET /sync/status': { running_run: null, last_run: null, next_run_at: null },
};

describe('Notifications bell', () => {
  it('shows the unread count and opens the related application', async () => {
    const { calls } = mockApi({
      ...base,
      'GET /notifications/unread-count': { unread: 1 },
      'GET /notifications/': [rejection, weekly],
      'POST /notifications/n1/read': { ...rejection, read_at: daysAgo(0) },
    });
    const { router } = renderWithProviders(<Header onSyncError={() => undefined} />, { route: '/analytics' });
    const bell = await screen.findByRole('button', { name: 'Notifications, 1 unread' });
    expect(calls.some((c) => c.url.startsWith('/notifications/?'))).toBe(false);
    await userEvent.click(bell);
    const popover = await screen.findByRole('dialog', { name: 'Notifications' });
    expect(calls.find((c) => c.url.startsWith('/notifications/?'))?.url).toBe('/notifications/?limit=10');
    await userEvent.click(await within(popover).findByRole('button', { name: /Rejection from Contoso/ }));
    await waitFor(() => expect(router.state.location.search).toBe('?id=a1'));
    expect(router.state.location.pathname).toBe('/applications');
    expect(calls.some((c) => c.method === 'POST' && c.url === '/notifications/n1/read')).toBe(true);
  });

  it('marks all read', async () => {
    const { calls } = mockApi({
      ...base,
      'GET /notifications/unread-count': { unread: 1 },
      'GET /notifications/': [rejection],
      'POST /notifications/read-all': { marked: 1 },
    });
    renderWithProviders(<Header onSyncError={() => undefined} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Mark all read' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/notifications/read-all')).toBe(true));
    expect(screen.getByRole('button', { name: /^Rejection from Contoso\. Data Engineer/ })).toBeInTheDocument();
  });
});

describe('NotificationsPage', () => {
  it('lists all notifications with the unread ones marked', async () => {
    mockApi({ 'GET /notifications/unread-count': { unread: 1 }, 'GET /notifications/': [rejection, weekly] });
    renderWithProviders(<NotificationsPage />, { route: '/notifications' });
    expect(
      await screen.findByRole('button', { name: 'Rejection from Contoso, unread. Data Engineer. just now' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Last week: 14 applied, 6 replies, 1 interview\. / })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeInTheDocument();
  });

  it('has a plain empty state', async () => {
    mockApi({ 'GET /notifications/unread-count': { unread: 0 }, 'GET /notifications/': [] });
    renderWithProviders(<NotificationsPage />, { route: '/notifications' });
    expect(await screen.findByText('No notifications yet.')).toBeInTheDocument();
  });
});
