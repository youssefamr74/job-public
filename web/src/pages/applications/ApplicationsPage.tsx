import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApplications } from '../../api/queries';
import { applyFilters, isTracked, matchesQuery, statusSummary, type DateRange, type Filters } from '../../lib/applications';
import { Empty, ErrorState, Loading } from '../../components/States';
import { AddApplicationDialog } from './AddApplicationDialog';
import { ApplicationsTable } from './ApplicationsTable';
import { Board } from './Board';
import { DetailPanel } from './DetailPanel';
import { FilterBar } from './FilterBar';
import styles from './ApplicationsPage.module.css';

type View = 'list' | 'board';

const DEFAULT_RANGE: DateRange = '60';
const RANGES = new Set<DateRange>(['30', '60', '90', 'all']);

function useApplicationsParams() {
  const [params, setParams] = useSearchParams();
  const view: View = params.get('view') === 'board' ? 'board' : 'list';
  const status = params.get('status');
  const rangeParam = params.get('range') as DateRange | null;
  const noReply = params.get('noreply') === '1';
  const query = params.get('q') ?? '';
  const filters = useMemo<Filters>(
    () => ({
      status,
      range: rangeParam && RANGES.has(rangeParam) ? rangeParam : DEFAULT_RANGE,
      noReply,
      query,
    }),
    [status, rangeParam, noReply, query],
  );
  const selectedId = params.get('id');

  const update = useCallback(
    (changes: Record<string, string | null>) => {
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
      );
    },
    [setParams],
  );

  return { view, filters, selectedId, update };
}

export function ApplicationsPage() {
  const applications = useApplications();
  const { view, filters, selectedId, update } = useApplicationsParams();
  const [adding, setAdding] = useState(false);

  const tracked = useMemo(() => (applications.data ?? []).filter(isTracked), [applications.data]);
  const filtered = useMemo(() => applyFilters(tracked, filters), [tracked, filters]);
  const searched = useMemo(() => tracked.filter((app) => matchesQuery(app, filters.query)), [tracked, filters.query]);
  const selected = selectedId ? applications.data?.find((app) => app.id === selectedId) : undefined;

  const open = useCallback((id: string | null) => update({ id }), [update]);
  const setFilters = (changes: Partial<Filters>) =>
    update({
      ...('status' in changes ? { status: changes.status ?? null } : {}),
      ...('range' in changes ? { range: changes.range === DEFAULT_RANGE ? null : (changes.range ?? null) } : {}),
      ...('noReply' in changes ? { noreply: changes.noReply ? '1' : null } : {}),
    });
  const clearFilters = () => update({ status: null, range: 'all', noreply: null, q: null });

  let body: ReactNode;
  if (applications.isPending) {
    body = <Loading>Loading applications…</Loading>;
  } else if (applications.isError) {
    body = (
      <ErrorState
        message={`Couldn’t load applications. ${applications.error.message}`}
        onRetry={() => void applications.refetch()}
      />
    );
  } else if (tracked.length === 0) {
    body = (
      <Empty title="No applications yet.">
        <p>Sync your mail to find them, or add one by hand.</p>
      </Empty>
    );
  } else if (view === 'board') {
    body = <Board applications={searched} onOpen={open} />;
  } else {
    body = (
      <>
        <FilterBar filters={filters} onChange={setFilters} summary={statusSummary(filtered)} />
        {filtered.length === 0 ? (
          <Empty title="No applications match these filters.">
            <button type="button" className="link-button" onClick={clearFilters}>
              Clear filters
            </button>
          </Empty>
        ) : (
          <ApplicationsTable applications={filtered} selectedId={selectedId} onOpen={open} />
        )}
      </>
    );
  }

  return (
    <div className={`${styles.page} ${view === 'board' ? styles.boardView : ''}`}>
      <section className={styles.content} aria-labelledby="applications-title">
        <div className={styles.titleRow}>
          <h1 id="applications-title" className={styles.title}>
            Applications
            {applications.data && <span className={styles.total}>{tracked.length}</span>}
          </h1>
          <div className={styles.titleActions}>
            <div className={styles.toggle} role="group" aria-label="View">
              <button type="button" aria-pressed={view === 'list'} onClick={() => update({ view: null })}>
                List
              </button>
              <button type="button" aria-pressed={view === 'board'} onClick={() => update({ view: 'board' })}>
                Board
              </button>
            </div>
            <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
              Add application
            </button>
          </div>
        </div>
        {body}
      </section>
      <DetailPanel
        application={selected}
        missing={Boolean(selectedId && applications.isSuccess && !selected)}
        mode={view === 'board' ? 'drawer' : 'side'}
        onClose={() => open(null)}
        onOpen={open}
      />
      <AddApplicationDialog open={adding} onOpenChange={setAdding} onCreated={(id) => open(id)} />
    </div>
  );
}
