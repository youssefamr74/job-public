import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { daysAgo, mockApi, renderWithProviders } from '../../test/utils';
import { TodayOverview } from './TodayOverview';

const today = {
  coming_up: [{ id: 'a1', company: 'Northwind Labs', role: 'Data Engineer', date: '2026-11-13T14:00:00', days: null }],
  attention: [
    { id: 'a2', company: 'Brightwave', role: 'Backend', reason: 'interview_held', date: daysAgo(3), days: 3 },
    { id: 'a3', company: 'Pracuj', role: 'Unknown', reason: 'action_needed', date: null, days: null },
    { id: 'a4', company: 'Kestrel Pay', role: 'Java Developer', reason: 'no_reply', date: null, days: 39 },
  ],
  this_week: { applied: 14, replies: 6, interviews: 1 },
};

describe('TodayOverview', () => {
  it('shows coming interviews, what needs attention and the week numbers', async () => {
    mockApi({ 'GET /applications/today': today });
    renderWithProviders(<TodayOverview onOpen={vi.fn()} />);

    const coming = (await screen.findByRole('heading', { name: 'Coming up' })).parentElement as HTMLElement;
    expect(within(coming).getByText('Northwind Labs · Data Engineer')).toBeInTheDocument();
    expect(within(coming).getByText('Fri 13 Nov, 14:00')).toBeInTheDocument();

    expect(screen.getByText(/Interview held .* · no news for 3 days/)).toBeInTheDocument();
    expect(screen.getByText('Pracuj')).toBeInTheDocument();
    expect(screen.getByText('The employer is waiting for something from you')).toBeInTheDocument();
    expect(screen.getByText('No reply · 39 days')).toBeInTheDocument();

    const week = screen.getByRole('heading', { name: 'This week' }).parentElement as HTMLElement;
    expect(within(week).getByText('14')).toBeInTheDocument();
    expect(within(week).getByText('replies')).toBeInTheDocument();
  });

  it('opens an application from any item', async () => {
    const onOpen = vi.fn();
    mockApi({ 'GET /applications/today': today });
    renderWithProviders(<TodayOverview onOpen={onOpen} />);
    await userEvent.click(await screen.findByRole('button', { name: /Kestrel Pay/ }));
    expect(onOpen).toHaveBeenCalledWith('a4');
  });

  it('says so when there is nothing to show', async () => {
    mockApi({ 'GET /applications/today': { coming_up: [], attention: [], this_week: { applied: 0, replies: 0, interviews: 0 } } });
    renderWithProviders(<TodayOverview onOpen={vi.fn()} />);
    expect(await screen.findByText('No interviews scheduled.')).toBeInTheDocument();
    expect(screen.getByText('Nothing needs you right now.')).toBeInTheDocument();
  });
});
