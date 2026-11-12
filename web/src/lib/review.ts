import { NEEDS_REVIEW, REVIEW_STATUSES, type AIReviewResult, type Application, type ReviewStatus } from '../api/types';
import { isMissing } from './applications';
import { plural, toDate } from './format';

interface HistoryEvent {
  message_id?: string;
  date?: string;
  subject?: string;
}

function history(app: Application): HistoryEvent[] {
  const events = app.raw_metadata?.history;
  return Array.isArray(events) ? events.filter((e): e is HistoryEvent => typeof e === 'object' && e !== null) : [];
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function latestMessageId(app: Application): string | null {
  const ids = history(app)
    .map((event) => event.message_id)
    .filter((id): id is string => typeof id === 'string' && /^[0-9a-f]+$/i.test(id));
  return ids.at(-1) ?? null;
}

export interface EmailSummary {
  messageId: string | null;
  subject: string | null;
  sender: string | null;
  snippet: string | null;
  date: string | null;
}

export function emailSummary(app: Application): EmailSummary {
  const meta = app.raw_metadata ?? {};
  const last = history(app).at(-1);
  return {
    messageId: latestMessageId(app),
    subject: text(meta.subject) ?? text(last?.subject),
    sender: text(meta.sender),
    snippet: text(meta.snippet),
    date: text(last?.date) ?? app.applied_date,
  };
}

/** "Tidewater Recruiting" from "Tidewater Recruiting <careers@tidewater.example>". */
export function senderName(sender: string | null | undefined): string | null {
  if (!sender) return null;
  const name = sender.replace(/<[^>]*>/, '').replace(/^["'\s]+|["'\s]+$/g, '');
  if (name) return name;
  const address = sender.match(/<([^>]+)>/)?.[1] ?? sender;
  return address.trim() || null;
}

function activity(app: Application): number {
  return toDate(app.last_activity_at ?? app.applied_date)?.getTime() ?? 0;
}

export function reviewQueue(apps: Application[]): Application[] {
  return apps.filter((app) => app.status === NEEDS_REVIEW).sort((a, b) => activity(b) - activity(a));
}

/** The status the rules leaned towards, when they had one. */
export function suggestedStatus(app: Application): ReviewStatus | null {
  const result = app.raw_metadata?.classifier_result;
  const status = result && typeof result === 'object' ? (result as { status?: unknown }).status : null;
  return REVIEW_STATUSES.find((s) => s === status) ?? null;
}

export function knownValue(value: string | null | undefined): string {
  return isMissing(value) ? '' : (value ?? '');
}

export function aiReviewSummary(result: AIReviewResult): string {
  if (result.queued_in_batch > 0) {
    return `Sent ${plural(result.queued_in_batch, 'email')} to your AI as a batch. The answers come in with a later sync.`;
  }
  if (result.checked === 0) return 'Nothing your AI could check: the emails left need your own decision.';
  const parts = [`${result.updated} sorted out`];
  if (result.not_job > 0) parts.push(`${result.not_job} don’t look like job emails`);
  if (result.unchanged > 0) parts.push(`${result.unchanged} still unclear`);
  if (result.failed > 0) parts.push(`${result.failed} failed`);
  return `Checked ${plural(result.checked, 'email')}: ${parts.join(', ')}.`;
}
