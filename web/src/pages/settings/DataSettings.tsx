import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useClearDropped, useDeleteAll, useDroppedCount } from '../../api/queries';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { DEMO, NOT_IN_DEMO } from '../../lib/demo';
import { plural } from '../../lib/format';
import { resetSetup } from '../../lib/setup';
import styles from './SettingsPage.module.css';

export function DataSettings() {
  const dropped = useDroppedCount();
  const clear = useClearDropped();
  const deleteAll = useDeleteAll();
  const navigate = useNavigate();
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const total = dropped.data?.total;

  return (
    <>
      <div className={styles.row}>
        <div>
          <h3 className={styles.rowTitle}>Export applications</h3>
          <p className={styles.plain}>Every application with its status, dates and notes.</p>
        </div>
        {DEMO ? (
          <p className={styles.plain}>{NOT_IN_DEMO}</p>
        ) : (
          <div className={styles.buttons}>
            <a className="btn" href="/data/export/applications.csv" download>
              Download CSV
            </a>
            <a className="btn" href="/data/export/applications.json" download>
              Download JSON
            </a>
          </div>
        )}
      </div>
      <div className={styles.row}>
        <div>
          <h3 className={styles.rowTitle}>Dropped-emails log</h3>
          <p className={styles.plain}>
            Subjects and senders of emails the sync skipped, kept to check the rules.{' '}
            {total !== undefined && `${plural(total, 'email')} logged.`}
          </p>
        </div>
        <div className={styles.buttons}>
          <button type="button" className="btn" onClick={() => setConfirmClear(true)} disabled={total === 0}>
            Clear log
          </button>
        </div>
      </div>
      <div className={styles.row}>
        <div>
          <h3 className={styles.rowTitle}>Delete all data</h3>
          <p className={styles.plain}>
            Applications, opportunities, notifications, sync history, the mail connection and AI settings.
          </p>
        </div>
        <div className={styles.buttons}>
          <button type="button" className={`btn ${styles.dangerButton}`} onClick={() => setConfirmDelete(true)}>
            Delete all data
          </button>
        </div>
      </div>
      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Clear the dropped-emails log?"
        confirmLabel="Clear log"
        pending={clear.isPending}
        error={clear.error?.message ?? null}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setConfirmClear(false) })}
      >
        <p>Applications aren’t affected. The log only helps check what the rules skipped.</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete all data?"
        confirmLabel="Delete everything"
        typeToConfirm="DELETE"
        pending={deleteAll.isPending}
        error={deleteAll.error?.message ?? null}
        onConfirm={() =>
          deleteAll.mutate(undefined, {
            onSuccess: () => {
              setConfirmDelete(false);
              resetSetup();
              navigate('/setup', { replace: true });
            },
          })
        }
      >
        <p>
          Everything Jōb stored on this computer is deleted and Gmail is disconnected. This can’t be undone. Export
          your applications first if you want to keep them.
        </p>
      </ConfirmDialog>
    </>
  );
}
