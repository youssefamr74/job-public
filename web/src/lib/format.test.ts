import { describe, expect, it } from 'vitest';
import { dateGroup } from './format';

const at = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h).toISOString();

describe('dateGroup', () => {
  const thursday = new Date(2026, 10, 12, 15);

  it('splits dates into Today, Yesterday, This week and Earlier', () => {
    expect(dateGroup(at(2026, 11, 12, 1), thursday)).toBe('Today');
    expect(dateGroup(at(2026, 11, 11, 23), thursday)).toBe('Yesterday');
    expect(dateGroup(at(2026, 11, 9), thursday)).toBe('This week');
    expect(dateGroup(at(2026, 11, 8), thursday)).toBe('Earlier');
    expect(dateGroup(null, thursday)).toBe('Earlier');
  });

  it('puts last Sunday under Yesterday on a Monday, not This week', () => {
    const monday = new Date(2026, 10, 9, 9);
    expect(dateGroup(at(2026, 11, 8), monday)).toBe('Yesterday');
    expect(dateGroup(at(2026, 11, 7), monday)).toBe('Earlier');
  });
});
