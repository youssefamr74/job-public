import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { daysAgo, makeApplication, mockApi, renderWithProviders } from '../../test/utils';
import { ApplicationsPage } from './ApplicationsPage';
import { NOTES_SAVE_DELAY_MS } from './NotesEditor';

const northwind = makeApplication({
  company: 'Northwind Labs',
  status: 'Interview',
  email_count: 2,
  applied_date: daysAgo(20),
  timeline: [
    { date: daysAgo(20), kind: 'email', subject: 'Thank you for applying', change: 'Applied' },
    { date: daysAgo(9), kind: 'email', subject: 'Next step: technical conversation', change: 'Applied to Interview' },
  ],
});
const review = makeApplication({ company: 'Tidewater', status: 'Needs Review' });
const old = makeApplication({ company: 'Vistula', status: 'Rejected', applied_date: daysAgo(90) });

describe('ApplicationsPage', () => {
  it('lists tracked applications from the last 60 days with a summary', async () => {
    mockApi({ 'GET /applications/': [northwind, review, old] });
    renderWithProviders(<ApplicationsPage />);
    expect(await screen.findByRole('button', { name: 'Northwind Labs' })).toBeInTheDocument();
    expect(screen.queryByText('Tidewater')).not.toBeInTheDocument();
    expect(screen.queryByText('Vistula')).not.toBeInTheDocument();
    expect(screen.getByText('1 interview')).toBeInTheDocument();
    expect(within(screen.getByRole('heading', { level: 1 })).getByText('2')).toBeInTheDocument();
  });

  it('shows plain loading and error states', async () => {
    mockApi({ 'GET /applications/': { status: 500, body: { detail: 'Database error' } } });
    renderWithProviders(<ApplicationsPage />);
    expect(screen.getByText('Loading applications…')).toBeInTheDocument();
    expect(await screen.findByText('Couldn’t load applications. Database error')).toBeInTheDocument();
  });

  it('opens the detail panel with the timeline and changes the status', async () => {
    const { calls } = mockApi({
      'GET /applications/': [northwind],
      [`PATCH /applications/${northwind.id}`]: { ...northwind, status: 'Offer' },
    });
    renderWithProviders(<ApplicationsPage />, { route: `/applications?id=${northwind.id}` });
    const panel = await screen.findByRole('complementary', { name: 'Application details' });
    expect(await within(panel).findByText('Next step: technical conversation')).toBeInTheDocument();
    expect(within(panel).getByText('Applied to Interview')).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole('button', { name: 'Change status' }));
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Offer' }));
    await waitFor(() => expect(calls.at(-1)).toMatchObject({ method: 'PATCH', body: { status: 'Offer' } }));
    expect(await within(panel).findByText('Offer', { selector: 'dd > span' })).toBeInTheDocument();
  });

  it('autosaves notes after a pause in typing', async () => {
    const { calls } = mockApi({
      'GET /applications/': [northwind],
      [`PATCH /applications/${northwind.id}`]: { ...northwind, notes: 'Ask about the team' },
    });
    renderWithProviders(<ApplicationsPage />, { route: `/applications?id=${northwind.id}` });
    const notes = await screen.findByLabelText('Notes');
    fireEvent.change(notes, { target: { value: 'Ask about' } });
    fireEvent.change(notes, { target: { value: 'Ask about the team' } });
    expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(0);
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1), {
      timeout: NOTES_SAVE_DELAY_MS * 3,
    });
    expect(calls.at(-1)?.body).toEqual({ notes: 'Ask about the team' });
    expect(await screen.findByText('Saved')).toBeInTheDocument();
  });

  it('adds an application from the dialog and opens it', async () => {
    const created = makeApplication({ company: 'Harbor Analytics', role: 'Analytics Engineer' });
    const { calls } = mockApi({ 'GET /applications/': [northwind], 'POST /applications/': { status: 201, body: created } });
    const { router } = renderWithProviders(<ApplicationsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add application' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add application' });
    await userEvent.type(within(dialog).getByLabelText('Company'), 'Harbor Analytics');
    await userEvent.type(within(dialog).getByLabelText('Role'), 'Analytics Engineer');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add application' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = calls.find((c) => c.method === 'POST');
    expect(post?.body).toMatchObject({ company: 'Harbor Analytics', role: 'Analytics Engineer', status: 'Applied' });
    expect(router.state.location.search).toContain(`id=${created.id}`);
  });

  it('shows the board with a column per status', async () => {
    mockApi({ 'GET /applications/': [northwind] });
    renderWithProviders(<ApplicationsPage />, { route: '/applications?view=board' });
    expect(await screen.findByRole('region', { name: /Interview/ })).toHaveTextContent('Northwind Labs');
    expect(screen.getByRole('button', { name: 'Board' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('asks how a held interview went and sends the answer', async () => {
    const held = makeApplication({
      company: 'Brightwave',
      status: 'Interview',
      interview_date: daysAgo(3),
      interview_held: true,
      needs_followup: true,
      no_news_days: 3,
    });
    const { calls } = mockApi({
      'GET /applications/': [held],
      [`POST /applications/${held.id}/interview-outcome`]: { ...held, needs_followup: false },
    });
    renderWithProviders(<ApplicationsPage />, { route: `/applications?id=${held.id}` });
    const prompt = await screen.findByRole('group', { name: 'How did it go?' });
    expect(within(prompt).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Rejected',
      'Next round',
      'Offer',
      'No answer yet',
    ]);
    await userEvent.click(within(prompt).getByRole('button', { name: 'No answer yet' }));
    await waitFor(() => expect(screen.queryByRole('group', { name: 'How did it go?' })).not.toBeInTheDocument());
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ outcome: 'no_answer' });
  });

  it('shows the Today overview when nothing is selected and opens an item', async () => {
    mockApi({
      'GET /applications/': [northwind],
      'GET /applications/today': {
        coming_up: [{ id: northwind.id, company: 'Northwind Labs', role: 'Data Engineer', date: daysAgo(-1) }],
        attention: [],
        this_week: { applied: 1, replies: 0, interviews: 1 },
      },
    });
    const { router } = renderWithProviders(<ApplicationsPage />);
    const today = await screen.findByRole('complementary', { name: 'Today' });
    await userEvent.click(await within(today).findByRole('button', { name: /Northwind Labs · Data Engineer/ }));
    expect(router.state.location.search).toContain(`id=${northwind.id}`);
  });
});
