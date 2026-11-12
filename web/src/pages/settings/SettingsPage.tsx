import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useHealth } from '../../api/queries';
import { DEMO, NOT_IN_DEMO, REPO_URL as REPO } from '../../lib/demo';
import { AISettings } from './AISettings';
import { DataSettings } from './DataSettings';
import { MailSettings } from './MailSettings';
import { SyncSettings } from './SyncSettings';
import styles from './SettingsPage.module.css';

const SECTIONS = [
  { id: 'mail', label: 'Mail' },
  { id: 'ai', label: 'AI' },
  { id: 'sync', label: 'Sync' },
  { id: 'data', label: 'Data' },
  { id: 'about', label: 'About' },
] as const;

function About() {
  const health = useHealth();
  const version = (health.data as { version?: string } | undefined)?.version;
  return (
    <dl className={styles.facts}>
      <div>
        <dt>Version</dt>
        <dd className="mono">{version ?? '—'}</dd>
      </div>
      <div>
        <dt>Source code</dt>
        <dd>
          <a href={REPO} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </dd>
      </div>
      <div>
        <dt>Guides</dt>
        <dd>
          <a href={`${REPO}/blob/main/docs/setup-gmail.md`} target="_blank" rel="noreferrer">
            Gmail
          </a>
          {' · '}
          <a href={`${REPO}/blob/main/docs/setup-ai.md`} target="_blank" rel="noreferrer">
            AI
          </a>
        </dd>
      </div>
      {!DEMO && (
        <div>
          <dt>API</dt>
          <dd>
            <a href="/docs" target="_blank" rel="noreferrer">
              API docs
            </a>
          </dd>
        </div>
      )}
    </dl>
  );
}

export function SettingsPage() {
  const location = useLocation();
  const [mailNotice] = useState(() => {
    const state = location.state as { mailNotice?: string; mailError?: boolean } | null;
    return state?.mailNotice ? { text: state.mailNotice, error: Boolean(state.mailError) } : null;
  });

  useEffect(() => {
    const id = location.hash.slice(1);
    if (!id) return;
    document.getElementById(id)?.scrollIntoView({ block: 'start' });
  }, [location.hash]);

  return (
    <div className={styles.page}>
      <nav className={styles.nav} aria-label="Settings sections">
        <h1 className={styles.title}>Settings</h1>
        <ul>
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`} aria-current={location.hash === `#${section.id}` ? 'location' : undefined}>
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.sections}>
        <section id="mail" className={styles.section} aria-labelledby="mail-title">
          <h2 id="mail-title" className={styles.sectionTitle}>
            Mail
          </h2>
          {DEMO ? <p className={styles.plain}>{NOT_IN_DEMO}</p> : <MailSettings notice={mailNotice} />}
        </section>
        <section id="ai" className={styles.section} aria-labelledby="ai-title">
          <h2 id="ai-title" className={styles.sectionTitle}>
            AI
          </h2>
          {DEMO ? <p className={styles.plain}>{NOT_IN_DEMO}</p> : <AISettings />}
        </section>
        <section id="sync" className={styles.section} aria-labelledby="sync-title">
          <h2 id="sync-title" className={styles.sectionTitle}>
            Sync
          </h2>
          <SyncSettings />
        </section>
        <section id="data" className={styles.section} aria-labelledby="data-title">
          <h2 id="data-title" className={styles.sectionTitle}>
            Data
          </h2>
          <DataSettings />
        </section>
        <section id="about" className={styles.section} aria-labelledby="about-title">
          <h2 id="about-title" className={styles.sectionTitle}>
            About
          </h2>
          <About />
        </section>
      </div>
    </div>
  );
}
