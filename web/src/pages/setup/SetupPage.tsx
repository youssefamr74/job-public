import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAIProviders, useAIStatus, useEstimate, useSetupStatus, useStartFirstSync, useSyncStatus } from '../../api/queries';
import type { Estimate, SyncRun } from '../../api/types';
import { AIForm } from '../../components/ai/AIForm';
import { MailConnect } from '../../components/mail/MailConnect';
import { ErrorState, Loading } from '../../components/States';
import { plural } from '../../lib/format';
import { DEMO, NOT_IN_DEMO } from '../../lib/demo';
import { oauthErrorText, takeOAuthReturn } from '../../lib/oauthReturn';
import { Placeholder } from '../Placeholder';
import { DEFAULT_MAX_EMAILS, SYNC_RANGES, markSetupDone, sinceDate, type SyncRange } from '../../lib/setup';
import styles from './SetupPage.module.css';

type Step = 'mail' | 'ai' | 'sync' | 'progress';

const STEPS: { id: Exclude<Step, 'progress'>; label: string }[] = [
  { id: 'mail', label: 'Gmail' },
  { id: 'ai', label: 'AI (optional)' },
  { id: 'sync', label: 'First sync' },
];

function StepNav({ step }: { step: Step }) {
  const current = step === 'progress' ? 'sync' : step;
  return (
    <ol className={styles.stepNav} aria-label="Setup steps">
      {STEPS.map((s, index) => (
        <li key={s.id} aria-current={s.id === current ? 'step' : undefined}>
          <span className={styles.stepNumber}>{index + 1}</span> {s.label}
        </li>
      ))}
    </ol>
  );
}

function MailStep({ error, onDone }: { error: string | null; onDone: () => void }) {
  return (
    <>
      <h1 className={styles.title}>Connect your Gmail</h1>
      <p className={styles.lead}>
        Jōb reads your inbox to find applications and keep their status up to date. It only reads; it never sends or
        deletes anything.
      </p>
      {error && (
        <p className={`error-text ${styles.banner}`} role="alert">
          {error}
        </p>
      )}
      <MailConnect initialMethod={error ? 'oauth' : 'imap'} returnTo="/setup?step=ai" onConnected={onDone} />
    </>
  );
}

function AIStep({ onDone }: { onDone: () => void }) {
  const ai = useAIStatus();
  const providers = useAIProviders();
  const [changing, setChanging] = useState(false);
  const status = ai.data;
  const name = providers.data?.find((p) => p.id === status?.provider)?.name ?? status?.provider;

  return (
    <>
      <h1 className={styles.title}>Add AI (optional)</h1>
      <p className={styles.lead}>
        The rules sort most emails on their own. With your own AI key, Jōb also sorts the unclear ones and writes a
        short weekly review. You pay your provider directly; Jōb never sees the bill.
      </p>
      {ai.isPending ? (
        <Loading>Loading…</Loading>
      ) : status?.configured && !changing ? (
        <div className={styles.done}>
          <p>
            AI is set up: <strong>{name}</strong> · <span className="mono">{status.model}</span>
          </p>
          <div className={styles.actions}>
            <button type="button" className="btn btn-primary" onClick={onDone}>
              Continue
            </button>
            <button type="button" className="btn" onClick={() => setChanging(true)}>
              Change
            </button>
          </div>
        </div>
      ) : (
        <AIForm
          status={status}
          submitLabel="Save and continue"
          onSaved={onDone}
          extraActions={
            <button type="button" className="btn" onClick={onDone}>
              Skip
            </button>
          }
        />
      )}
    </>
  );
}

function EstimateText({ estimate }: { estimate: Estimate }) {
  const cost =
    estimate.estimated_cost_usd == null
      ? 'The price for this model isn’t known, so there is no cost estimate.'
      : `About $${estimate.estimated_cost_usd < 0.01 ? '0.01 or less' : estimate.estimated_cost_usd.toFixed(2)}${
          estimate.would_use_batch ? ' with batches' : ''
        }.`;
  return (
    <p>
      Of {plural(estimate.emails_checked, 'email')}, the rules settle {estimate.settled_by_rules} and filter{' '}
      {estimate.filtered_out}; {plural(estimate.would_send_to_ai, 'email')} would go to your AI. {cost}
    </p>
  );
}

