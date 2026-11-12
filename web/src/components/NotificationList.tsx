import { useNavigate } from 'react-router-dom';
import { useMarkRead } from '../api/queries';
import type { Notification } from '../api/types';
import { timeAgo } from '../lib/format';
import { useNow } from '../lib/useNow';
import styles from './NotificationList.module.css';

interface Props {
  items: Notification[];
  onOpen?: () => void;
}

/** Each notification opens the application or page it is about, and counts as read. */
export function NotificationList({ items, onOpen }: Props) {
  const navigate = useNavigate();
  const markRead = useMarkRead();
  const now = useNow();

  const open = (item: Notification) => {
    if (!item.read_at) markRead.mutate(item.id);
    onOpen?.();
    if (item.link) navigate(item.link);
  };

  return (
    <ul className={styles.list}>
      {items.map((item) => {
        const time = timeAgo(item.created_at, now);
        const label = [`${item.title}${item.read_at ? '' : ', unread'}`, item.body, time].filter(Boolean).join('. ');
        return (
          <li key={item.id}>
            <button
              type="button"
              className={styles.item}
              data-unread={!item.read_at || undefined}
              aria-label={label}
              onClick={() => open(item)}
            >
              <span className={styles.dot} aria-hidden="true" />
              <span className={styles.text}>
                <span className={styles.title}>{item.title}</span>
                {item.body && <span className={styles.body}>{item.body}</span>}
              </span>
              <span className={styles.time}>{time}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
