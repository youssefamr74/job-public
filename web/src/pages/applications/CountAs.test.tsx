import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { makeApplication, mockApi, renderWithProviders } from '../../test/utils';
import { CountAs } from './CountAs';

const groups = {
  groups: [
    { key: 'registered nurse', label: 'Registered Nurse', applied: 12 },
    { key: 'staff nurse', label: 'Staff Nurse', applied: 3 },
  ],
  merges: [{ source: 'staff nurse', source_label: 'Staff Nurse', target: 'registered nurse', target_label: 'Registered Nurse' }],
};

describe('CountAs', () => {
  it('shows the group after merges and saves a "Count as" choice', async () => {
    const application = makeApplication({ role: 'Senior Staff Nurse', role_group: 'staff nurse' });
    const { calls } = mockApi({
      'GET /analytics/role-groups': groups,
      [`PATCH /applications/${application.id}/metadata`]: { ...application, role_group_override: 'Registered Nurse' },
    });
    renderWithProviders(<dl><CountAs application={application} /></dl>);
    expect(await screen.findByText('Registered Nurse')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Change' }));
    await userEvent.type(screen.getByLabelText('Count as'), 'Midwife');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ role_group_override: 'Midwife' }));
  });

  it('goes back to the role’s own group', async () => {
    const application = makeApplication({ role: 'Barista', role_group: 'barista', role_group_override: 'Coffee Specialist' });
    const { calls } = mockApi({
      'GET /analytics/role-groups': { groups: [], merges: [] },
      [`PATCH /applications/${application.id}/metadata`]: { ...application, role_group_override: null },
    });
    renderWithProviders(<dl><CountAs application={application} /></dl>);
    expect(screen.getByText('Coffee Specialist')).toBeInTheDocument();
    expect(screen.getByText('(set by you)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Use the role’s group' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ role_group_override: '' }));
  });
});
