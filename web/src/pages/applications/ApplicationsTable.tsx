import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import type { Application } from '../../api/types';
import { isMissing, STATUS_ORDER, statusClass } from '../../lib/applications';
import { dateGroup, shortDate, toDate } from '../../lib/format';
import { ActivityText } from '../../components/ActivityText';
import { ProgressSteps } from '../../components/ProgressSteps';
import { hasModifier, isTypingTarget } from '../../lib/keyboard';
import { useNow } from '../../lib/useNow';
import styles from './ApplicationsTable.module.css';

const column = createColumnHelper<Application>();

function time(value: string | null | undefined): number {
  return toDate(value)?.getTime() ?? 0;
}

interface Props {
  applications: Application[];
  selectedId: string | null;
  onOpen: (id: string) => void;
}

export function ApplicationsTable({ applications, selectedId, onOpen }: Props) {
  const now = useNow(60_000);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'applied', desc: true }]);
  const [cursorId, setCursorId] = useState<string | null>(selectedId);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());

  const columns = useMemo(
    () => [
      column.accessor((app) => app.company ?? '', {
        id: 'company',
        header: 'Company',
        cell: ({ row }) => (
          <button type="button" className={styles.open} onClick={() => onOpen(row.original.id)}>
            {isMissing(row.original.company) ? <span className="muted">Company not found</span> : row.original.company}
          </button>
        ),
      }),
      column.accessor((app) => (isMissing(app.role) ? '' : (app.role ?? '')), {
        id: 'role',
        header: 'Role',
        cell: ({ row }) =>
          isMissing(row.original.role) ? <span className="muted">Role not found</span> : row.original.role,
      }),
      column.accessor('status', {
        header: 'Status',
        sortingFn: (a, b) => (STATUS_ORDER[a.original.status] ?? 9) - (STATUS_ORDER[b.original.status] ?? 9),
        cell: ({ row }) => (
          <>
            <span className={statusClass(row.original.status)}>{row.original.status}</span>
            <ProgressSteps step={row.original.progress_step} />
          </>
        ),
      }),
      column.accessor((app) => time(app.applied_date), {
        id: 'applied',
        header: 'Applied',
        cell: ({ row }) => <span className="mono">{shortDate(row.original.applied_date, now)}</span>,
      }),
      column.accessor((app) => time(app.last_activity_at), {
        id: 'activity',
        header: 'Last activity',
        cell: ({ row }) => <ActivityText application={row.original} now={now} />,
      }),
      column.accessor('email_count', {
        id: 'emails',
        header: 'Emails',
        cell: ({ getValue }) => <span className="mono">{getValue()}</span>,
      }),
    ],
    [now, onOpen],
  );

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: applications,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (app) => app.id,
    sortDescFirst: false,
  });
  const rows = table.getRowModel().rows;
  const sortedBy = sorting[0]?.id;
  const groupField = sortedBy === 'applied' ? 'applied_date' : sortedBy === 'activity' ? 'last_activity_at' : null;

  useEffect(() => {
    if (selectedId) setCursorId(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (hasModifier(event) || event.shiftKey || isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key !== 'j' && key !== 'k' && key !== 'enter') return;
      if (rows.length === 0) return;
      const index = rows.findIndex((row) => row.id === cursorId);

      if (key === 'enter') {
        const current = rows[index];
        const focusIsFree = event.target === document.body || (event.target as HTMLElement).tagName === 'TR';
        if (!focusIsFree || !current) return;
        event.preventDefault();
        onOpen(current.id);
        return;
      }
      event.preventDefault();
      const next = key === 'j' ? Math.min(index + 1, rows.length - 1) : Math.max(index - 1, 0);
      const target = rows[index < 0 ? 0 : next];
      if (!target) return;
      const id = target.id;
      setCursorId(id);
      rowRefs.current.get(id)?.scrollIntoView({ block: 'nearest' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rows, cursorId, onOpen]);

  return (
    <>
      <div className={styles.scroller}>
        <table className={styles.table}>
          <caption className="visually-hidden">Applications. Column headers sort the table.</caption>
          <colgroup>
            <col className={styles.colCompany} />
            <col className={styles.colRole} />
            <col className={styles.colStatus} />
            <col className={styles.colApplied} />
            <col className={styles.colActivity} />
            <col className={styles.colEmails} />
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className={styles[`cell-${header.id}`]}
                      aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    >
                      <button type="button" className={styles.sort} onClick={header.column.getToggleSortingHandler()}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <span className={styles.arrow} aria-hidden="true">
                          {sorted === 'asc' ? '↑' : sorted === 'desc' ? '↓' : ''}
                        </span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const group = groupField ? dateGroup(row.original[groupField], now) : null;
              const previous = rows[index - 1];
              const showGroup =
                groupField !== null && (!previous || dateGroup(previous.original[groupField], now) !== group);
              return (
              <Fragment key={row.id}>
              {showGroup && (
                <tr className={styles.group}>
                  <th scope="colgroup" colSpan={row.getVisibleCells().length}>
                    {group}
                  </th>
                </tr>
              )}
              <tr
                ref={(element) => {
                  if (element) rowRefs.current.set(row.id, element);
                  else rowRefs.current.delete(row.id);
                }}
                className={styles.row}
                data-open={row.id === selectedId || undefined}
                data-cursor={row.id === cursorId || undefined}
                aria-current={row.id === selectedId ? 'true' : undefined}
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest('button')) return;
                  setCursorId(row.id);
                  onOpen(row.id);
                }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className={styles[`cell-${cell.column.id}`]}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
              </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.hint}>
        <kbd>J</kbd> / <kbd>K</kbd> to move · <kbd>Enter</kbd> to open · <kbd>E</kbd> to edit
      </p>
    </>
  );
}
