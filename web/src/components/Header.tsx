import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import * as Popover from '@radix-ui/react-popover';
import {
  useApplications,
  useMarkAllRead,
  useNotifications,
  useOpenOpportunities,
  useUnreadCount,
} from '../api/queries';
import { NEEDS_REVIEW } from '../api/types';
import { hasModifier } from '../lib/keyboard';
import { BellIcon, SearchIcon, SettingsIcon } from './Icons';
import { NotificationList } from './NotificationList';
import { SyncStatus } from './SyncStatus';
import styles from './Header.module.css';

function Count({ value, label }: { value: number | undefined; label: string }) {
  if (value === undefined) return null;
  return (
    <span className={styles.count}>
      {value}
      <span className="visually-hidden"> {label}</span>
    </span>
  );
}

interface Props {
  onSyncError: (message: string | null) => void;
}

export function Header({ onSyncError }: Props) {
  const applications = useApplications();
  const opportunities = useOpenOpportunities();
  const needsReview = applications.data?.filter((app) => app.status === NEEDS_REVIEW).length;

  return (
    <header className={styles.header}>
      <Link to="/applications" className={styles.logo} aria-label="Jōb, applications">
        Jōb
      </Link>
      <nav className={styles.tabs} aria-label="Main">
        <NavLink to="/applications" className={styles.tab}>
          Applications
        </NavLink>
        <NavLink to="/review" className={styles.tab}>
          Needs review <Count value={needsReview} label="to review" />
        </NavLink>
        <NavLink to="/opportunities" className={styles.tab}>
          Opportunities <Count value={opportunities.data?.length} label="open" />
        </NavLink>
        <NavLink to="/analytics" className={styles.tab}>
          Analytics
        </NavLink>
      </nav>
      <div className={styles.actions}>
        <HeaderSearch />
        <SyncStatus onError={onSyncError} />
        <Notifications />
        <Link to="/settings" className="btn btn-icon" aria-label="Settings" title="Settings">
          <SettingsIcon />
        </Link>
      </div>
    </header>
  );
}

function HeaderSearch() {
  const input = useRef<HTMLInputElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const onApplications = location.pathname.startsWith('/applications');
  const value = onApplications ? (params.get('q') ?? '') : '';

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      } else if (event.key === '/' && !hasModifier(event) && document.activeElement === document.body) {
        event.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const change = (next: string) => {
    if (onApplications) {
      const updated = new URLSearchParams(params);
      if (next) updated.set('q', next);
      else updated.delete('q');
      setParams(updated, { replace: true });
    } else {
      navigate(`/applications?q=${encodeURIComponent(next)}`);
    }
  };

  return (
    <div className={styles.search} role="search">
      <SearchIcon />
      <label htmlFor="global-search" className="visually-hidden">
        Search companies or roles
      </label>
      <input
        ref={input}
        id="global-search"
        type="search"
        placeholder="Search companies or roles"
        autoComplete="off"
        value={value}
        onChange={(event) => change(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            if (value) change('');
            else input.current?.blur();
          }
        }}
      />
      <kbd className={styles.hint} aria-hidden="true">
        Ctrl K
      </kbd>
    </div>
  );
}

const POPOVER_LIMIT = 10;

function Notifications() {
  const [open, setOpen] = useState(false);
  const unread = useUnreadCount().data?.unread ?? 0;
  const list = useNotifications(POPOVER_LIMIT, open);
  const markAll = useMarkAllRead();
  const label = unread ? `Notifications, ${unread} unread` : 'Notifications, none unread';

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger className={`btn btn-icon ${styles.bell}`} aria-label={label} title="Notifications">
        <BellIcon />
        {unread > 0 && (
          <span className={styles.badge} aria-hidden="true">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className={`overlay-menu ${styles.notifications}`}
          align="end"
          sideOffset={6}
          aria-label="Notifications"
        >
          <div className={styles.notificationsHead}>
            <p className={styles.notificationsTitle}>Notifications</p>
            {unread > 0 && (
              <button type="button" className="link-button" onClick={() => markAll.mutate()}>
                Mark all read
              </button>
            )}
          </div>
          {list.isPending ? (
            <p className="muted" role="status">
              Loading…
            </p>
          ) : list.isError ? (
            <p className="error-text">Couldn’t load notifications. {list.error.message}</p>
          ) : list.data.length === 0 ? (
            <p className="muted">Nothing new. Status changes and reminders will show up here.</p>
          ) : (
            <NotificationList items={list.data} onOpen={() => setOpen(false)} />
          )}
          <Link to="/notifications" className={styles.notificationsAll} onClick={() => setOpen(false)}>
            See all notifications
          </Link>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