function SyncStep({ onStarted }: { onStarted: (runId: string) => void }) {
  const ai = useAIStatus();
  const estimate = useEstimate();
  const start = useStartFirstSync();
  const [range, setRange] = useState<SyncRange>('60');
  const [max, setMax] = useState(DEFAULT_MAX_EMAILS);
  const configured = ai.data?.configured === true;
  const options = { since_date: sinceDate(Number(range)), max_messages: max };
  const valid = Number.isInteger(max) && max >= 1 && max <= DEFAULT_MAX_EMAILS;

  return (
    <>
      <h1 className={styles.title}>Run the first sync</h1>
      <p className={styles.lead}>
        Jōb looks through this much of your mail once. After that, syncs only read what is new.
      </p>
      <div className={styles.fields}>
        <div className="field">
          <label htmlFor="sync-range">How far back</label>
          <select
            id="sync-range"
            className="input"
            value={range}
            onChange={(event) => {
              setRange(event.target.value as SyncRange);
              estimate.reset();
            }}
          >
            {SYNC_RANGES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="sync-max">At most this many emails</label>
          <input
            id="sync-max"
            className="input mono"
            type="number"
            min={1}
            max={DEFAULT_MAX_EMAILS}
            value={Number.isNaN(max) ? '' : max}
            onChange={(event) => {
              setMax(event.target.valueAsNumber);
              estimate.reset();
            }}
          />
        </div>
      </div>
      {configured && (
        <div className={styles.estimate}>
          <h2 className={styles.subTitle}>AI cost</h2>
          {estimate.isSuccess ? (
            <EstimateText estimate={estimate.data} />
          ) : estimate.isError ? (
            <p className="error-text" role="alert">
              Couldn’t estimate. {estimate.error.message}
            </p>
          ) : (
            <p className={styles.muted}>Jōb reads the subjects and senders to count what would go to your AI.</p>
          )}
          <button
            type="button"
            className="btn"
            onClick={() => estimate.mutate(options)}
            disabled={!valid || estimate.isPending}
          >
            {estimate.isPending ? 'Estimating…' : estimate.isSuccess ? 'Estimate again' : 'Estimate the cost'}
          </button>
        </div>
      )}
      {start.isError && (
        <p className="error-text" role="alert">
          The sync didn’t start. {start.error.message}
        </p>
      )}
      <div className={`${styles.actions} ${styles.footer}`}>
        <button
          type="button"
          className={`btn btn-primary ${styles.primary}`}
          disabled={!valid || start.isPending}
          onClick={() => start.mutate(options, { onSuccess: ({ run_id }) => onStarted(run_id) })}
        >
          {start.isPending ? 'Starting…' : 'Start'}
        </button>
        {!valid && <span className="error-text">Enter a number from 1 to {DEFAULT_MAX_EMAILS}.</span>}
      </div>
    </>
  );
}

const STAGES: Record<string, string> = {
  fetching: 'Reading your mail',
  filtering: 'Setting aside newsletters and alerts',
  classifying: 'Sorting the emails',
  saving: 'Saving applications',
};

function progressPercent(run: SyncRun): number | null {
  if (!run.progress_total) return null;
  return Math.min(100, Math.round((run.progress_done / run.progress_total) * 100));
}

function ProgressStep({ runId, onFinished }: { runId: string | null; onFinished: () => void }) {
  const status = useSyncStatus();
  const running = status.data?.running_run ?? null;
  const last = status.data?.last_run ?? null;
  const ours = (run: SyncRun | null) => run !== null && (runId === null || run.id === runId);
  const finished = ours(last) && last?.status !== 'running' ? last : null;
  const succeeded = finished !== null && finished.status !== 'failed';

  useEffect(() => {
    if (!succeeded) return;
    const id = window.setTimeout(onFinished, 1500);
    return () => window.clearTimeout(id);
  }, [succeeded, onFinished]);

  const run = (ours(running) ? running : null) ?? finished;
  const percent = run ? progressPercent(run) : null;

  return (
    <>
      <h1 className={styles.title}>{finished ? (succeeded ? 'First sync done' : 'The sync stopped') : 'Syncing your mail'}</h1>
      <div className={styles.progress} role="status" aria-live="polite">
        {!run ? (
          <p className={styles.muted}>Starting…</p>
        ) : finished ? (
          succeeded ? (
            <p>
              Found {plural(Number(finished.summary?.new_applications ?? 0), 'application')}. Opening them now…
            </p>
          ) : (
            <p className="error-text">{finished.error_message ?? 'The sync stopped with an error.'}</p>
          )
        ) : (
          <>
            <p>
              {STAGES[run.stage ?? 'fetching'] ?? 'Working'}
              {run.stage === 'fetching' ? ` · ${plural(run.progress_done, 'email')}` : ''}
              {percent !== null && run.stage !== 'fetching' ? ` · ${run.progress_done} of ${run.progress_total}` : ''}
            </p>
            <div
              className={styles.bar}
              role="progressbar"
              aria-label="Sync progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent ?? undefined}
            >
              <div className={styles.barFill} data-indeterminate={percent === null || undefined} style={{ width: `${percent ?? 30}%` }} />
            </div>
          </>
        )}
      </div>
      {finished && (
        <div className={styles.actions}>
          <button type="button" className="btn btn-primary" onClick={onFinished}>
            Go to applications
          </button>
        </div>
      )}
      {!finished && <p className={styles.muted}>You can leave this page; the sync keeps going.</p>}
    </>
  );
}

export function SetupPage() {
  if (DEMO) {
    return (
      <Placeholder title="Setup">
        <p>
          {NOT_IN_DEMO}. The demo already has sample data. <Link to="/applications">Go to applications</Link>
        </p>
      </Placeholder>
    );
  }
  return <SetupWizard />;
}

function SetupWizard() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const setup = useSetupStatus();
  const [oauthResult] = useState(() => ({ result: params.get('mail'), reason: params.get('reason') }));
  const mailError =
    oauthResult.result && oauthResult.result !== 'connected' ? oauthErrorText(oauthResult.reason) : null;
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current || !oauthResult.result) return;
    handled.current = true;
    const connected = oauthResult.result === 'connected';
    const back = takeOAuthReturn();
    if (back && !back.startsWith('/setup')) {
      navigate(back, {
        replace: true,
        state: { mailNotice: connected ? 'Gmail is connected.' : mailError, mailError: !connected },
      });
      return;
    }
    setParams({ step: connected ? 'ai' : 'mail' }, { replace: true });
  }, [oauthResult, mailError, navigate, setParams]);

  const requested = params.get('step') as Step | null;
  const go = (step: Step, extra: Record<string, string> = {}) => setParams({ step, ...extra });
  const queryClient = useQueryClient();
  const finish = useCallback(() => {
    markSetupDone();
    void queryClient.invalidateQueries();
    navigate('/applications', { replace: true });
  }, [navigate, queryClient]);

  let step: Step;
  if (requested && ['mail', 'ai', 'sync', 'progress'].includes(requested)) step = requested;
  else step = setup.data && setup.data.mail !== 'none' ? 'ai' : 'mail';
  if (step !== 'mail' && setup.data?.mail === 'none' && step !== 'progress') step = 'mail';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.logo}>Jōb</span>
        <span className={styles.local}>Runs on this computer</span>
      </header>
      <main id="main" className={styles.main}>
        <StepNav step={step} />
        {setup.isPending && !params.get('mail') ? (
          <Loading>Loading…</Loading>
        ) : setup.isError ? (
          <ErrorState message={`Jōb isn’t answering. ${setup.error.message}`} onRetry={() => void setup.refetch()} />
        ) : step === 'mail' ? (
          <MailStep error={mailError} onDone={() => go('ai')} />
        ) : step === 'ai' ? (
          <AIStep onDone={() => go('sync')} />
        ) : step === 'sync' ? (
          <SyncStep onStarted={(run) => go('progress', { run })} />
        ) : (
          <ProgressStep runId={params.get('run')} onFinished={finish} />
        )}
        {step !== 'progress' && (
          <p className={styles.skip}>
            <Link to="/applications" onClick={markSetupDone}>
              Skip setup for now
            </Link>
          </p>
        )}
      </main>
    </div>
  );
}
