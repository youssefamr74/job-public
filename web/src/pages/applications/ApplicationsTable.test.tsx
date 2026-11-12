import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { daysAgo, makeApplication } from '../../test/utils';
import { ApplicationsTable } from './ApplicationsTable';

const apps = [
  makeApplication({ company: 'Brightwave', status: 'Assessment', applied_date: daysAgo(3) }),
  makeApplication({ company: 'Orchard Robotics', role: 'Unknown', applied_date: daysAgo(8) }),
  makeApplication({ company: 'Kestrel Pay', no_reply_days: 27, applied_date: daysAgo(27), email_count: 4 }),
];

function companies() {
  return screen
    .getAllByRole('row')
    .flatMap((row) => within(row).queryAllByRole('cell').slice(0, 1))
    .map((cell) => cell.textContent);
}

describe('ApplicationsTable', () => {
  it('shows missing roles and stale applications in words', () => {
    render(<ApplicationsTable applications={apps} selectedId={null} onOpen={vi.fn()} />);
    expect(screen.getByText('Role not found')).toBeInTheDocument();
    expect(screen.getByText('No reply · 27 days')).toBeInTheDocument();
  });

  it('sorts newest first, and by a column when its header is clicked', async () => {
    render(<ApplicationsTable applications={apps} selectedId={null} onOpen={vi.fn()} />);
    expect(companies()).toEqual(['Brightwave', 'Orchard Robotics', 'Kestrel Pay']);
    await userEvent.click(screen.getByRole('button', { name: /Company/ }));
    expect(companies()).toEqual(['Brightwave', 'Kestrel Pay', 'Orchard Robotics']);
    expect(screen.getByRole('columnheader', { name: /Company/ })).toHaveAttribute('aria-sort', 'ascending');
  });

  it('moves with J and K and opens with Enter', async () => {
    const onOpen = vi.fn();
    render(<ApplicationsTable applications={apps} selectedId={null} onOpen={onOpen} />);
    await userEvent.keyboard('j');
    await userEvent.keyboard('j');
    await userEvent.keyboard('k');
    await userEvent.keyboard('j');
    await userEvent.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledWith(apps[1]?.id);
  });

  it('opens a row from the company button', async () => {
    const onOpen = vi.fn();
    render(<ApplicationsTable applications={apps} selectedId={null} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: 'Kestrel Pay' }));
    expect(onOpen).toHaveBeenCalledWith(apps[2]?.id);
  });

  it('groups rows by date when sorted by a date, and not otherwise', async () => {
    const grouped = [
      makeApplication({ company: 'Fresh', applied_date: new Date().toISOString() }),
      makeApplication({ company: 'Old', applied_date: daysAgo(40) }),
    ];
    render(<ApplicationsTable applications={grouped} selectedId={null} onOpen={vi.fn()} />);
    expect(screen.getByRole('columnheader', { name: 'Today' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Earlier' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Role/ }));
    expect(screen.queryByRole('columnheader', { name: 'Today' })).not.toBeInTheDocument();
  });

  it('shows a held interview with no news instead of a date, and the progress steps', () => {
    const held = makeApplication({
      company: 'Brightwave',
      status: 'Interview',
      interview_date: '2026-11-09T10:00:00Z',
      interview_held: true,
      no_news_days: 1,
      progress_step: 3,
    });
    render(<ApplicationsTable applications={[held]} selectedId={null} onOpen={vi.fn()} />);
    expect(screen.getByText('Interview held Nov 9 · no news for 1 day')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Reached Interview, step 3 of 4' })).toBeInTheDocument();
  });
});
