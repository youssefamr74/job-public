import { useId, useState, type ReactNode } from 'react';
import type { AnalyticsOverview, RateRow } from '../../api/types';
import { barWidth, dayLabel, percent } from '../../lib/analytics';
import styles from './Charts.module.css';

interface CardProps {
  title: string;
  subtitle: string;
  chart: ReactNode;
  table: ReactNode;
  empty?: string | null;
  /** Controls next to "Show as table". */
  actions?: ReactNode;
  /** Shown between the title and the chart. */
  extra?: ReactNode;
}

/** A titled chart with a "Show as table" switch, so every number can be read without the bars. */
export function ChartCard({ title, subtitle, chart, table, empty, actions, extra }: CardProps) {
  const [asTable, setAsTable] = useState(false);
  const titleId = useId();
  return (
    <section className={styles.card} aria-labelledby={titleId}>
      <div className={styles.cardHead}>
        <div>
          <h2 id={titleId} className={styles.cardTitle}>
            {title}
          </h2>
          <p className={styles.cardSubtitle}>{subtitle}</p>
        </div>
        <div className={styles.cardActions}>
          {actions}
          {!empty && (
            <button
              type="button"
              className={styles.tableToggle}
              aria-pressed={asTable}
              onClick={() => setAsTable((value) => !value)}
            >
              {asTable ? 'Show as chart' : 'Show as table'}
            </button>
          )}
        </div>
      </div>
      {extra}
      {empty ? <p className={styles.empty}>{empty}</p> : asTable ? table : chart}
    </section>
  );
}

export function DataTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <table className={styles.table}>
      <caption className="visually-hidden">{caption}</caption>
      <thead>
        <tr>
          {head.map((cell, i) => (
            <th key={cell} scope="col" className={i > 0 ? styles.num : undefined}>
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={String(row[0])}>
            {row.map((cell, i) =>
              i === 0 ? (
                <th key={i} scope="row">
                  {cell}
                </th>
              ) : (
                <td key={i} className={styles.num}>
                  {cell}
                </td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function WeeklyCard({ weeks, subtitle }: { weeks: AnalyticsOverview['per_week']; subtitle: string }) {
  const max = Math.max(...weeks.map((w) => w.count), 0);
  const peak = weeks.findIndex((w) => w.count === max && max > 0);
  const latest = weeks.length - 1;
  const sparse = weeks.length > 8;
  const chart = (
    <div className={styles.columns} role="img" aria-label={`Applications per week, highest ${max}.`}>
      {weeks.map((week, index) => {
        const label = dayLabel(week.week_start);
        const pinned = index === peak || index === latest;
        return (
          <div key={week.week_start} className={styles.column} title={`Week of ${label}: ${week.count}`}>
            <div className={styles.columnTrack}>
              <span className={styles.columnValue} data-pinned={pinned || undefined}>
                {week.count}
              </span>
              <div className={styles.columnBar} style={{ height: `${max ? (week.count / max) * 100 : 0}%` }} />
            </div>
            <span className={styles.columnLabel} data-skip={(sparse && (latest - index) % 2 === 1) || undefined}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
  return (
    <ChartCard
      title="Applications per week"
      subtitle={subtitle}
      empty={max === 0 ? 'No applications in this range.' : null}
      chart={chart}
      table={
      <DataTable
        caption="Applications per week"
        head={['Week of', 'Applications']}
        rows={weeks.map((w) => [dayLabel(w.week_start), w.count])}
      />
      }
    />
  );
}

export function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div className={styles.track} title={label}>
      <div className={styles.fill} style={{ width: `${barWidth(value, max)}%` }} />
    </div>
  );
}

export function FunnelCard({ steps }: { steps: AnalyticsOverview['funnel'] }) {
  const max = steps[0]?.count ?? 0;
  const chart = (
    <ul className={styles.rows}>
      {steps.map((step, index) => (
        <li key={step.step} className={styles.row}>
          <span>{step.step}</span>
          <Bar value={step.count} max={max} label={`${step.step}: ${step.count}`} />
          <span className={styles.value}>
            {step.count}
            {index > 0 && <span className={styles.rate}>{percent(step.rate)}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <ChartCard
      title="How far applications got"
      subtitle="Each step counts applications that reached it"
      empty={max === 0 ? 'No applications in this range.' : null}
      chart={chart}
      table={
      <DataTable
        caption="How far applications got"
        head={['Step', 'Applications', 'Share']}
        rows={steps.map((s) => [s.step, s.count, percent(s.rate)])}
      />
      }
    />
  );
}

export function WeekdayCard({ rows }: { rows: RateRow[] }) {
  const chart = (
    <ul className={`${styles.rows} ${styles.weekdays}`}>
      {rows.map((row) => (
        <li key={row.label} className={styles.row}>
          <span className="mono">{row.label}</span>
          <Bar
            value={row.enough ? (row.response_rate ?? 0) : 0}
            max={100}
            label={row.enough ? `${row.label}: ${percent(row.response_rate)}` : `${row.label}: ${row.applied} applications`}
          />
          <span className={`${styles.value} ${row.enough ? '' : styles.tooFew}`}>
            {row.enough ? percent(row.response_rate) : 'too few'}
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <ChartCard
      title="Response rate by day you applied"
      subtitle="Days with fewer than 10 applications are left out"
      chart={chart}
      table={
      <DataTable
        caption="Response rate by day you applied"
        head={['Day', 'Applied', 'Response rate']}
        rows={rows.map((r) => [r.label, r.applied, r.enough ? percent(r.response_rate) : 'too few'])}
      />
      }
    />
  );
}
