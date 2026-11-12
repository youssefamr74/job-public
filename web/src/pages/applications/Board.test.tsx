import { describe, expect, it, vi } from 'vitest';
import { createEvent, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { makeApplication, mockApi, renderWithProviders } from '../../test/utils';
import { Board, CARDS_PER_COLUMN } from './Board';

function dataTransfer() {
  const store = new Map<string, string>();
  return {
    get types() {
      return [...store.keys()];
    },
    setData: (type: string, value: string) => store.set(type, value),
    getData: (type: string) => store.get(type) ?? '',
    dropEffect: 'none',
    effectAllowed: 'all',
  };
}

describe('Board', () => {
  it('groups cards by status with counts and plain status text', () => {
    mockApi({});
    const apps = [
      makeApplication({ company: 'Kestrel Pay', no_reply_days: 27 }),
      makeApplication({ company: 'Northwind Labs', status: 'Interview', interview_date: '2026-11-13T14:00:00' }),
      makeApplication({ company: 'Larkspur', email_count: 1 }),
    ];
    renderWithProviders(<Board applications={apps} onOpen={vi.fn()} />);
    const applied = screen.getByRole('region', { name: /Applied/ });
    expect(within(applied).getByText('2')).toBeInTheDocument();
    expect(within(applied).getByText('No reply · 27 days')).toBeInTheDocument();
    expect(within(applied).getByText(/· 1 email$/)).toBeInTheDocument();
    expect(screen.getByText('Interview Fri 13 Nov, 14:00')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: /Offer/ })).getByText('Nothing here yet.')).toBeInTheDocument();
  });

  it('hides long columns behind "Show N more"', () => {
    mockApi({});
    const apps = Array.from({ length: CARDS_PER_COLUMN + 3 }, (_, i) => makeApplication({ company: `Company ${i}` }));
    renderWithProviders(<Board applications={apps} onOpen={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show 3 more' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(CARDS_PER_COLUMN + 3);
  });

  it('changes the status when a card is dropped on another column', async () => {
    const app = makeApplication({ company: 'Kestrel Pay' });
    const { calls } = mockApi({ [`PATCH /applications/${app.id}`]: { ...app, status: 'Interview' } });
    renderWithProviders(<Board applications={[app]} onOpen={vi.fn()} />);

    const transfer = dataTransfer();
    const card = screen.getByRole('button', { name: /Kestrel Pay/ });
    const target = screen.getByRole('region', { name: /Interview/ });
    for (const [element, factory] of [
      [card, createEvent.dragStart],
      [target, createEvent.dragOver],
      [target, createEvent.drop],
    ] as const) {
      const event = factory(element);
      Object.defineProperty(event, 'dataTransfer', { value: transfer });
      fireEvent(element, event);
    }

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ method: 'PATCH', body: { status: 'Interview' } });
    expect(await screen.findByText('Kestrel Pay moved to Interview.')).toBeInTheDocument();
  });

  it('shows a held interview as no news rather than an upcoming one', () => {
    mockApi({});
    const held = makeApplication({
      company: 'Brightwave',
      status: 'Interview',
      interview_date: '2026-11-09T10:00:00Z',
      interview_held: true,
      no_news_days: 2,
    });
    renderWithProviders(<Board applications={[held]} onOpen={vi.fn()} />);
    expect(screen.getByText('Interview held Nov 9 · no news for 2 days')).toBeInTheDocument();
    expect(screen.queryByText(/^Interview Mon/)).not.toBeInTheDocument();
  });
});
