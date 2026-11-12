import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import * as Tooltip from '@radix-ui/react-tooltip';
import { ApiError } from '../api/client';
import { keys, useStartSync, useSyncStatus } from '../api/queries';
import type { SyncRun } from '../api/types';
import { timeAgo } from '../lib/format';
import { useNow } from '../lib/useNow';
import styles from './SyncStatus.module.css';

function progressText(run: SyncRun): string {
  if (run.stage === 'fetching' || !run.stage) return `Syncing… fetched ${run.progress_done}`;
  if (run.progress_total) return `Syncing… checked ${run.progress_done} of ${run.progress_total}`;
  return 'Syncing…';
}

interface Props {
  onError: (message: string | null) => void;
}

export function SyncStatus({ onError }: Props) {
  const queryClient = useQueryClient();
  const status = useSyncStatus();
  const startSync = useStartSync();
  const now = useNow();
  const running = status.data?.running_run ?? null;
  const wasRunning = useRef(false);

  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: keys.applications });
      void queryClient.invalidateQueries({ queryKey: keys.openOpportunities });
      void queryClient.invalidateQueries({ queryKey: keys.mailStatus });
      void queryClient.invalidateQueries({ queryKey: keys.notifications });
    }
    wasRunning.current = Boolean(running);
  }, [running, queryClient]);

  const start = () => {
    onError(null);
    startSync.mutate(undefined, {
      onError: (error) => {
        if (error instanceof ApiError && error.status === 409) return;
        onError(error.message);
      },
    });
  };

  const lastRun = status.data?.last_run;
  const failed = !running && lastRun && lastRun.status === 'failed';
  let label: string;
  if (running) label = progressText(running);
  else if (status.isPending) label = '';
  else if (status.isError) label = 'Sync status unavailable';
  else if (status.data?.last_success_at) label = `Synced ${timeAgo(status.data.last_success_at, now)}`;
  else label = 'Not synced yet';

  return (
    <div className={styles.sync}>
      <span className={styles.label} role="status" aria-live="polite">
        {failed ? (
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <span className={styles.failed} tabIndex={0}>
                Last sync failed
              </span>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content className="tooltip" sideOffset={6}>
                {lastRun.error_message ?? 'The sync stopped with an error.'}
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        ) : (
          <span className={running ? 'mono' : undefined}>{label}</span>
        )}
      </span>
      <button type="button" className="btn" onClick={start} disabled={Boolean(running) || startSync.isPending}>
        {running ? 'Syncing' : 'Sync now'}
      </button>
    </div>
  );
}
