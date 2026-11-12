import { useId, useState } from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import {
  useAIStatus,
  useMergeRoleGroups,
  useRoleGroups,
  useSuggestRoleGroups,
  useUndoRoleGroupMerge,
} from '../../api/queries';
import type { RoleGroupRow, RoleGroupSuggestion } from '../../api/types';
import { percent } from '../../lib/analytics';
import { plural } from '../../lib/format';
import { Bar, ChartCard, DataTable } from './Charts';
import styles from './Charts.module.css';

const NO_ROLE = '__no_role__';
const rowId = (row: RoleGroupRow) => row.key ?? NO_ROLE;
const rate = (part: number, whole: number) => (whole ? Math.round((part / whole) * 1000) / 10 : null);

type SortKey = 'label' | 'applied' | 'rate';
type Sort = { key: SortKey; descending: boolean };
const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'label', label: 'Role' },
  { key: 'applied', label: 'Applied', numeric: true },
  { key: 'rate', label: 'Response rate' },
];

function sortGroups(rows: RoleGroupRow[], { key, descending }: Sort): RoleGroupRow[] {
  const value = (row: RoleGroupRow) => (key === 'applied' ? row.applied : (row.response_rate ?? -1));
  return [...rows].sort((a, b) => {
    const order = key === 'label' ? a.label.localeCompare(b.label) : value(a) - value(b);
    return (descending ? -order : order) || b.applied - a.applied || a.label.localeCompare(b.label);
  });
}

/** Response rate per role group. A group is a core title ("Senior Nurse (m/w/d)" counts as Nurse); the user
 * can merge groups and see the exact titles in each. Groups below the minimum fold into "Other roles". */
export function RoleGroupsCard({ rows, minimum }: { rows: RoleGroupRow[]; minimum: number }) {
  const [sort, setSort] = useState<Sort>({ key: 'applied', descending: true });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [expandedSmall, setExpandedSmall] = useState<string | null>(null);
  const [otherOpen, setOtherOpen] = useState(false);
  const otherId = useId();
  const ai = useAIStatus();

  const large = sortGroups(rows.filter((row) => row.enough), sort);
  const small = sortGroups(rows.filter((row) => !row.enough), sort);
  const otherApplied = small.reduce((sum, row) => sum + row.applied, 0);
  const otherReplied = small.reduce((sum, row) => sum + row.replied, 0);
  const otherRate = rate(otherReplied, otherApplied);

  const sortBy = (key: SortKey) =>
    setSort((current) => (current.key === key ? { key, descending: !current.descending } : { key, descending: key !== 'label' }));
  const toggle = (setter: typeof setExpanded) => (row: RoleGroupRow) =>
    setter((current) => (current === rowId(row) ? null : rowId(row)));

  const chart = (
    <div className={styles.roleTable}>
      <div className={styles.roleHead} role="group" aria-label="Sort role groups">
        {COLUMNS.map((column) => {
          const active = sort.key === column.key;
          return (
            <button
              key={column.key}
              type="button"
              className={`${styles.sortButton} ${column.numeric ? styles.num : ''}`}
              aria-pressed={active}
              onClick={() => sortBy(column.key)}
            >
              {column.label}
              <span aria-hidden="true">{active ? (sort.descending ? ' ↓' : ' ↑') : ''}</span>
              {active && <span className="visually-hidden">{sort.descending ? ', highest first' : ', lowest first'}</span>}
            </button>
          );
        })}
      </div>
      <ul className={styles.roleRows}>
        {large.map((row) => (
          <GroupRow key={rowId(row)} row={row} open={expanded === rowId(row)} onToggle={() => toggle(setExpanded)(row)} />
        ))}
        {small.length > 0 && (
          <li className={styles.roleGroup}>
            <div className={styles.roleRow}>
              <button
                type="button"
                className={styles.roleToggle}
                aria-expanded={otherOpen}
                aria-controls={otherId}
                onClick={() => setOtherOpen((open) => !open)}
              >
                <span className={styles.chevron} aria-hidden="true">
                  {otherOpen ? '▾' : '▸'}
                </span>
                <span className={styles.roleName}>Other roles</span>
                <span className={styles.roleCount}>{plural(small.length, 'role')}</span>
              </button>
              <span className={`mono ${styles.num}`}>{otherApplied}</span>
              <Bar value={otherRate ?? 0} max={100} label={`Other roles: ${percent(otherRate)}`} />
              <span className={styles.value}>{percent(otherRate)}</span>
            </div>
            {otherOpen && (
              <ul id={otherId} className={styles.otherRows} aria-label="Other roles">
                {small.map((row) => (
                  <GroupRow
                    key={rowId(row)}
                    row={row}
                    open={expandedSmall === rowId(row)}
                    onToggle={() => toggle(setExpandedSmall)(row)}
                  />
                ))}
              </ul>
            )}
          </li>
        )}
      </ul>
      {small.length > 0 && (
        <p className={styles.roleNote}>
          Roles with fewer than {plural(minimum, 'application')} are grouped under Other roles.
        </p>
      )}
    </div>
  );

  const tableRows: (string | number)[][] = large.map((r) => [r.label, r.applied, r.replied, percent(r.response_rate)]);
  if (small.length) tableRows.push([`Other roles (${plural(small.length, 'role')})`, otherApplied, otherReplied, percent(otherRate)]);

  return (
    <ChartCard
      title="Response rate by role"
      subtitle="Role groups, most applications first"
      empty={rows.length === 0 ? 'No applications in this range.' : null}
      extra={ai.data?.configured && rows.length > 1 ? <Suggestions /> : null}
      chart={chart}
      table={<DataTable caption="Response rate by role" head={['Role', 'Applied', 'Replied', 'Response rate']} rows={tableRows} />}
    />
  );
}

