import { useCallback } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  useConvertOpportunity,
  useDismissOpportunity,
  useOpportunities,
  type OpportunityFilter,
} from '../../api/queries';
import type { Opportunity } from '../../api/types';
import { EmailView } from '../../components/EmailView';
import { Empty, ErrorState, Loading } from '../../components/States';
import { CloseIcon } from '../../components/Icons';
import { shortDate } from '../../lib/format';
import { senderName } from '../../lib/review';
import styles from './OpportunitiesPage.module.css';

const STATUS_LABEL: Record<string, string> = { open: 'Open', converted: 'Applied', dismissed: 'Dismissed' };

function OpportunityDetail({ opportunity, onClose }: { opportunity: Opportunity; onClose: () => void }) {
  const navigate = useNavigate();
  const convert = useConvertOpportunity();
  const dismiss = useDismissOpportunity();
  const busy = convert.isPending || dismiss.isPending;
  const error = convert.error ?? dismiss.error;

  return (
    <aside className={styles.detail} aria-label="Opportunity">
      <button type="button" className={`btn btn-icon ${styles.close}`} onClick={onClose} aria-label="Close email">
        <CloseIcon />
      </button>
      <p className={styles.eyebrow}>
        {[opportunity.company, opportunity.role].filter(Boolean).join(' · ') || 'Recruiter outreach'}
      </p>
      {opportunity.status === 'open' ? (
        <div className={styles.actions}>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() =>
              convert.mutate(opportunity.id, { onSuccess: (created) => navigate(`/applications?id=${created.id}`) })
            }>
            {convert.isPending ? 'Converting…' : 'Convert to application'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => dismiss.mutate(opportunity.id)}>
            Dismiss
          </button>
        </div>
      ) : (
        <p className={styles.done} role="status">
          {opportunity.status === 'converted' ? 'You applied.' : 'Dismissed.'}
          {opportunity.application_id && (
            <>
              {' '}
              <Link to={`/applications?id=${opportunity.application_id}`}>Open the application</Link>
            </>
          )}
        </p>
      )}
      {error && (
        <p className="error-text" role="alert">
          That didn’t work. {error.message}
        </p>
      )}
      <EmailView
        messageId={opportunity.message_id ?? null}
        subject={opportunity.subject}
        sender={opportunity.sender}
        date={opportunity.date}
      />
    </aside>
  );
}

export function OpportunitiesPage() {
  const [params, setParams] = useSearchParams();
  const filter: OpportunityFilter = params.get('show') === 'all' ? 'all' : 'open';
  const opportunities = useOpportunities(filter);
  const selectedId = params.get('id');
  const selected = opportunities.data?.find((o) => o.id === selectedId);

  const update = useCallback(
    (changes: Record<string, string | null>) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  const list = opportunities.data ?? [];

  return (
    <div className={styles.page}>
      <section className={styles.content} aria-labelledby="opportunities-title">
        <div className={styles.titleRow}>
          <h1 id="opportunities-title" className={styles.title}>
            Opportunities
            {opportunities.data && <span className={styles.total}>{list.length}</span>}
          </h1>
          <div className={styles.toggle} role="group" aria-label="Show">
            <button type="button" aria-pressed={filter === 'open'} onClick={() => update({ show: null })}>
              Open
            </button>
            <button type="button" aria-pressed={filter === 'all'} onClick={() => update({ show: 'all' })}>
              All
            </button>
          </div>
        </div>
        <p className={styles.lead}>Recruiters who reached out. They become applications once you apply.</p>
        {opportunities.isPending ? (
          <Loading>Loading opportunities…</Loading>
        ) : opportunities.isError ? (
          <ErrorState
            message={`Couldn’t load opportunities. ${opportunities.error.message}`}
            onRetry={() => void opportunities.refetch()}
          />
        ) : list.length === 0 ? (
          <Empty title={filter === 'open' ? 'No open opportunities.' : 'No opportunities yet.'}>
            <p>When a recruiter writes to you first, it shows up here instead of in your applications.</p>
          </Empty>
        ) : (
          <div className={styles.scroller}>
            <table className={styles.table}>
              <caption className="visually-hidden">Opportunities</caption>
              <colgroup>
                <col className={styles.colCompany} />
                <col className={styles.colRole} />
                <col className={styles.colSender} />
                <col className={styles.colDate} />
                <col className={styles.colStatus} />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col">Role</th>
                  <th scope="col">From</th>
                  <th scope="col">Date</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {list.map((o) => (
                  <tr
                    key={o.id}
                    className={styles.row}
                    data-open={o.id === selectedId || undefined}
                    aria-current={o.id === selectedId ? 'true' : undefined}
                    onClick={(event) => {
                      if ((event.target as HTMLElement).closest('button')) return;
                      update({ id: o.id });
                    }}
                  >
                    <td>
                      <button type="button" className={styles.open} onClick={() => update({ id: o.id })}>
                        {o.company || 'Unknown company'}
                      </button>
                    </td>
                    <td>{o.role || '—'}</td>
                    <td title={o.sender ?? undefined}>{senderName(o.sender) ?? '—'}</td>
                    <td className="mono">{shortDate(o.date)}</td>
                    <td className={o.status === 'open' ? undefined : styles.muted}>
                      {STATUS_LABEL[o.status] ?? o.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {selected && <OpportunityDetail key={selected.id} opportunity={selected} onClose={() => update({ id: null })} />}
    </div>
  );
}
