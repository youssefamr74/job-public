import { useSearchParams } from 'react-router-dom';
import { useAnalytics, useWeeklyReview } from '../../api/queries';
import type { AnalyticsOverview, AnalyticsRange, WeeklyReview } from '../../api/types';
import { ErrorState, Loading } from '../../components/States';
import { RANGES, dayLabel, percent, perWeek, replyTime } from '../../lib/analytics';
import { plural } from '../../lib/format';
import { FunnelCard, WeekdayCard, WeeklyCard } from './Charts';
import { RoleGroupsCard } from './RoleGroupsCard';
import styles from './AnalyticsPage.module.css';

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className={styles.tile}>
      <dt className={styles.tileLabel}>{label}</dt>
      <dd className={styles.tileValue}>{value}</dd>
      <dd className={styles.tileNote}>{note}</dd>
    </div>
  );
}

function Headline({ data }: { data: AnalyticsOverview['headline'] }) {
  return (
    <dl className={styles.tiles}>
      <Tile label="Applications" value={String(data.applications)} note={perWeek(data.per_week)} />
      <Tile
        label="Response rate"
        value={percent(data.response_rate)}
        note={data.applications ? `${data.replied} of ${data.applications} got any reply` : 'No applications yet'}
      />
      <Tile
        label="Typical time to reply"
        value={replyTime(data.median_days_to_reply)}
        note={data.median_days_to_reply == null ? 'No replies yet' : 'median, first reply'}
      />
      <Tile
        label="Daily goal"
        value={`${data.goal_days_met} of ${data.goal_days}`}
        note={`days met this week · goal ${data.daily_goal}`}
      />
    </dl>
  );
}

function ThisWeek({ review }: { review: WeeklyReview }) {
  const written = review.ai_configured && review.highlight;
  return (
    <section className={styles.week} aria-labelledby="this-week">
      <div>
        <h2 id="this-week" className={styles.weekTitle}>
          This week
        </h2>
        <p className={styles.weekSubtitle}>
          {dayLabel(review.week_start)} to {dayLabel(review.week_end)}
          {written && ' · written by your AI'}
        </p>
        <dl className={styles.weekNumbers}>
          <div>
            <dt>Applied</dt>
            <dd>{review.applications_this_week}</dd>
          </div>
          <div>
            <dt>Replies</dt>
            <dd>{review.responses_this_week}</dd>
          </div>
          <div>
            <dt>Interviews booked</dt>
            <dd>{review.interviews_this_week}</dd>
          </div>
        </dl>
      </div>
      {written && (
        <div className={styles.weekText}>
          <p>
            <strong>Went well.</strong> {review.highlight}
          </p>
          {review.concern && (
            <p>
              <strong>Worth a look.</strong> {review.concern}
            </p>
          )}
          {review.focus_items && review.focus_items.length > 0 && (
            <>
              <h3 className={styles.nextWeek}>Next week</h3>
              <ol>
                {review.focus_items.map((item) => (
                  <li key={item}>{item.replace(/^\s*(?:\d+[.)]|[-*•])\s*/, '')}</li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </section>
  );
}

export function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('range');
  const range: AnalyticsRange = RANGES.some((r) => r.value === requested) ? (requested as AnalyticsRange) : '60';
  const overview = useAnalytics(range);
  const review = useWeeklyReview();

  const setRange = (value: AnalyticsRange) =>
    setParams(value === '60' ? {} : { range: value }, { replace: true });

  const data = overview.data;
  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>Analytics</h1>
        <div className={styles.toggle} role="group" aria-label="Date range">
          {RANGES.map((r) => (
            <button key={r.value} type="button" aria-pressed={range === r.value} onClick={() => setRange(r.value)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {overview.isPending ? (
        <Loading>Loading analytics…</Loading>
      ) : overview.isError ? (
        <ErrorState
          message={`Couldn’t load analytics. ${overview.error.message}`}
          onRetry={() => void overview.refetch()}
        />
      ) : data ? (
        <>
          <Headline data={data.headline} />
          <div className={styles.grid}>
            <WeeklyCard
              weeks={data.per_week}
              subtitle={range === 'all' ? `All time, ${plural(data.per_week.length, 'week')}` : `Last ${plural(data.per_week.length, 'week')}`}
            />
            <FunnelCard steps={data.funnel} />
            <RoleGroupsCard rows={data.by_role} minimum={data.role_min_applications} />
            <WeekdayCard rows={data.by_weekday} />
          </div>
        </>
      ) : null}
      {review.data && <ThisWeek review={review.data} />}
    </div>
  );
}
