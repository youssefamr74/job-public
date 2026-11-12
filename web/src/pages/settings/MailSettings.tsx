import { useState } from 'react';
import { ApiError } from '../../api/client';
import { useDisconnectMail, useMailStatus, useReconnectOAuth, useTestMail } from '../../api/queries';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { MailConnect, type MailMethod } from '../../components/mail/MailConnect';
import { ErrorState, Loading } from '../../components/States';
import { shortDate } from '../../lib/format';
import { rememberOAuthReturn } from '../../lib/oauthReturn';
import styles from './SettingsPage.module.css';

const RETURN_TO = '/settings#mail';

const METHOD: Record<MailMethod, string> = { imap: 'App password', oauth: 'Your own Google Cloud client' };
const SWITCH: Record<MailMethod, string> = {
  imap: 'Switch to an app password',
  oauth: 'Switch to your own Google Cloud client',
};
const STATE: Record<string, string> = {
  connected: 'Connected',
  needs_relink: 'Needs reconnecting',
  error: 'Last check failed',
};

type Panel = { kind: 'reconnect' | 'switch'; method: MailMethod } | null;

export function MailSettings({ notice }: { notice: { text: string; error: boolean } | null }) {
  const mail = useMailStatus();
  const test = useTestMail();
  const reconnectOAuth = useReconnectOAuth();
  const disconnect = useDisconnectMail();
  const [panel, setPanel] = useState<Panel>(null);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState<string | null>(notice && !notice.error ? notice.text : null);
  const oauthError = notice?.error ? notice.text : null;

  if (mail.isPending) return <Loading>Loading mail settings…</Loading>;
  if (mail.isError) {
    return <ErrorState message={`Couldn’t load mail settings. ${mail.error.message}`} onRetry={() => void mail.refetch()} />;
  }

  const data = mail.data;
  const connected = () => {
    setPanel(null);
    setDone('Gmail is connected.');
    test.reset();
  };

  if (data.status === 'none') {
    return (
      <>
        <p className={styles.plain}>Not connected. Jōb can’t sync until you connect Gmail.</p>
        {done && <p className={styles.success}>{done}</p>}
        {oauthError && (
          <p className="error-text" role="alert">
            {oauthError}
          </p>
        )}
        <MailConnect returnTo={RETURN_TO} submitLabel="Test and connect" onConnected={connected} />
      </>
    );
  }

  const method = (data.source ?? 'imap') as MailMethod;
  const other: MailMethod = method === 'imap' ? 'oauth' : 'imap';

  const reconnect = () => {
    setDone(null);
    if (method === 'oauth') {
      reconnectOAuth.mutate(undefined, {
        onSuccess: ({ auth_url }) => {
          rememberOAuthReturn(RETURN_TO);
          window.location.assign(auth_url);
        },
        onError: () => setPanel({ kind: 'reconnect', method: 'oauth' }),
      });
    } else {
      setPanel({ kind: 'reconnect', method: 'imap' });
    }
  };

  return (
    <>
      <dl className={styles.facts}>
        <div>
          <dt>Status</dt>
          <dd className={data.status === 'connected' ? undefined : styles.warning}>{STATE[data.status] ?? data.status}</dd>
        </div>
        <div>
          <dt>Address</dt>
          <dd>{data.email ?? '—'}</dd>
        </div>
        <div>
          <dt>Method</dt>
          <dd>{METHOD[method]}</dd>
        </div>
        <div>
          <dt>Connected on</dt>
          <dd className="mono">{shortDate(data.connected_at)}</dd>
        </div>
      </dl>
      {data.last_error && data.status !== 'connected' && <p className={styles.warning}>{data.last_error}</p>}
      {done && (
        <p className={styles.success} role="status">
          {done}
        </p>
      )}
      {oauthError && !done && (
        <p className="error-text" role="alert">
          {oauthError}
        </p>
      )}
      <div className={styles.buttons}>
        <button type="button" className="btn" onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? 'Testing…' : 'Test connection'}
        </button>
        <button type="button" className="btn" onClick={reconnect} disabled={reconnectOAuth.isPending}>
          Reconnect
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => setPanel({ kind: 'switch', method: other })}
          aria-expanded={panel?.kind === 'switch'}
        >
          {SWITCH[other]}
        </button>
        <button type="button" className="btn" onClick={() => setConfirming(true)}>
          Disconnect
        </button>
      </div>
      {test.data && (
        <p className={test.data.ok ? styles.success : 'error-text'} role="status">
          {test.data.ok ? `Works. Signed in as ${test.data.email ?? data.email}.` : test.data.message}
        </p>
      )}
      {test.isError && (
        <p className="error-text" role="alert">
          {test.error.message}
        </p>
      )}
      {panel && (
        <div className={styles.panel}>
          <div className={styles.panelHead}>
            <h3>{panel.kind === 'reconnect' ? 'Reconnect Gmail' : SWITCH[panel.method]}</h3>
            <button type="button" className="link-button" onClick={() => setPanel(null)}>
              Cancel
            </button>
          </div>
          {panel.kind === 'switch' && (
            <p className={styles.plain}>The new connection replaces the current one once it works.</p>
          )}
          <MailConnect
            key={`${panel.kind}-${panel.method}`}
            initialMethod={panel.method}
            initialEmail={data.email ?? undefined}
            fixedMethod
            submitLabel="Test and save"
            returnTo={RETURN_TO}
            onConnected={connected}
          />
        </div>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Disconnect Gmail?"
        confirmLabel="Disconnect"
        pending={disconnect.isPending}
        error={disconnect.error instanceof ApiError ? disconnect.error.message : null}
        onConfirm={() =>
          disconnect.mutate(undefined, {
            onSuccess: () => {
              setConfirming(false);
              setDone('Gmail is disconnected. Your applications are kept.');
            },
          })
        }
      >
        <p>
          Jōb stops syncing and removes the saved {method === 'oauth' ? 'Google access' : 'app password'}. Your
          applications stay.
        </p>
      </ConfirmDialog>
    </>
  );
}
