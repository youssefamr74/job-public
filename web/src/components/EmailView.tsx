import { useMessage } from '../api/queries';
import { ApiError } from '../api/client';
import { emailDate } from '../lib/format';
import styles from './EmailView.module.css';

interface Props {
  messageId: string | null;
  subject: string | null | undefined;
  sender: string | null | undefined;
  date?: string | null;
  snippet?: string | null;
  headingLevel?: 2 | 3;
}

function paragraphs(body: string): string[][] {
  return body
    .split(/\n{2,}/)
    .map((block) => block.split('\n'))
    .filter((lines) => lines.some((line) => line.trim()));
}

function Body({ text }: { text: string }) {
  return (
    <div className={styles.body}>
      {paragraphs(text).map((lines, index) => (
        <p key={index}>
          {lines.map((line, i) => (
            <span key={i}>
              {i > 0 && <br />}
              {line}
            </span>
          ))}
        </p>
      ))}
    </div>
  );
}

function errorText(error: Error): string {
  if (error instanceof ApiError && error.status === 404) return 'This email is no longer in your mailbox.';
  return `Couldn’t load the email. ${error.message}`;
}

/** An email read from the mail source on demand; falls back to what the sync kept when it can't be opened. */
export function EmailView({ messageId, subject, sender, date, snippet, headingLevel = 2 }: Props) {
  const message = useMessage(messageId);
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  const data = message.data;
  const shownSubject = data?.subject || subject || '(no subject)';
  const shownSender = data?.sender || sender;
  const shownDate = data?.date ?? date;

  return (
    <article className={styles.email} aria-label="Email">
      <Heading className={styles.subject}>{shownSubject}</Heading>
      <p className={styles.meta}>
        {shownSender}
        {shownSender && shownDate && ' · '}
        {shownDate && <span className="mono">{emailDate(shownDate)}</span>}
      </p>
      {!messageId ? (
        <>
          {snippet && <Body text={snippet} />}
          <p className={styles.note}>The full email isn’t available for this one.</p>
        </>
      ) : message.isPending ? (
        <p className={styles.note} role="status">
          Loading the email…
        </p>
      ) : message.isError ? (
        <div className={styles.note} role="alert">
          <p>{errorText(message.error)}</p>
          {snippet && <Body text={snippet} />}
          <button type="button" className="link-button" onClick={() => void message.refetch()}>
            Try again
          </button>
        </div>
      ) : data?.body ? (
        <Body text={data.body} />
      ) : (
        <p className={styles.note}>This email has no text.</p>
      )}
    </article>
  );
}
