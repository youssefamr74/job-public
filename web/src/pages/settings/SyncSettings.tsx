import { ApiError } from '../../api/client';
import { useSaveSyncSettings, useStartSync, useSyncRuns, useSyncSettings, useSyncStatus } from '../../api/queries';
import type { SyncRun } from '../../api/types';
import { ErrorState, Loading } from '../../components/States';
import { emailDate, timeAgo } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import styles from './SettingsPage.module.css';

const INTERVALS = [
  { value: 0, label: 'Off (only when you click Sync now)' },
  { value: 15, label: 'Every 15 minutes' },
  { value: 30, label: 'Every 30 minutes' },
  { value: 60, label: 'Every hour' },
  { value: 180, label: 'Every 3 hours' },
  { value: 360, label: 'Every 6 hours' },
  { value: 720, label: 'Every 12 hours' },
  { value: 1440, label: 'Once a day' },
];

const STATUS: Record<string, string> = {
  running: 'Running',
  succeeded: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
  waiting_for_ai: 'Waiting for AI',
};

function count(run: SyncRun, key: string): number | string {
  const value = run.funnel?.[key];
  return typeof value === 'number' ? value : '—';
}

export function SyncSettings() {
  const settings = useSyncSettings();
  const save = useSaveSyncSettings();
  const status = useSyncStatus();
  const start = useStartSync();
  const running = Boolean(status.data?.running_run);
  const runs = useSyncRuns(10, running);
  const now = useNow();

  const options =
    settings.data && !INTERVALS.some((i) => i.value === settings.data.interval_minutes)
      ? [...INTERVALS, { value: settings.data.interval_minutes, label: `Every ${settings.data.interval_minutes} minutes` }]
      : INTERVALS;

  return (
    <>
      <div className={styles.inline}>
        <div className="field">
          <label htmlFor="sync-interval">Sync automatically</label>
          <select
            id="sync-interval"
            className="input"
            value={settings.data?.interval_minutes ?? ''}
            disabled={!settings.data || save.isPending}
            onChange={(event) => save.mutate(Number(event.target.value))}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => start.mutate()}
          disabled={running || start.isPending}
        >
          {running ? 'Syncing…' : 'Sync now'}
        </button>
      </div>
      {save.isSuccess && (
        <p className={styles.success} role="status">
          Saved.
        </p>
      )}
      {save.isError && (
        <p className="error-text" role="alert">
          {save.error.message}
        </p>
      )}
      {start.isError && !(start.error instanceof ApiError && start.error.status === 409) && (
        <p className="error-text" role="alert">
          Sync didn’t start: {start.error.message}
        </p>
      )}
      <h3 className={styles.subTitle}>Last 10 runs</h3>
      {runs.isPending ? (
        <Loading>Loading sync runs…</Loading>
      ) : runs.isError ? (
        <ErrorState message={`Couldn’t load sync runs. ${runs.error.message}`} onRetry={() => void runs.refetch()} />
      ) : runs.data.length === 0 ? (
        <p className={styles.plain}>No syncs yet.</p>
      ) : (
        <div className={styles.scroller}>
          <table className={styles.table}>
            <caption className="visually-hidden">The last 10 sync runs</caption>
            <thead>
              <tr>
                <th scope="col">Status</th>
                <th scope="col">Started</th>
                <th scope="col" className={styles.num}>
                  Emails
                </th>
                <th scope="col" className={styles.num}>
                  New
                </th>
                <th scope="col" className={styles.num}>
                  Updated
                </th>
                <th scope="col" className={styles.num}>
                  To review
                </th>
                <th scope="col">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => (
                <tr key={run.id}>
                  <td className={run.status === 'failed' ? styles.warning : undefined}>
                    {STATUS[run.status] ?? run.status}
                  </td>
                  <td title={emailDate(run.started_at)}>{timeAgo(run.started_at, now)}</td>
                  <td className={styles.num}>{count(run, 'fetched')}</td>
                  <td className={styles.num}>{count(run, 'saved_new')}</td>
                  <td className={styles.num}>{count(run, 'updated_existing')}</td>
                  <td className={styles.num}>{count(run, 'needs_review')}</td>
                  <td className={styles.errorCell}>{run.error_message ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
