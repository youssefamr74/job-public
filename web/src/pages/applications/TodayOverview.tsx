import { useToday } from '../../api/queries';
import type { AttentionItem } from '../../api/types';
import { heldText, isMissing } from '../../lib/applications';
import { interviewDate } from '../../lib/format';
import styles from './TodayOverview.module.css';

function reasonText(item: AttentionItem): string {
  switch (item.reason) {
    case 'interview_held':
      return heldText({ interview_date: item.date ?? null, no_news_days: item.days ?? null });
    case 'action_needed':
      return 'The employer is waiting for something from you';
    case 'no_reply':
      return `No reply · ${item.days} days`;
  }
}

function name(item: { company: string | null; role: string | null }) {
  const company = isMissing(item.company) ? 'Company not found' : item.company;
  return isMissing(item.role) ? company : `${company} · ${item.role}`;
}

export function TodayOverview({ onOpen }: { onOpen: (id: string) => void }) {
  const today = useToday();

  return (
    <div className={styles.today}>
      <h2 className={styles.title}>Today</h2>
      {today.isPending ? (
        <p className={styles.note} role="status">
          Loading…
        </p>
      ) : today.isError ? (
        <p className={styles.note} role="alert">
          Couldn’t load the overview. {today.error.message}
        </p>
      ) : (
        <>
          <section aria-labelledby="today-coming-up">
            <h3 id="today-coming-up" className={styles.heading}>
              Coming up
            </h3>
            {today.data.coming_up.length === 0 ? (
              <p className={styles.note}>No interviews scheduled.</p>
            ) : (
              <ul className={styles.list}>
                {today.data.coming_up.map((item) => (
                  <li key={item.id}>
                    <button type="button" className={styles.item} onClick={() => onOpen(item.id)}>
                      <span className={styles.name}>{name(item)}</span>
                      <span className={`${styles.detail} status-Interview`}>{interviewDate(item.date)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="today-attention">
            <h3 id="today-attention" className={styles.heading}>
              Needs your attention
            </h3>
            {today.data.attention.length === 0 ? (
              <p className={styles.note}>Nothing needs you right now.</p>
            ) : (
              <ul className={styles.list}>
                {today.data.attention.map((item) => (
                  <li key={`${item.reason}-${item.id}`}>
                    <button type="button" className={styles.item} onClick={() => onOpen(item.id)}>
                      <span className={styles.name}>{name(item)}</span>
                      <span className={`${styles.detail} stale`}>{reasonText(item)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="today-week">
            <h3 id="today-week" className={styles.heading}>
              This week
            </h3>
            <dl className={styles.numbers}>
              <div>
                <dt>applied</dt>
                <dd>{today.data.this_week.applied}</dd>
              </div>
              <div>
                <dt>replies</dt>
                <dd>{today.data.this_week.replies}</dd>
              </div>
              <div>
                <dt>interviews</dt>
                <dd>{today.data.this_week.interviews}</dd>
              </div>
            </dl>
          </section>
        </>
      )}
      <p className={styles.hint}>
        <kbd>J</kbd> / <kbd>K</kbd> to move · <kbd>Enter</kbd> to open
      </p>
    </div>
  );
}
