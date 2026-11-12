import { describe, expect, it } from 'vitest';
import { daysAgo, makeApplication } from '../test/utils';
import { applyFilters, isMissing, statusSummary } from './applications';

describe('applyFilters', () => {
  const apps = [
    makeApplication({ company: 'Kestrel Pay', status: 'Applied', no_reply_days: 27, applied_date: daysAgo(27) }),
    makeApplication({ company: 'Brightwave', role: 'Backend', status: 'Assessment', applied_date: daysAgo(10) }),
    makeApplication({ company: 'Vistula', status: 'Rejected', applied_date: daysAgo(80) }),
  ];

  it('filters by status, date range, no reply and search', () => {
    const base = { status: null, range: 'all' as const, noReply: false, query: '' };
    expect(applyFilters(apps, { ...base, status: 'Rejected' }).map((a) => a.company)).toEqual(['Vistula']);
    expect(applyFilters(apps, { ...base, range: '60' })).toHaveLength(2);
    expect(applyFilters(apps, { ...base, noReply: true }).map((a) => a.company)).toEqual(['Kestrel Pay']);
    expect(applyFilters(apps, { ...base, query: 'backend' }).map((a) => a.company)).toEqual(['Brightwave']);
  });

  it('summarises counts in pipeline order and skips empty statuses', () => {
    expect(statusSummary(apps)).toBe('1 applied · 1 assessment · 1 rejected');
  });

  it('treats Unknown and blanks as missing', () => {
    expect(isMissing('Unknown')).toBe(true);
    expect(isMissing('  ')).toBe(true);
    expect(isMissing(null)).toBe(true);
    expect(isMissing('Data Engineer')).toBe(false);
  });
});
