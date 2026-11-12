import type { Application } from '../api/types';
import { heldText } from '../lib/applications';
import { relativeDay } from '../lib/format';

/** Last activity in words: a held interview with no news, a long wait for a reply, or a date. */
export function ActivityText({ application, now }: { application: Application; now?: Date }) {
  if (application.interview_held) return <span className="stale">{heldText(application)}</span>;
  if (application.no_reply_days != null) {
    return <span className="stale">No reply · {application.no_reply_days} days</span>;
  }
  return <>{relativeDay(application.last_activity_at, now)}</>;
}