function GroupRow({ row, open, onToggle }: { row: RoleGroupRow; open: boolean; onToggle: () => void }) {
  const panelId = useId();
  return (
    <li className={styles.roleGroup}>
      <div className={styles.roleRow}>
        <button
          type="button"
          className={styles.roleToggle}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
        >
          <span className={styles.chevron} aria-hidden="true">
            {open ? '▾' : '▸'}
          </span>
          <span className={row.key === null ? `${styles.roleName} muted` : styles.roleName}>{row.label}</span>
          {row.titles.length > 1 && <span className={styles.roleCount}>{plural(row.titles.length, 'title')}</span>}
        </button>
        <span className={`mono ${styles.num}`}>{row.applied}</span>
        <Bar value={row.response_rate ?? 0} max={100} label={`${row.label}: ${percent(row.response_rate)}`} />
        <span className={styles.value}>{percent(row.response_rate)}</span>
      </div>
      {open && (
        <div id={panelId} className={styles.rolePanel}>
          <ul className={styles.titleList} aria-label={`Titles in ${row.label}`}>
            {row.titles.map((title) => (
              <li key={title.title}>
                <span>{title.title}</span>
                <span className="mono">
                  {title.applied} · {percent(rate(title.replied, title.applied))}
                </span>
              </li>
            ))}
          </ul>
          {row.key === null ? (
            <p className={styles.roleHint}>No role was found in these emails. Use “Count as” on an application to place it in a group.</p>
          ) : (
            <GroupActions row={row} />
          )}
        </div>
      )}
    </li>
  );
}

function GroupActions({ row }: { row: RoleGroupRow }) {
  const groups = useRoleGroups();
  const merge = useMergeRoleGroups();
  const undo = useUndoRoleGroupMerge();
  const targets = (groups.data?.groups ?? []).filter((group) => group.key !== row.key);
  const error = merge.error ?? undo.error;

  return (
    <>
      {row.merged.length > 0 && (
        <ul className={styles.mergedList} aria-label={`Merged into ${row.label}`}>
          {row.merged.map((group) => (
            <li key={group.key}>
              <span>
                Includes <strong>{group.label}</strong>
              </span>
              <button
                type="button"
                className="link-button"
                disabled={undo.isPending}
                onClick={() => undo.mutate(group.key)}
              >
                Undo merge
              </button>
            </li>
          ))}
        </ul>
      )}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger className={`btn ${styles.smallButton}`} disabled={merge.isPending || targets.length === 0}>
          Merge into…
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content className={`overlay-menu ${styles.mergeMenu}`} align="start" sideOffset={4}>
            <DropdownMenu.Label className="overlay-label">Count {row.label} as</DropdownMenu.Label>
            {targets.map((group) => (
              <DropdownMenu.Item
                key={group.key}
                className="overlay-item"
                onSelect={() => row.key && merge.mutate({ source: row.key, target: group.key })}
              >
                <span>{group.label}</span>
                <span className="mono muted">{group.applied}</span>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {error && (
        <p className="error-text" role="alert">
          Not saved: {error.message}
        </p>
      )}
    </>
  );
}

function Suggestions() {
  const suggest = useSuggestRoleGroups();
  const merge = useMergeRoleGroups();
  const [done, setDone] = useState<Set<string>>(new Set());
  const keyOf = (s: RoleGroupSuggestion) => `${s.source}>${s.target}`;
  const pending = (suggest.data?.suggestions ?? []).filter((s) => !done.has(keyOf(s)));
  const decide = (s: RoleGroupSuggestion) => setDone((current) => new Set(current).add(keyOf(s)));

  return (
    <div className={styles.suggestions}>
      <button
        type="button"
        className={`btn ${styles.smallButton}`}
        disabled={suggest.isPending}
        onClick={() => {
          setDone(new Set());
          suggest.mutate();
        }}
      >
        {suggest.isPending ? 'Asking your AI…' : 'Suggest groups'}
      </button>
      {suggest.isError && (
        <p className="error-text" role="alert">
          No suggestions: {suggest.error.message}
        </p>
      )}
      {suggest.isSuccess &&
        (pending.length === 0 ? (
          <p className={styles.roleHint} role="status">
            {suggest.data.suggestions.length === 0 ? 'Your AI found no groups to merge.' : 'All suggestions handled.'}
          </p>
        ) : (
          <ul className={styles.suggestionList} aria-label="Suggested merges">
            {pending.map((s) => (
              <li key={keyOf(s)}>
                <p>
                  Merge <strong>{s.source_label}</strong> into <strong>{s.target_label}</strong>
                  {s.reason && <span className={styles.roleHint}> · {s.reason}</span>}
                </p>
                <div className={styles.suggestionButtons}>
                  <button
                    type="button"
                    className={`btn ${styles.smallButton}`}
                    disabled={merge.isPending}
                    onClick={() => merge.mutate({ source: s.source, target: s.target }, { onSuccess: () => decide(s) })}
                  >
                    Accept
                  </button>
                  <button type="button" className={`btn ${styles.smallButton}`} onClick={() => decide(s)}>
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ))}
      {merge.isError && (
        <p className="error-text" role="alert">
          Not merged: {merge.error.message}
        </p>
      )}
    </div>
  );
}
