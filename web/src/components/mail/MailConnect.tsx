import { useId, useState, type FormEvent } from 'react';
import { useConnectImap, useRedirectUri, useStartOAuth } from '../../api/queries';
import { rememberOAuthReturn } from '../../lib/oauthReturn';
import styles from './MailConnect.module.css';

export type MailMethod = 'imap' | 'oauth';

interface Props {
  initialMethod?: MailMethod;
  initialEmail?: string;
  /** Hide the method choice, e.g. when reconnecting the same way. */
  fixedMethod?: boolean;
  submitLabel?: string;
  /** Where to come back to after Google's consent screen. */
  returnTo: string;
  onConnected: () => void;
}

const SECURITY_URL = 'https://myaccount.google.com/security';
const APP_PASSWORDS_URL = 'https://myaccount.google.com/apppasswords';
const CLOUD_CONSOLE_URL = 'https://console.cloud.google.com/apis/credentials';
const GUIDE_URL = 'https://github.com/youssefamr74/job-public/blob/main/docs/setup-gmail.md';

function External({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

function ImapForm({ initialEmail, submitLabel, onConnected }: Pick<Props, 'initialEmail' | 'submitLabel' | 'onConnected'>) {
  const [email, setEmail] = useState(initialEmail ?? '');
  const [password, setPassword] = useState('');
  const connect = useConnectImap();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    connect.mutate({ email: email.trim(), app_password: password }, { onSuccess: onConnected });
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <h3 className={styles.stepsTitle}>Steps</h3>
      <ol className={styles.steps}>
        <li>
          Turn on 2-Step Verification in your <External href={SECURITY_URL}>Google security settings</External>.
        </li>
        <li>
          Open <External href={APP_PASSWORDS_URL}>App passwords</External>, type the name “Jōb” and click Create.
        </li>
        <li>Copy the 16 characters Google shows you and paste them below. Google shows them only once.</li>
      </ol>
      <div className="field">
        <label htmlFor="mail-email">Gmail address</label>
        <input
          id="mail-email"
          className={`input ${styles.input}`}
          type="email"
          autoComplete="email"
          placeholder="you@gmail.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="mail-password">App password</label>
        <input
          id="mail-password"
          className={`input mono ${styles.input}`}
          type="password"
          autoComplete="off"
          placeholder="xxxx xxxx xxxx xxxx"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-describedby="mail-password-note"
          required
        />
        <p id="mail-password-note" className={styles.note}>
          Stored encrypted on this computer. Remove it any time in Settings.
        </p>
      </div>
      {connect.isError && (
        <p className="error-text" role="alert">
          {connect.error.message}
        </p>
      )}
      <div className={styles.actions}>
        <button type="submit" className={`btn btn-primary ${styles.submit}`} disabled={connect.isPending}>
          {connect.isPending ? 'Checking…' : (submitLabel ?? 'Test and continue')}
        </button>
        <span className={styles.note}>We check the connection before saving anything.</span>
      </div>
    </form>
  );
}

function OAuthForm({ returnTo }: Pick<Props, 'returnTo'>) {
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [copied, setCopied] = useState(false);
  const redirect = useRedirectUri();
  const start = useStartOAuth();
  const uri = redirect.data?.redirect_uri ?? '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(uri);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    start.mutate(
      { client_id: clientId.trim(), client_secret: secret.trim() },
      {
        onSuccess: ({ auth_url }) => {
          rememberOAuthReturn(returnTo);
          window.location.assign(auth_url);
        },
      },
    );
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <h3 className={styles.stepsTitle}>Steps</h3>
      <ol className={styles.steps}>
        <li>
          In the <External href={CLOUD_CONSOLE_URL}>Google Cloud console</External>, enable the Gmail API and create
          an OAuth client of type “Web application”.
        </li>
        <li>Add the redirect URI below to the client’s authorized redirect URIs.</li>
        <li>
          Paste the client ID and secret here and click Connect. The <External href={GUIDE_URL}>Gmail guide</External>{' '}
          has every step with screenshots.
        </li>
      </ol>
      <div className="field">
        <span className="field-label" id="redirect-label">
          Redirect URI
        </span>
        <div className={styles.copyRow}>
          <code className={styles.code} aria-labelledby="redirect-label">
            {redirect.isPending ? 'Loading…' : uri}
          </code>
          <button type="button" className="btn" onClick={() => void copy()} disabled={!uri}>
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <span className="visually-hidden" role="status">
          {copied ? 'Redirect URI copied' : ''}
        </span>
      </div>
      <div className="field">
        <label htmlFor="oauth-client-id">Client ID</label>
        <input
          id="oauth-client-id"
          className={`input ${styles.input}`}
          autoComplete="off"
          placeholder="1234-abc.apps.googleusercontent.com"
          value={clientId}
          onChange={(event) => setClientId(event.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="oauth-client-secret">Client secret</label>
        <input
          id="oauth-client-secret"
          className={`input ${styles.input}`}
          type="password"
          autoComplete="off"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          required
        />
        <p className={styles.note}>Stored encrypted on this computer. Jōb asks Google for read-only access.</p>
      </div>
      {start.isError && (
        <p className="error-text" role="alert">
          {start.error.message}
        </p>
      )}
      <div className={styles.actions}>
        <button type="submit" className={`btn btn-primary ${styles.submit}`} disabled={start.isPending}>
          {start.isPending ? 'Opening Google…' : 'Connect'}
        </button>
        <span className={styles.note}>Google asks you to allow read access, then sends you back here.</span>
      </div>
    </form>
  );
}

export function MailConnect({
  initialMethod = 'imap',
  initialEmail,
  fixedMethod = false,
  submitLabel,
  returnTo,
  onConnected,
}: Props) {
  const [method, setMethod] = useState<MailMethod>(initialMethod);
  const name = useId();

  return (
    <div>
      {!fixedMethod && (
        <fieldset className={styles.methods}>
          <legend className="visually-hidden">How to connect</legend>
          <label className={styles.method}>
            <input type="radio" name={name} checked={method === 'imap'} onChange={() => setMethod('imap')} />
            <span>
              <span className={styles.methodTitle}>App password</span>
              <span className={styles.methodNote}>About 3 minutes. Needs 2-Step Verification on your Google account.</span>
            </span>
          </label>
          <label className={styles.method}>
            <input type="radio" name={name} checked={method === 'oauth'} onChange={() => setMethod('oauth')} />
            <span>
              <span className={styles.methodTitle}>Your own Google Cloud client</span>
              <span className={styles.methodNote}>About 10 minutes. Read-only access. For people who prefer OAuth.</span>
            </span>
          </label>
        </fieldset>
      )}
      {method === 'imap' ? (
        <ImapForm initialEmail={initialEmail} submitLabel={submitLabel} onConnected={onConnected} />
      ) : (
        <OAuthForm returnTo={returnTo} />
      )}
    </div>
  );
}
