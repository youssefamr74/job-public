import { useState } from 'react';
import { Link, Navigate, Outlet } from 'react-router-dom';
import { useMailStatus, useSetupStatus } from '../api/queries';
import { DEMO, REPO_URL } from '../lib/demo';
import { needsSetup } from '../lib/setup';
import { Header } from './Header';
import styles from './Layout.module.css';

export function Layout() {
  const mail = useMailStatus();
  const [syncError, setSyncError] = useState<string | null>(null);
  const setup = useSetupStatus();
  const needsRelink = mail.data?.status === 'needs_relink';

  if (setup.data && needsSetup(setup.data)) return <Navigate to="/setup" replace />;

  return (
    <div className={styles.app}>
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>
      {DEMO && (
        <p className={styles.demo}>
          Demo with sample data · <a href={REPO_URL}>Install Jōb to use your own Gmail</a>
        </p>
      )}
      <Header onSyncError={setSyncError} />
      {needsRelink && (
        <p className={styles.notice} role="status">
          Gmail needs to be reconnected before Jōb can sync again. <Link to="/settings">Reconnect in Settings</Link>
        </p>
      )}
      {syncError && (
        <p className={styles.notice} role="alert">
          Sync didn’t start: {syncError}
          <button type="button" className="link-button" onClick={() => setSyncError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <main id="main" className={styles.main} tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
