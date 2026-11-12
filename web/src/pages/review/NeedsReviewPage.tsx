import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApplications } from '../../api/queries';
import type { Application } from '../../api/types';
import { EmailView } from '../../components/EmailView';
import { Empty, ErrorState, Loading } from '../../components/States';
import { shortDate } from '../../lib/format';
import { emailSummary, reviewQueue, senderName } from '../../lib/review';
import { AiReviewButton } from './AiReviewButton';
import { DecisionForm } from './DecisionForm';
import styles from './NeedsReviewPage.module.css';

const VISIBLE = 5;

export function NeedsReviewPage() {
  const applications = useApplications();
  const [params, setParams] = useSearchParams();
  const [expanded, setExpanded] = useState(false);
  const queue = useMemo(() => reviewQueue(applications.data ?? []), [applications.data]);

  const requested = params.get('id');
  const index = Math.max(
    queue.findIndex((app) => app.id === requested),
    0,
  );
  const selected: Application | undefined = queue[index];

  const select = useCallback(
    (id: string | null) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (id) next.set('id', id);
          else next.delete('id');
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  const nextId = (current: Application) => {
    const position = queue.findIndex((app) => app.id === current.id);
    const after = queue.slice(position + 1).concat(queue.slice(0, position));
    return after[0]?.id ?? null;
  };

  if (applications.isPending) {
    return (
      <div className={styles.single}>
        <Loading>Loading emails to review…</Loading>
      </div>
    );
  }
  if (applications.isError) {
    return (
      <div className={styles.single}>
        <ErrorState
          message={`Couldn’t load emails to review. ${applications.error.message}`}
          onRetry={() => void applications.refetch()}
        />
      </div>
    );
  }

  const showAll = expanded || index >= VISIBLE;
  const visible = showAll ? queue : queue.slice(0, VISIBLE);

  return (
    <div className={styles.page}>
      <section className={styles.queue} aria-labelledby="review-title">
        <div className={styles.intro}>
          <h1 id="review-title" className={styles.title}>
            Needs review
          </h1>
          <p className={styles.lead}>
            Emails the rules weren’t sure about. Decide each one, or let your AI go through them.
          </p>
          {queue.length > 0 && <AiReviewButton />}
        </div>
        {queue.length > 0 && (
          <ul className={styles.list} aria-label="Emails to review">
            {visible.map((app) => {
              const email = emailSummary(app);
              const current = app.id === selected?.id;
              return (
                <li key={app.id}>
                  <button
                    type="button"
                    className={styles.item}
                    aria-current={current ? 'true' : undefined}
                    onClick={() => select(app.id)}
                  >
                    <span className={styles.itemTop}>
                      <span className={styles.from}>{senderName(email.sender) ?? app.company ?? 'Unknown sender'}</span>
                      <span className={`mono ${styles.date}`}>{shortDate(email.date)}</span>
                    </span>
                    <span className={styles.itemSubject}>{email.subject ?? '(no subject)'}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {!showAll && queue.length > VISIBLE && (
          <button type="button" className={styles.more} onClick={() => setExpanded(true)}>
            {queue.length - VISIBLE} more
          </button>
        )}
      </section>
      <section className={styles.detail} aria-label="Selected email">
        {selected ? (
          <>
            <EmailView {...emailSummary(selected)} />
            <DecisionForm key={selected.id} application={selected} onDone={() => select(nextId(selected))} />
          </>
        ) : (
          <Empty title="Nothing to review.">
            <p>New emails the rules aren’t sure about will show up here after a sync.</p>
          </Empty>
        )}
      </section>
    </div>
  );
}
