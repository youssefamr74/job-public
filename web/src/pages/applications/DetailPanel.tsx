import { useEffect, useRef, useState } from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useInterviewOutcome, useUpdateApplication } from '../../api/queries';
import { BOARD_STATUSES, type Application, type BoardStatus, type InterviewOutcome } from '../../api/types';
import { CheckIcon, CloseIcon } from '../../components/Icons';
import { heldText, isMissing, statusClass } from '../../lib/applications';
import { ProgressSteps } from '../../components/ProgressSteps';
import { interviewDate, shortDate } from '../../lib/format';
import { hasModifier, isTypingTarget } from '../../lib/keyboard';
import { CountAs } from './CountAs';
import { EditDetailsDialog } from './EditDetailsDialog';
import { NotesEditor } from './NotesEditor';
import { TodayOverview } from './TodayOverview';
import styles from './DetailPanel.module.css';

const SOURCES: Record<string, string> = { gmail: 'Gmail', manual: 'Added by you' };

interface Props {
  application: Application | undefined;
  missing: boolean;
  mode: 'side' | 'drawer';
  onClose: () => void;
  onOpen: (id: string) => void;
}

export function DetailPanel({ application, missing, mode, onClose, onOpen }: Props) {
  const panel = useRef<HTMLElement>(null);
  const open = Boolean(application) || missing;

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isTypingTarget(event.target)) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (mode === 'drawer' && application) panel.current?.focus();
  }, [mode, application]);

  if (mode === 'drawer' && !open) return null;

  return (
    <aside
      ref={panel}
      className={styles.panel}
      data-mode={mode}
      data-open={open || undefined}
      aria-label={application || missing ? 'Application details' : 'Today'}
      tabIndex={-1}
    >
      {open && (
        <button type="button" className={`btn btn-icon ${styles.close}`} onClick={onClose} aria-label="Close details">
          <CloseIcon />
        </button>
      )}
      {application ? (
        <Details key={application.id} application={application} />
      ) : missing ? (
        <p className={styles.empty}>This application no longer exists.</p>
      ) : (
        <TodayOverview onOpen={onOpen} />
      )}
    </aside>
  );
}

function Details({ application }: { application: Application }) {
  const update = useUpdateApplication();
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'e' && !hasModifier(event) && !isTypingTarget(event.target)) {
        event.preventDefault();
        setEditing(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const setStatus = (status: string) => {
    if (status === application.status) return;
    update.mutate({ id: application.id, changes: { status: status as BoardStatus } });
  };

  return (
    <>
      <p className={styles.eyebrow}>Application</p>
      <h2 className={styles.company}>
        {isMissing(application.company) ? <span className="muted">Company not found</span> : application.company}
      </h2>
      <p className={styles.role}>
        {isMissing(application.role) ? <span className="muted">Role not found</span> : application.role}
      </p>

      <dl className={styles.facts}>
        <div>
          <dt>Status</dt>
          <dd>
            <span className={statusClass(application.status)}>{application.status}</span>
            <ProgressSteps step={application.progress_step} />
          </dd>
        </div>
        <div>
          <dt>Applied</dt>
          <dd className="mono">{shortDate(application.applied_date)}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{SOURCES[application.source ?? ''] ?? application.source ?? '—'}</dd>
        </div>
        <div>
          <dt>Emails</dt>
          <dd className="mono">{application.email_count}</dd>
        </div>
        {application.interview_held ? (
          <div className={styles.wide}>
            <dt>Interview</dt>
            <dd className="stale">{heldText(application)}</dd>
          </div>
        ) : (
          application.interview_date && (
            <div className={styles.wide}>
              <dt>Interview</dt>
              <dd className="status-Interview">{interviewDate(application.interview_date)}</dd>
            </div>
          )
        )}
        {application.no_reply_days != null && (
          <div className={styles.wide}>
            <dt>Last activity</dt>
            <dd className="stale">No reply · {application.no_reply_days} days</dd>
          </div>
        )}
        {application.status !== 'Needs Review' && <CountAs application={application} />}
      </dl>

      {application.needs_followup && <FollowUp application={application} />}

      <div className={styles.actions}>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger className="btn">Change status</DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="overlay-menu" align="start" sideOffset={4}>
              <DropdownMenu.RadioGroup value={application.status} onValueChange={setStatus}>
                {BOARD_STATUSES.map((status) => (
                  <DropdownMenu.RadioItem key={status} value={status} className="overlay-item">
                    <span className={statusClass(status)}>{status}</span>
                    <DropdownMenu.ItemIndicator>
                      <CheckIcon />
                    </DropdownMenu.ItemIndicator>
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <button type="button" className="btn" onClick={() => setEditing(true)}>
          Edit details
        </button>
      </div>
      {update.isError && (
        <p className="error-text" role="alert">
          Status not changed: {update.error.message}
        </p>
      )}

      <section aria-labelledby="timeline-title">
        <h3 id="timeline-title" className={styles.sectionTitle}>
          Timeline
        </h3>
        {application.timeline.length === 0 ? (
          <p className={styles.timelineEmpty}>No emails yet.</p>
        ) : (
          <ol className={styles.timeline}>
            {application.timeline.map((event, index) => (
              <li key={`${event.date}-${index}`} className={styles.event}>
                <span className="mono">{shortDate(event.date)}</span>
                <div>
                  <p className={styles.subject}>{event.subject || '(no subject)'}</p>
                  {event.change && <p className={styles.change}>{event.change}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <NotesEditor applicationId={application.id} initial={application.notes ?? ''} />
      <EditDetailsDialog application={application} open={editing} onOpenChange={setEditing} />
    </>
  );
}

const OUTCOMES: { value: InterviewOutcome; label: string }[] = [
  { value: 'rejected', label: 'Rejected' },
  { value: 'next_round', label: 'Next round' },
  { value: 'offer', label: 'Offer' },
  { value: 'no_answer', label: 'No answer yet' },
];

function FollowUp({ application }: { application: Application }) {
  const outcome = useInterviewOutcome();
  return (
    <div className={styles.followUp} role="group" aria-labelledby="follow-up-title">
      <p id="follow-up-title" className={styles.followUpTitle}>
        How did it go?
      </p>
      <div className={styles.followUpOptions}>
        {OUTCOMES.map((option) => (
          <button
            key={option.value}
            type="button"
            className="btn"
            disabled={outcome.isPending}
            onClick={() => outcome.mutate({ id: application.id, outcome: option.value })}
          >
            {option.label}
          </button>
        ))}
      </div>
      {outcome.isError && (
        <p className="error-text" role="alert">
          Not saved: {outcome.error.message}
        </p>
      )}
    </div>
  );
}
