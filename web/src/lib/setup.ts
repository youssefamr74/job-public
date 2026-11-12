import type { SetupStatus } from '../api/types';

const KEY = 'job.setupDone';

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

export function markSetupDone() {
  try {
    localStorage.setItem(KEY, '1');
  } catch {
    /* without storage the first-sync check below still stops the wizard from coming back */
  }
}

export function resetSetup() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to reset */
  }
}

/** The wizard opens by itself only on a first run: no mail, no sync yet, and never finished or skipped. */
export function needsSetup(status: SetupStatus): boolean {
  return status.mail === 'none' && !status.first_sync_done && !read();
}

export type SyncRange = '30' | '60' | '90' | '180' | '365';

export const SYNC_RANGES: { value: SyncRange; label: string }[] = [
  { value: '30', label: 'Last 30 days' },
  { value: '60', label: 'Last 60 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
];

export const DEFAULT_MAX_EMAILS = 2000;

/** The local calendar day `days` ago, as YYYY-MM-DD. */
export function sinceDate(days: number, now: Date = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days);
  const month = String(day.getMonth() + 1).padStart(2, '0');
  const date = String(day.getDate()).padStart(2, '0');
  return `${day.getFullYear()}-${month}-${date}`;
}
