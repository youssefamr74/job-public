import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { AnalyticsOverview, WeeklyReview } from '../../api/types';
import { mockApi, renderWithProviders } from '../../test/utils';
import { AnalyticsPage } from './AnalyticsPage';

const overview: AnalyticsOverview = {
  range: '60',
  since: '2026-09-13',
  headline: {
    applications: 159, per_week: 18.4, replied: 54, response_rate: 34, median_days_to_reply: 9.2,
    replies_timed: 50, goal_days_met: 4, goal_days: 7, daily_goal: 5,
  },
  per_week: [
    { week_start: '2026-10-27', count: 12 },
    { week_start: '2026-11-03', count: 25 },
    { week_start: '2026-11-10', count: 7 },
  ],
  funnel: [
    { step: 'Applied', count: 159, rate: 100 },
    { step: 'Got a reply', count: 54, rate: 34 },
    { step: 'Assessment', count: 5, rate: 3.1 },
    { step: 'Interview', count: 2, rate: 1.3 },
    { step: 'Offer', count: 0, rate: 0 },
  ],
  by_role: [
    {
      key: 'data analyst', label: 'Data Analyst', applied: 18, replied: 8, response_rate: 44.4, enough: true,
      titles: [
        { title: 'Senior Data Analyst (m/w/d)', applied: 11, replied: 5 },
        { title: 'Data Analyst', applied: 7, replied: 3 },
      ],
      merged: [{ key: 'reporting analyst', label: 'Reporting Analyst' }],
    },
    {
      key: 'nurse', label: 'Nurse', applied: 12, replied: 9, response_rate: 75, enough: true,
      titles: [{ title: 'Nurse (m/w/d)', applied: 12, replied: 9 }], merged: [],
    },
    {
      key: 'bi developer', label: 'BI Developer', applied: 4, replied: 1, response_rate: 25, enough: false,
      titles: [{ title: 'BI Developer', applied: 4, replied: 1 }], merged: [],
    },
    {
      key: null, label: 'Role not found', applied: 2, replied: 0, response_rate: 0, enough: false,
      titles: [{ title: 'No role found', applied: 2, replied: 0 }], merged: [],
    },
  ],
  role_min_applications: 5,
  by_weekday: [
    { label: 'Mon', applied: 30, replied: 11, response_rate: 37.6, enough: true },
    { label: 'Sat', applied: 3, replied: 1, response_rate: null, enough: false },
  ],
};

const review: WeeklyReview = {
  week_start: '2026-11-03', week_end: '2026-11-09', applications_this_week: 14, applications_last_week: 10,
  responses_this_week: 6, interviews_this_week: 1, ai_configured: false, goals_met_this_week: 3, streak: 2,
  highlight: null, concern: null, focus_items: null,
};

