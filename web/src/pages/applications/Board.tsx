import { useMemo, useState, type DragEvent, type ReactNode } from 'react';
import { useUpdateApplication } from '../../api/queries';
import { BOARD_STATUSES, type Application, type BoardStatus } from '../../api/types';
import { heldText, isMissing } from '../../lib/applications';
import { interviewDate, plural, shortDate, toDate } from '../../lib/format';
import styles from './Board.module.css';

export const CARDS_PER_COLUMN = 6;
const DRAG_TYPE = 'application/x-job-application';

interface Props {
  applications: Application[];
  onOpen: (id: string) => void;
}

export function Board({ applications, onOpen }: Props) {
  const update = useUpdateApplication();
  const [announcement, setAnnouncement] = useState('');
  const [dropTarget, setDropTarget] = useState<BoardStatus | null>(null);

  const columns = useMemo(() => {
    const byStatus = new Map<BoardStatus, Application[]>(BOARD_STATUSES.map((status) => [status, []]));
    for (const app of applications) byStatus.get(app.status as BoardStatus)?.push(app);
    for (const list of byStatus.values()) {
      list.sort((a, b) => (toDate(b.last_activity_at)?.getTime() ?? 0) - (toDate(a.last_activity_at)?.getTime() ?? 0));
    }
    return byStatus;
  }, [applications]);

  const move = (id: string, status: BoardStatus) => {
    const app = applications.find((item) => item.id === id);
    if (!app || app.status === status) return;
    update.mutate(
      { id, changes: { status } },
      {
        onSuccess: () => setAnnouncement(`${app.company ?? 'Application'} moved to ${status}.`),
        onError: (error) => setAnnouncement(`${app.company ?? 'Application'} was not moved: ${error.message}`),
      },
    );
  };

  return (
    <>
      <div className={styles.board}>
        {BOARD_STATUSES.map((status) => (
          <Column
            key={status}
            status={status}
            applications={columns.get(status) ?? []}
            isDropTarget={dropTarget === status}
            onDragTarget={setDropTarget}
            onDrop={move}
            onOpen={onOpen}
          />
        ))}
      </div>
      <p className={styles.hint}>
        Drag a card to change its status. Your change always wins over the next sync.
        <span className="visually-hidden"> Without a mouse, open a card and use Change status.</span>
      </p>
      {update.isError && (
        <p className="error-text" role="alert">
          {announcement}
        </p>
      )}
      <p className="visually-hidden" role="status" aria-live="polite">
        {update.isError ? '' : announcement}
      </p>
    </>
  );
}

interface ColumnProps {
  status: BoardStatus;
  applications: Application[];
  isDropTarget: boolean;
  onDragTarget: (status: BoardStatus | null) => void;
  onDrop: (id: string, status: BoardStatus) => void;
  onOpen: (id: string) => void;
}

function Column({ status, applications, isDropTarget, onDragTarget, onDrop, onOpen }: ColumnProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? applications : applications.slice(0, CARDS_PER_COLUMN);
  const hidden = applications.length - visible.length;
  const headingId = `board-${status}`;

  const accepts = (event: DragEvent) => event.dataTransfer.types.includes(DRAG_TYPE);

  return (
    <section
      className={styles.column}
      aria-labelledby={headingId}
      data-drop-target={isDropTarget || undefined}
      onDragOver={(event) => {
        if (!accepts(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        onDragTarget(status);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) onDragTarget(null);
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDragTarget(null);
        const id = event.dataTransfer.getData(DRAG_TYPE);
        if (id) onDrop(id, status);
      }}
    >
      <h2 id={headingId} className={styles.columnTitle}>
        {status}
        <span className={styles.columnCount}>{applications.length}</span>
      </h2>
      {applications.length === 0 ? (
        <p className={styles.emptyColumn}>Nothing here yet.</p>
      ) : (
        <ul className={styles.cards}>
          {visible.map((app) => (
            <li key={app.id}>
              <Card application={app} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <button type="button" className={`link-button ${styles.more}`} onClick={() => setExpanded(true)}>
          Show {hidden} more
        </button>
      )}
    </section>
  );
}

function Card({ application, onOpen }: { application: Application; onOpen: (id: string) => void }) {
  let meta: ReactNode;
  if (application.interview_held) {
    meta = <span className="stale">{heldText(application)}</span>;
  } else if (application.status === 'Interview' && application.interview_date) {
    meta = <span className="status-Interview">Interview {interviewDate(application.interview_date)}</span>;
  } else if (application.no_reply_days != null) {
    meta = <span className="stale">No reply · {application.no_reply_days} days</span>;
  } else {
    meta = (
      <span className="mono">
        {shortDate(application.last_activity_at)} · {plural(application.email_count, 'email')}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={styles.card}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData(DRAG_TYPE, application.id);
        event.dataTransfer.effectAllowed = 'move';
      }}
      onClick={() => onOpen(application.id)}
    >
      <span className={styles.company}>
        {isMissing(application.company) ? <span className="muted">Company not found</span> : application.company}
      </span>
      <span className={styles.role}>
        {isMissing(application.role) ? <span className="muted">Role not found</span> : application.role}
      </span>
      <span className={styles.meta}>{meta}</span>
    </button>
  );
}
