import { useMarkAllRead, useNotifications, useUnreadCount } from '../../api/queries';
import { NotificationList } from '../../components/NotificationList';
import { Empty, ErrorState, Loading } from '../../components/States';
import styles from './NotificationsPage.module.css';

const PAGE_LIMIT = 200;

export function NotificationsPage() {
  const list = useNotifications(PAGE_LIMIT);
  const unread = useUnreadCount().data?.unread ?? 0;
  const markAll = useMarkAllRead();

  return (
    <section className={styles.page} aria-labelledby="notifications-title">
      <div className={styles.titleRow}>
        <h1 id="notifications-title" className={styles.title}>
          Notifications
        </h1>
        {unread > 0 && (
          <button type="button" className="btn" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
            Mark all read
          </button>
        )}
      </div>
      <p className={styles.lead}>Kept on this computer for 90 days. Nothing is sent anywhere.</p>
      {list.isPending ? (
        <Loading>Loading notifications…</Loading>
      ) : list.isError ? (
        <ErrorState message={`Couldn’t load notifications. ${list.error.message}`} onRetry={() => void list.refetch()} />
      ) : list.data.length === 0 ? (
        <Empty title="No notifications yet.">
          <p>New rejections, interviews, reminders and a weekly summary will show up here.</p>
        </Empty>
      ) : (
        <div className={styles.list}>
          <NotificationList items={list.data} />
        </div>
      )}
    </section>
  );
}