describe('AnalyticsPage', () => {
  it('shows the headline numbers, charts and this week’s numbers without AI', async () => {
    mockApi({ 'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    expect(await screen.findByText('159', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('about 18 a week')).toBeInTheDocument();
    expect(screen.getByText('34%', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('54 of 159 got any reply')).toBeInTheDocument();
    expect(screen.getByText('9 days')).toBeInTheDocument();
    expect(screen.getByText('4 of 7')).toBeInTheDocument();
    expect(screen.getByText('days met this week · goal 5')).toBeInTheDocument();
    expect(screen.getByText('too few')).toBeInTheDocument();
    expect(screen.getByText('Last 3 weeks')).toBeInTheDocument();

    const week = await screen.findByRole('region', { name: 'This week' });
    expect(within(week).getByText('Interviews booked').nextSibling).toHaveTextContent('1');
    expect(within(week).queryByText(/written by your AI/)).not.toBeInTheDocument();
    expect(within(week).queryByText('Went well.')).not.toBeInTheDocument();
  });

  it('switches a chart to a table', async () => {
    mockApi({ 'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    const card = await screen.findByRole('region', { name: 'How far applications got' });
    await userEvent.click(within(card).getByRole('button', { name: 'Show as table' }));
    const table = within(card).getByRole('table', { name: 'How far applications got' });
    const row = within(table).getByRole('rowheader', { name: 'Got a reply' }).closest('tr') as HTMLElement;
    expect(within(row).getByText('54')).toBeInTheDocument();
    expect(within(row).getByText('34%')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Show as chart' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('changes the range', async () => {
    const { calls } = mockApi({ 'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    await screen.findByText('4 of 7');
    await userEvent.click(screen.getByRole('button', { name: '30 days' }));
    await waitFor(() => expect(calls.map((c) => c.url)).toContain('/analytics/overview?range=30'));
    expect(screen.getByRole('button', { name: '30 days' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows the AI’s weekly review when AI is configured', async () => {
    mockApi({
      'GET /analytics/overview': overview,
      'GET /analytics/weekly-review': {
        ...review, ai_configured: true, highlight: 'Data roles get the most replies.',
        concern: 'Eleven applications have had no reply.', focus_items: ['1. Prepare for Thursday.', 'Follow up.'],
      },
    });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    expect(await screen.findByText('Data roles get the most replies.')).toBeInTheDocument();
    expect(screen.getByText(/written by your AI/)).toBeInTheDocument();
    expect(screen.getByText('Prepare for Thursday.')).toBeInTheDocument();
  });

  it('sorts by Applied, folds small groups into Other roles and expands the exact titles', async () => {
    mockApi({
      'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review,
      'GET /ai/status': { configured: false, has_api_key: false },
      'GET /analytics/role-groups': { groups: [], merges: [] },
    });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    const card = await screen.findByRole('region', { name: 'Response rate by role' });
    const names = () => within(card).getAllByRole('button', { expanded: false }).map((b) => b.textContent);
    expect(names()).toEqual(['▸Data Analyst2 titles', '▸Nurse', '▸Other roles2 roles']);
    expect(within(card).getByText('Roles with fewer than 5 applications are grouped under Other roles.')).toBeInTheDocument();
    expect(within(card).queryByText('BI Developer')).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Suggest groups' })).not.toBeInTheDocument();

    const other = within(card).getByRole('button', { name: /Other roles/ });
    expect(other.closest('li')).toHaveTextContent('617%');
    await userEvent.click(other);
    const folded = within(card).getByRole('list', { name: 'Other roles' });
    expect(within(folded).getByText('BI Developer')).toBeInTheDocument();
    expect(within(folded).getByText('Role not found')).toBeInTheDocument();
    await userEvent.click(other);

    await userEvent.click(within(card).getByRole('button', { name: /Response rate/ }));
    expect(names()).toEqual(['▸Nurse', '▸Data Analyst2 titles', '▸Other roles2 roles']);
    await userEvent.click(within(card).getByRole('button', { name: /Response rate/ }));
    expect(names()[0]).toBe('▸Data Analyst2 titles');
    expect(within(card).getByRole('button', { name: /Response rate/ })).toHaveAccessibleName('Response rate, lowest first');

    const group = within(card).getByRole('button', { name: /Data Analyst/ });
    expect(group).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(group);
    const titles = within(card).getByRole('list', { name: 'Titles in Data Analyst' });
    expect(within(titles).getByText('Senior Data Analyst (m/w/d)')).toBeInTheDocument();
    expect(within(titles).getByText('11 · 46%')).toBeInTheDocument();
  });

  it('merges a group into another and undoes a merge', async () => {
    const { calls } = mockApi({
      'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review,
      'GET /ai/status': { configured: false, has_api_key: false },
      'GET /analytics/role-groups': {
        groups: [
          { key: 'data analyst', label: 'Data Analyst', applied: 18 },
          { key: 'business analyst', label: 'Business Analyst', applied: 6 },
        ],
        merges: [],
      },
      'POST /analytics/role-groups/merge': { status: 204 },
      'DELETE /analytics/role-groups/merge': { status: 204 },
    });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    const card = await screen.findByRole('region', { name: 'Response rate by role' });
    await userEvent.click(within(card).getByRole('button', { name: /Data Analyst/ }));

    await userEvent.click(within(card).getByRole('button', { name: 'Undo merge' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true));
    expect(calls.find((c) => c.method === 'DELETE')?.url).toContain('source=reporting+analyst');

    await userEvent.click(within(card).getByRole('button', { name: 'Merge into…' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /Business Analyst/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ source: 'data analyst', target: 'business analyst' }),
    );
  });

  it('asks the AI for merges and applies only the accepted ones', async () => {
    const { calls } = mockApi({
      'GET /analytics/overview': overview, 'GET /analytics/weekly-review': review,
      'GET /ai/status': { configured: true, has_api_key: true },
      'POST /analytics/role-groups/suggest': {
        suggestions: [
          { source: 'bi developer', source_label: 'BI Developer', target: 'data analyst', target_label: 'Data Analyst', reason: null },
          { source: 'reporting analyst', source_label: 'Reporting Analyst', target: 'data analyst', target_label: 'Data Analyst', reason: 'Same job' },
        ],
      },
      'POST /analytics/role-groups/merge': { status: 204 },
    });
    renderWithProviders(<AnalyticsPage />, { route: '/analytics' });
    const card = await screen.findByRole('region', { name: 'Response rate by role' });
    await userEvent.click(await within(card).findByRole('button', { name: 'Suggest groups' }));
    const list = await within(card).findByRole('list', { name: 'Suggested merges' });
    expect(calls.some((c) => c.url.endsWith('/merge'))).toBe(false);

    const [first, second] = within(list).getAllByRole('listitem');
    await userEvent.click(within(first as HTMLElement).getByRole('button', { name: 'Reject' }));
    await userEvent.click(within(second as HTMLElement).getByRole('button', { name: 'Accept' }));
    await waitFor(() => expect(within(card).getByText('All suggestions handled.')).toBeInTheDocument());
    const merges = calls.filter((c) => c.url.endsWith('/merge'));
    expect(merges.map((c) => c.body)).toEqual([{ source: 'reporting analyst', target: 'data analyst' }]);
  });
});
