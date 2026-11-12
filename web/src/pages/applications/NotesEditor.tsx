import { useCallback, useEffect, useRef, useState } from 'react';
import { useUpdateApplication } from '../../api/queries';
import styles from './DetailPanel.module.css';

export const NOTES_SAVE_DELAY_MS = 800;

interface Props {
  applicationId: string;
  initial: string;
}

export function NotesEditor({ applicationId, initial }: Props) {
  const update = useUpdateApplication();
  const [value, setValue] = useState(initial);
  const saved = useRef<string | null>(initial);
  const latest = useRef(initial);
  const timer = useRef<number | undefined>(undefined);
  const { mutate } = update;

  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    if (latest.current === saved.current) return;
    const notes = latest.current;
    saved.current = notes;
    mutate(
      { id: applicationId, changes: { notes } },
      {
        onError: () => {
          if (saved.current === notes) saved.current = null;
        },
      },
    );
  }, [applicationId, mutate]);

  useEffect(() => flush, [flush]);

  const change = (next: string) => {
    setValue(next);
    latest.current = next;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, NOTES_SAVE_DELAY_MS);
  };

  let state = '';
  if (update.isPending) state = 'Saving…';
  else if (update.isError) state = 'Not saved. Keep typing or leave the field to try again.';
  else if (update.isSuccess) state = 'Saved';

  return (
    <div className={styles.notes}>
      <div className={styles.notesHeader}>
        <label htmlFor="application-notes" className={styles.sectionTitle}>
          Notes
        </label>
        <span className={update.isError ? 'error-text' : styles.saveState} role="status" aria-live="polite">
          {state}
        </span>
      </div>
      <textarea
        id="application-notes"
        className={styles.textarea}
        placeholder="Recruiter name, salary range, what to prepare"
        value={value}
        onChange={(event) => change(event.target.value)}
        onBlur={flush}
        maxLength={20000}
      />
    </div>
  );
}
