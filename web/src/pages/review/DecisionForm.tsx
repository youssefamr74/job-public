import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNotJob, useSaveReview, useToOpportunity } from '../../api/queries';
import { REVIEW_STATUSES, type Application, type ReviewStatus } from '../../api/types';
import { isMissing } from '../../lib/applications';
import { hasModifier, isTypingTarget } from '../../lib/keyboard';
import { knownValue, suggestedStatus } from '../../lib/review';
import styles from './DecisionForm.module.css';

interface Props {
  application: Application;
  onDone: () => void;
}

function matchText(app: Application) {
  const company = isMissing(app.company) ? null : app.company;
  const role = isMissing(app.role) ? null : app.role;
  if (company || role) {
    return (
      <>
        The rules matched this to <strong>{[company, role].filter(Boolean).join(' · ')}</strong> but couldn’t tell the
        status.
      </>
    );
  }
  return <>The rules couldn’t tell the company, the role or the status.</>;
}

export function DecisionForm({ application, onDone }: Props) {
  const [company, setCompany] = useState(() => knownValue(application.company));
  const [role, setRole] = useState(() => knownValue(application.role));
  const [status, setStatus] = useState<ReviewStatus | null>(() => suggestedStatus(application));
  const [hint, setHint] = useState<string | null>(null);
  const save = useSaveReview();
  const notJob = useNotJob();
  const toOpportunity = useToOpportunity();
  const busy = save.isPending || notJob.isPending || toOpportunity.isPending;
  const error = save.error ?? notJob.error ?? toOpportunity.error;
  const submitRef = useRef<() => void>(() => undefined);

  const submit = () => {
    if (busy) return;
    if (!status) {
      setHint('Pick what this email is first.');
      return;
    }
    setHint(null);
    const changedCompany = company.trim() !== knownValue(application.company) && company.trim() !== '';
    const changedRole = role.trim() !== knownValue(application.role) && role.trim() !== '';
    save.mutate(
      {
        id: application.id,
        status,
        ...(changedCompany ? { company: company.trim() } : {}),
        ...(changedRole ? { role: role.trim() } : {}),
      },
      { onSuccess: onDone },
    );
  };
  useEffect(() => {
    submitRef.current = submit;
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (hasModifier(event) || isTypingTarget(event.target)) return;
      const target = event.target as HTMLElement | null;
      if (event.key === 'Enter') {
        if (target?.closest('button, a')) return;
        event.preventDefault();
        submitRef.current();
        return;
      }
      const number = Number(event.key);
      if (number >= 1 && number <= REVIEW_STATUSES.length) {
        event.preventDefault();
        setStatus(REVIEW_STATUSES[number - 1] ?? null);
        setHint(null);
      } else if (event.key.toLowerCase() === 's') {
        event.preventDefault();
        onDone();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDone]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  return (
    <form className={styles.form} onSubmit={onSubmit} aria-label="Decision">
      <p className={styles.match}>{matchText(application)}</p>
      <div className={styles.fields}>
        <div className="field">
          <label htmlFor="review-company">Company</label>
          <input
            id="review-company"
            className="input"
            value={company}
            onChange={(event) => setCompany(event.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="field">
          <label htmlFor="review-role">Role</label>
          <input
            id="review-role"
            className="input"
            value={role}
            onChange={(event) => setRole(event.target.value)}
            autoComplete="off"
          />
        </div>
      </div>
      <fieldset className={styles.statuses}>
        <legend className="field-label">What is this email?</legend>
        <div className={styles.statusButtons}>
          {REVIEW_STATUSES.map((value, i) => (
            <button
              key={value}
              type="button"
              className={styles.status}
              aria-pressed={status === value}
              aria-keyshortcuts={String(i + 1)}
              onClick={() => {
                setStatus(value);
                setHint(null);
              }}
            >
              <span className={styles.key} aria-hidden="true">
                {i + 1}
              </span>
              {value}
            </button>
          ))}
        </div>
      </fieldset>
      <div className={styles.other}>
        <button
          type="button"
          className="link-button"
          disabled={busy}
          onClick={() => notJob.mutate(application.id, { onSuccess: onDone })}
        >
          Not a job email
        </button>
        <button
          type="button"
          className="link-button"
          disabled={busy}
          onClick={() => toOpportunity.mutate(application.id, { onSuccess: onDone })}
        >
          It’s a recruiter reaching out
        </button>
      </div>
      <div className={styles.actions}>
        <button type="submit" className={`btn btn-primary ${styles.save}`} disabled={busy} aria-keyshortcuts="Enter">
          {save.isPending ? 'Saving…' : 'Save and next'}
        </button>
        <button type="button" className={`btn ${styles.skip}`} onClick={onDone} disabled={busy} aria-keyshortcuts="S">
          Skip
        </button>
        <span className={styles.shortcuts} aria-hidden="true">
          <kbd>Enter</kbd> save · <kbd>S</kbd> skip
        </span>
      </div>
      {(hint || error) && (
        <p className={hint ? styles.hint : 'error-text'} role="alert">
          {hint ?? `Couldn’t save. ${error?.message ?? ''}`}
        </p>
      )}
    </form>
  );
}
