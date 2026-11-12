import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Opportunity } from '../../api/types';
import { daysAgo, makeApplication, mockApi, renderWithProviders } from '../../test/utils';
import { OpportunitiesPage } from './OpportunitiesPage';

const contoso: Opportunity = {
  id: 'o1',
  company: 'Contoso',
  role: 'Data Engineer',
  sender: 'Riley Chen <riley@contoso.example>',
  subject: 'Exciting opportunity at Contoso',
  date: daysAgo(2),
  thread_id: 't1',
  message_id: '1a2b',
  status: 'open',
  application_id: null,
};
const fabrikam: Opportunity = { ...contoso, id: 'o2', company: 'Fabrikam', message_id: null, subject: 'Hello' };

describe('OpportunitiesPage', () => {
  it('lists open opportunities with company, role, sender, date and status', async () => {
    mockApi({ 'GET /opportunities/': [contoso, fabrikam] });
    renderWithProviders(<OpportunitiesPage />, { route: '/opportunities' });
    const row = (await screen.findByRole('button', { name: 'Contoso' })).closest('tr') as HTMLElement;
    expect(within(row).getByText('Data Engineer')).toBeInTheDocument();
    expect(within(row).getByText('Riley Chen')).toBeInTheDocument();
    expect(within(row).getByText('Open')).toBeInTheDocument();
  });

  it('shows the email on demand and converts it to an application', async () => {
    const created = makeApplication({ id: 'a1', company: 'Contoso' });
    const { calls } = mockApi({
      'GET /opportunities/': [contoso],
      'GET /mail/messages/1a2b': { id: '1a2b', subject: contoso.subject, sender: contoso.sender, date: contoso.date, body: 'Interested?' },
      'POST /opportunities/o1/convert': created,
    });
    const { router } = renderWithProviders(<OpportunitiesPage />, { route: '/opportunities' });
    expect(calls.some((c) => c.url.startsWith('/mail/messages'))).toBe(false);
    await userEvent.click(await screen.findByRole('button', { name: 'Contoso' }));
    const panel = screen.getByRole('complementary', { name: 'Opportunity' });
    expect(await within(panel).findByText('Interested?')).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole('button', { name: 'Convert to application' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url === '/opportunities/o1/convert')).toBe(true),
    );
    await waitFor(() => expect(router.state.location.search).toBe('?id=a1'));
    expect(router.state.location.pathname).toBe('/applications');
  });

  it('dismisses, and explains when the email can’t be opened', async () => {
    const { calls } = mockApi({
      'GET /opportunities/': [fabrikam],
      'POST /opportunities/o2/dismiss': { ...fabrikam, status: 'dismissed' },
    });
    renderWithProviders(<OpportunitiesPage />, { route: '/opportunities?id=o2' });
    const panel = await screen.findByRole('complementary', { name: 'Opportunity' });
    expect(within(panel).getByText('The full email isn’t available for this one.')).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/opportunities/o2/dismiss')).toBe(true));
  });

  it('switches to all opportunities', async () => {
    const { calls } = mockApi({ 'GET /opportunities/': [] });
    renderWithProviders(<OpportunitiesPage />, { route: '/opportunities' });
    expect(await screen.findByText('No open opportunities.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(await screen.findByText('No opportunities yet.')).toBeInTheDocument();
    expect(calls.map((c) => c.url)).toEqual(['/opportunities/?status=open', '/opportunities/']);
  });
});
