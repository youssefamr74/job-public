"""Gmail sync: fetch, classify, match to existing applications, apply status rules, save in one batch."""

import asyncio
import html
import logging
import uuid as uuid_lib
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from applications.schemas import USER_METADATA_KEYS
from applications.models import Application, EmailCache
from applications.role_groups import role_group
from classifier.role_quality import role_or_unknown
from applications.review import ignored_ids_and_threads
from applications.routing import ACCOUNT, CLASSIFIED, OPPORTUNITY, OPPORTUNITY_NOTE, route_email
from sync_runs.models import (
    CANCELLED,
    ERR_AI_UNAVAILABLE,
    ERR_AUTH_FAILED,
    ERR_INTERNAL,
    ERR_NEEDS_RELINK,
    ERR_NOT_CONNECTED,
    ERR_UNREACHABLE,
    FAILED,
    STAGE_CLASSIFYING,
    STAGE_FETCHING,
    STAGE_FILTERING,
    STAGE_SAVING,
    SUCCEEDED,
    TRIGGER_MANUAL,
    WAITING_FOR_AI,
)
from sync_runs.schemas import SyncOptions
from sync_runs.service import RunTracker
from applications.service import is_valid_transition, parse_email_date, stored_status
from auth.models import User
from classifier.batch_service import AiPending, NotJob, classify_emails_batch
from classifier.heuristics import filter_reason
from classifier.normalization import is_platform_name, make_fingerprint
from classifier.text import clean_text
from companion.service import generate_moment
from diagnostics.models import (
    REASON_FILTERED_OUT,
    REASON_JOB_ALERT,
    REASON_NO_COMPANY_OR_ROLE,
    REASON_ACCOUNT,
    REASON_NOT_JOB,
    REASON_SOCIAL,
    REASON_SURVEY,
)
from diagnostics.service import forget_dropped, record_dropped
from constants.app_config import FULL_SYNC_DAYS, MAX_RESULTS
from constants.job_statuses import STATUS_PRIORITY, TERMINAL_STATUSES, MOMENT_TYPE_BY_STATUS
from mail.base import Cursor, MailAuthError, MailError
from mail.fetch import fetch_new_emails
from mail.models import MailAccount
from mail.service import mark_sync_ok, open_mail_source, record_mail_failure, save_cursor
from goals.service import save_goal_record, update_streak
from ai.service import ai_configured
from opportunities.models import Opportunity
from opportunities.service import dismissed_threads, mark_converted, open_all
from utils.timeutil import local_date, utc_now

logger = logging.getLogger(__name__)

FILTER_COUNTERS = {
    REASON_FILTERED_OUT: "blocked_by_filter",
    REASON_JOB_ALERT: "job_alerts",
    REASON_SOCIAL: "social",
    REASON_SURVEY: "surveys",
}
# With a clear status the email is saved even when company and role are unknown;
# its subject stays visible and later emails in the thread attach to it.
SAVE_WITHOUT_COMPANY = {"Applied", "Rejected", "Assessment"}
SAVE_WITHOUT_COMPANY_CONFIDENCE = 0.8
# An email with one of these statuses from the opportunity's company shows the user is in the process.
APPLIED_STATUSES = {"Applied", "Assessment", "Interview"}


class _InMemoryApp:
    def __init__(self, status, raw_metadata, interview_date, thread_id, job_id, company=None, role=None, user_id=None,
                 app_id=None):
        self.id = app_id
        self.action_needed = False
        self.status = status
        self.raw_metadata = raw_metadata
        self.interview_date = interview_date
        self.email_thread_id = thread_id
        self.job_id = job_id
        self.company = company
        self.role = role
        self.manually_modified = False
        self.user_id = user_id
        self.applied_date = datetime.now(timezone.utc)


async def _prefetch_existing(
    user: User,
    db: AsyncSession,
    emails: list[dict],
) -> tuple[dict, dict, dict, dict, set]:
    all_apps_result = await db.execute(
        select(Application).where(Application.user_id == user.id)
    )
    existing_by_thread:      dict[str, Application] = {}
    existing_by_job_id:      dict[str, Application] = {}
    existing_by_fingerprint: dict[str, Application] = {}
    existing_by_company:     dict[str, list] = {}

    for app in all_apps_result.scalars().all():
        if app.email_thread_id:
            existing_by_thread[app.email_thread_id] = app
        if app.job_id:
            existing_by_job_id[app.job_id] = app
        if app.application_fingerprint:
            existing_by_fingerprint[app.application_fingerprint] = app
        key = app.company.lower() if app.company else ""
        if key and key != "unknown" and not is_platform_name(app.company):
            existing_by_company.setdefault(key, []).append(app)

    email_ids = [e.get("id") for e in emails if e.get("id")]
    cached_ids: set[str] = set()
    if email_ids:
        cache_result = await db.execute(
            select(EmailCache.gmail_message_id).where(
                EmailCache.user_id == user.id,
                EmailCache.gmail_message_id.in_(email_ids),
            )
        )
        cached_ids = {row[0] for row in cache_result.fetchall()}

    logger.info(
        f"Prefetch | threads={len(existing_by_thread)} "
        f"job_ids={len(existing_by_job_id)} "
        f"fingerprints={len(existing_by_fingerprint)} "
        f"cached={len(cached_ids)}"
    )

    return existing_by_thread, existing_by_job_id, existing_by_fingerprint, existing_by_company, cached_ids


def _dropped(email: dict, reason: str, detail: str = "") -> dict:
    return {
        "gmail_message_id": email.get("id"),
        "subject": (email.get("subject") or "")[:500],
        "sender": (email.get("sender") or "")[:500],
        "snippet": clean_text(email.get("body") or "")[:200],
        "reason": reason,
        "detail": detail,
    }


def _prefilter_emails(
    emails: list[dict],
    cached_ids: set[str],
    stats: dict,
    dropped: list[dict],
    route=None,
    routed: Optional[dict] = None,
) -> list[dict]:
    """Drops what is certainly not an application. With a router, calendar invites, account mail and
    outreach are kept (and recorded in `routed`) even when the plain filter would call them noise."""
    emails_to_classify = []
    for email in emails:
        email_id = email.get("id", "")
        if email_id and email_id in cached_ids:
            stats["already_processed"] += 1
            continue
        sender  = email.get("sender") or ""
        subject = email.get("subject") or ""
        body    = (email.get("body") or "")[:1000]
        decision = filter_reason(sender, subject, body)
        # Alerts, social mail and surveys are never routed; only the generic "no job signal" filters are.
        if route is not None and (decision is None or decision[0] == REASON_FILTERED_OUT):
            try:
                routing = route(email)
            except Exception:
                logger.warning("Routing failed; classifying normally", exc_info=True)
                routing = None
            if routing is not None:
                routed[email_id] = routing
                emails_to_classify.append(email)
                continue
        if decision:
            reason, detail = decision
            stats[FILTER_COUNTERS[reason]] += 1
            dropped.append(_dropped(email, reason, detail))
            logger.info(f"{reason.upper()} ({detail})")
            continue
        emails_to_classify.append(email)
    return emails_to_classify


def _find_existing(
    thread_id: Optional[str],
    job_id: Optional[str],
    fingerprint: Optional[str],
    company: str,
    role: str,
    effective_status: str,
    existing_by_thread: dict,
    existing_by_job_id: dict,
    existing_by_fingerprint: dict,
    existing_by_company: dict,
    stats: dict,
) -> Optional[Application]:
    if thread_id:
        existing = existing_by_thread.get(thread_id)
        if existing:
            stats["matched_by_thread"] += 1
            return existing

    if job_id:
        existing = existing_by_job_id.get(job_id)
        if existing:
            stats["matched_by_job_id"] += 1
            return existing

    if fingerprint and role != "Unknown":
        existing = existing_by_fingerprint.get(fingerprint)
        if existing:
            stats["matched_by_fingerprint"] += 1
            return existing

    # A platform name like "Workable" stands for many employers, so it never matches by company.
    if company != "Unknown" and not is_platform_name(company) and effective_status != "Applied":
        matches = existing_by_company.get(company.lower(), [])
        if matches:
            now = datetime.now(timezone.utc)
            window = timedelta(days=90)

            def get_date(m):
                d = m.applied_date if not isinstance(m, _InMemoryApp) else m.applied_date
                if d and d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d

            def get_status(m):
                if isinstance(m, _InMemoryApp):
                    return m.status
                return m.status

            recent = [
                m for m in matches
                if get_date(m) and (now - get_date(m)) <= window
            ]

            if recent:
                best = max(recent, key=lambda a: STATUS_PRIORITY.get(get_status(a), -1))
                stats["matched_by_company"] += 1
                return best

    return None


def _build_metadata(
    subject: str,
    sender: str,
    body: str,
    result: dict,
    effective_status: str,
    confidence: float,
    email_date: datetime = None,
    message_id: Optional[str] = None,
) -> tuple[dict, dict]:
    new_event = {
        "message_id": message_id,
        "date":       (email_date or utc_now()).isoformat(),
        "status":     effective_status,
        "confidence": confidence,
        "reason":     result.get("reason", ""),
        "subject":    subject,
    }
    raw_metadata = {
        "subject":    subject,
        "sender":     sender,
        "snippet":    body[:300],
        "classifier_result": {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in result.items()
        },
        "confidence":    confidence,
        "source":        result.get("source"),
        "classified_at": utc_now().isoformat(),
    }
    return new_event, raw_metadata


def _apply_to_existing(
    idx: int,
    existing,
    effective_status: str,
    confidence: float,
    interview_date,
    raw_metadata: dict,
    new_event: dict,
    email_id: str,
    company: str,
    role: str,
    fingerprint: Optional[str],
    thread_id: Optional[str],
    job_id: Optional[str],
    new_cache_entries: list,
    existing_by_thread: dict,
    existing_by_job_id: dict,
    existing_by_fingerprint: dict,
    stats: dict,
    new_apps: list,
) -> bool:
    """Returns True when the caller should skip to the next email."""
    existing_history = (existing.raw_metadata or {}).get("history", [])
    existing_history.append(new_event)
    raw_metadata["history"] = existing_history
    for key in USER_METADATA_KEYS:
        if (existing.raw_metadata or {}).get(key):
            raw_metadata[key] = existing.raw_metadata[key]

    # Offer and Rejected are final unless the classifier is very sure.
    if existing.status in TERMINAL_STATUSES and not existing.manually_modified:
        if confidence < 0.95:
            existing.raw_metadata = raw_metadata
            if interview_date and not existing.interview_date:
                existing.interview_date = interview_date
            stats["terminal_protected"] += 1
            logger.info(f"[{idx}] TERMINAL PROTECTED | stays {existing.status}")
            if email_id:
                new_cache_entries.append({"gmail_message_id": email_id, "user_id": existing.user_id, "processed": True})
            return True

    # The user's own edits always win over sync.
    if existing.manually_modified:
        existing.raw_metadata = raw_metadata
        if interview_date and not existing.interview_date:
            existing.interview_date = interview_date
        stats["manual_protected"] += 1
        logger.info(f"[{idx}] MANUAL PROTECTED")
        if email_id:
            new_cache_entries.append({"gmail_message_id": email_id, "user_id": existing.user_id, "processed": True})
        return True

    if effective_status != existing.status:
        if is_valid_transition(existing.status, effective_status):
            logger.info(f"[{idx}] TRANSITION {existing.status}→{effective_status}")
            existing.status = effective_status
            existing.action_needed = False
            if isinstance(existing, _InMemoryApp):
                for app in new_apps:
                    if (app.get("company") == existing.company and
                        app.get("role") == existing.role and
                        app.get("user_id") == existing.user_id):
                        app["status"] = effective_status
                        app["raw_metadata"] = raw_metadata
                        break
    else:
        stats["transition_blocked"] += 1
        logger.info(f"[{idx}] TRANSITION BLOCKED {existing.status}→{effective_status}")
    existing.raw_metadata = raw_metadata
    if interview_date and not existing.interview_date:
        existing.interview_date = interview_date
    stats["updated_existing"] += 1

    # Later emails in this batch should match this application too.
    if fingerprint:
        existing_by_fingerprint[fingerprint] = existing
    if thread_id:
        existing_by_thread[thread_id] = existing
    if job_id:
        existing_by_job_id[job_id] = existing

    return False


def _create_new(
    user: User,
    company: str,
    role: str,
    effective_status: str,
    applied_date,
    interview_date,
    job_id: Optional[str],
    location: Optional[str],
    fingerprint: Optional[str],
    thread_id: Optional[str],
    raw_metadata: dict,
    new_event: dict,
    new_apps: list,
    existing_by_thread: dict,
    existing_by_job_id: dict,
    existing_by_fingerprint: dict,
    existing_by_company: dict,
    stats: dict,
    action_needed: bool = False,
) -> None:
    raw_metadata["history"] = [new_event]
    app_id = uuid_lib.uuid4()
    new_apps.append({
        "id":                      app_id,
        "user_id":                 user.id,
        "company":                 company,
        "role":                    role,
        "role_group":              role_group(role, company),
        "status":                  effective_status,
        "applied_date":            applied_date,
        "interview_date":          interview_date,
        "source":                  "gmail",
        "notes":                   None,
        "raw_metadata":            raw_metadata,
        "manually_modified":       False,
        "email_thread_id":         thread_id,
        "job_id":                  job_id,
        "location":                location,
        "application_fingerprint": fingerprint,
        "action_needed":           action_needed,
    })
    stats["saved_new"] += 1

    placeholder = _InMemoryApp(
        effective_status, raw_metadata, interview_date,
        thread_id, job_id, company=company, role=role, user_id=user.id, app_id=app_id
    )
    placeholder.action_needed = action_needed
    if fingerprint:
        existing_by_fingerprint[fingerprint] = placeholder
    if thread_id:
        existing_by_thread[thread_id] = placeholder
    if job_id:
        existing_by_job_id[job_id] = placeholder
    if company != "Unknown" and not is_platform_name(company):
        existing_by_company.setdefault(company.lower(), []).append(placeholder)


def _update_opportunity(opportunity, new_opportunities: list, route, subject: str, sender: str, when: datetime) -> None:
    """A later email in the same thread: keep one row per thread, with the latest details."""
    changes = {"subject": subject[:500], "sender": sender[:500], "date": when}
    if route.company and not opportunity.company:
        changes["company"] = route.company
    if route.role and not opportunity.role:
        changes["role"] = route.role
    for key, value in changes.items():
        setattr(opportunity, key, value)
    for row in new_opportunities:
        if row["id"] == opportunity.id:
            row.update(changes)


def _attach_note(app, new_apps: list, message_id: str, when: datetime, subject: str, reason: str) -> None:
    """Record an email on an application without touching its status."""
    event = {"message_id": message_id, "date": when.isoformat(), "status": app.status,
             "confidence": 1.0, "reason": reason, "subject": subject}
    metadata = dict(app.raw_metadata or {})
    metadata["history"] = [*metadata.get("history", []), event]
    app.raw_metadata = metadata
    if isinstance(app, _InMemoryApp):
        for row in new_apps:
            if row["id"] == app.id:
                row["raw_metadata"] = metadata


def _flag_action_needed(app, new_apps: list) -> None:
    app.action_needed = True
    if isinstance(app, _InMemoryApp):
        for row in new_apps:
            if row["id"] == app.id:
                row["action_needed"] = True


async def _batch_save(
    db: AsyncSession,
    new_apps: list[dict],
    new_cache_entries: list[dict],
    new_opportunities: Optional[list[dict]] = None,
) -> None:
    if new_apps:
        await db.execute(
            sqlite_insert(Application)
            .values(new_apps)
            .on_conflict_do_nothing(index_elements=["user_id", "application_fingerprint"])
        )
    if new_opportunities:
        await db.execute(
            sqlite_insert(Opportunity)
            .values(new_opportunities)
            .on_conflict_do_nothing(index_elements=["user_id", "message_id"])
        )
    if new_cache_entries:
        await db.execute(
            sqlite_insert(EmailCache)
            .values(new_cache_entries)
            .on_conflict_do_nothing(index_elements=["user_id", "gmail_message_id"])
        )
    await db.commit()
    logger.info("Batch commit successful")


async def _save_cursor(db: AsyncSession, account: MailAccount, cursor: Cursor) -> None:
    try:
        await save_cursor(db, account, cursor)
        logger.info(f"Saved mail cursor {cursor}")
    except Exception:
        await db.rollback()
        logger.warning("Failed to save the mail cursor", exc_info=True)


def _log_stats(stats: dict, ai_used: bool) -> None:
    classifier = "rules and AI" if ai_used else "rules only, no AI"
    ai_part = (
        f", {stats['classified_by_ai']} by AI, {stats['ai_failed']} AI failures kept the rules result, "
        f"{stats['waiting_for_ai']} waiting for an AI batch"
    ) if ai_used else ""
    logger.info(
        "=== SYNC COMPLETE === "
        f"fetched {stats['fetched']} ({stats['fetch_failed']} failed to fetch) "
        f"→ {stats['already_processed']} already processed, {stats['job_alerts']} job alerts, "
        f"{stats['social']} social, {stats['surveys']} surveys, {stats['blocked_by_filter']} filtered out "
        f"→ {stats['classified']} classified ({classifier}{ai_part}) "
        f"→ {stats['not_job']} not job-related, {stats['no_company_or_role']} without company or role "
        f"→ {stats['kept']} kept ({stats['kept_without_company']} without company or role): "
        f"{stats['saved_new']} new, {stats['updated_existing']} updated, {stats['needs_review']} need review"
    )
    logger.info(
        "Matching | " + ", ".join(
            f"{key}={stats[key]}" for key in (
                "matched_by_thread", "matched_by_job_id", "matched_by_fingerprint", "matched_by_company",
                "terminal_protected", "manual_protected", "transition_blocked",
            )
        )
    )


def _build_sync_moment(sync_events: list[dict]) -> dict | None:
    """Pick the most important status change of the sync: offer > interview > assessment > rejection."""
    if not sync_events:
        return None

    by_status = {}
    for e in sync_events:
        by_status.setdefault(e["status"], []).append(e)

    offers      = by_status.get("Offer", [])
    interviews  = by_status.get("Interview", [])
    assessments = by_status.get("Assessment", [])
    rejections  = by_status.get("Rejected", [])

    if offers:
        company = offers[0]["company"]
        return {
            "type": "offer",
            "title": f"You got an offer{f' from {company}' if company else ''}. 🎉",
            "body": "That's what all the work was for. Take a moment.",
            "count": len(offers),
        }

    if interviews:
        if len(interviews) == 1:
            company = interviews[0]["company"]
            return {
                "type": "interview",
                "title": f"Interview invite{f' from {company}' if company else ''}.",
                "body": "That's a real opportunity. Want to start preparing?",
                "count": 1,
            }
        return {
            "type": "interview",
            "title": f"{len(interviews)} interview invites came in.",
            "body": "Multiple opportunities at once — let's get you ready.",
            "count": len(interviews),
        }

    if assessments:
        if len(assessments) == 1:
            company = assessments[0]["company"]
            return {
                "type": "assessment",
                "title": f"Assessment from{f' {company}' if company else ' a company'}.",
                "body": "They want to see what you can do. That's progress.",
                "count": 1,
            }
        return {
            "type": "assessment",
            "title": f"{len(assessments)} assessments received.",
            "body": "Multiple companies want to test you. Focus on the strongest match.",
            "count": len(assessments),
        }

    if rejections:
        if len(rejections) == 1:
            company = rejections[0]["company"]
            return {
                "type": "rejection",
                "title": f"{'They' if not company else company} passed this time.",
                "body": "That stings a little. But you're still in the game.",
                "count": 1,
            }
        return {
            "type": "rejection",
            "title": f"{len(rejections)} rejections came in.",
            "body": "That's a rough batch. You still have active opportunities — keep the rhythm.",
            "count": len(rejections),
        }

    return None


def _build_summary(stats: dict, sync_events: list[dict]) -> dict:
    return {
        "new_applications":  stats.get("saved_new", 0),
        "updated":           stats.get("updated_existing", 0),
        "new_rejections":    sum(1 for e in sync_events if e["status"] == "Rejected"),
        "new_interviews":    sum(1 for e in sync_events if e["status"] == "Interview"),
        "needs_review":      stats.get("needs_review", 0),
        "new_opportunities": stats.get("opportunities", 0),
        "sync_moment":       _build_sync_moment(sync_events),
    }


async def sync_applications(
    user: User, db: AsyncSession, run_id: Optional[uuid_lib.UUID] = None,
    trigger: str = TRIGGER_MANUAL, options: Optional[SyncOptions] = None,
) -> dict:
    tracker = await RunTracker.begin(db, user, trigger, run_id)
    if tracker is None:
        return {"synced": 0, "message": "Sync already in progress", "error": False}
    try:
        return await _run_sync(user, db, tracker, options)
    except Exception:
        await db.rollback()
        await tracker.finish(FAILED, error_code=ERR_INTERNAL)
        raise


async def _run_sync(user: User, db: AsyncSession, tracker: RunTracker, options: Optional[SyncOptions]) -> dict:
    try:
        connection = await open_mail_source(db, user)
    except MailError as exc:
        await tracker.finish(FAILED, error_code=ERR_NEEDS_RELINK if isinstance(exc, MailAuthError) else ERR_UNREACHABLE)
        return {"synced": 0, "message": exc.message, "error": True}
    if connection is None:
        await tracker.finish(FAILED, error_code=ERR_NOT_CONNECTED)
        return {"synced": 0, "message": "No mail account connected", "error": True}
    account, source, cursor = connection.account, connection.source, connection.cursor
    if cursor:
        logger.info(f"=== SYNC START === (incremental from {cursor})")
    else:
        logger.info(f"=== SYNC START === (last {FULL_SYNC_DAYS} days)")

    since_date = date.today() - timedelta(days=FULL_SYNC_DAYS)
    max_messages = MAX_RESULTS
    if not cursor and options is not None:
        since_date = options.since_date or since_date
        max_messages = options.max_messages or max_messages

    await tracker.stage(STAGE_FETCHING)
    try:
        fetched = await fetch_new_emails(
            source, cursor, since_date, max_messages,
            on_progress=tracker.progress, should_stop=lambda: tracker.cancelled,
        )
    except MailError as exc:
        logger.error(f"Mail fetch failed: {exc.code}")
        await record_mail_failure(db, account, exc)
        await tracker.finish(FAILED, error_code=ERR_AUTH_FAILED if isinstance(exc, MailAuthError) else ERR_UNREACHABLE)
        return {"synced": 0, "message": exc.message, "error": True}
    finally:
        await source.close()
    emails = fetched.emails
    logger.info(f"Fetched {len(emails)} emails, {fetched.failed} failed")

    if fetched.stopped:
        await tracker.finish(CANCELLED, funnel={"fetched": len(emails)}, summary=_build_summary({}, []))
        return {"synced": 0, "message": "Sync cancelled", "error": False, "run_id": str(tracker.run_id)}

    if not emails:
        if fetched.cursor:
            await _save_cursor(db, account, fetched.cursor)
        await mark_sync_ok(db, user, account)
        await tracker.finish(SUCCEEDED, funnel={"fetched": 0}, summary=_build_summary({}, []))
        msg = "No new emails since last sync" if cursor else "No emails found"
        return {"synced": 0, "skipped": 0, "message": msg, "error": False, "run_id": str(tracker.run_id)}

    await tracker.stage(STAGE_FILTERING, total=len(emails))

    (
        existing_by_thread,
        existing_by_job_id,
        existing_by_fingerprint,
        existing_by_company,
        cached_ids,
    ) = await _prefetch_existing(user, db, emails)

    ai_used = ai_configured()
    stats = {
        "fetched":                len(emails),
        "fetch_failed":           fetched.failed,
        "already_processed":      0,
        "ignored_by_you":         0,
        "blocked_by_filter":      0,
        "job_alerts":             0,
        "social":                 0,
        "surveys":                0,
        "account_attached":       0,
        "account_filtered":       0,
        "opportunities":          0,
        "opportunities_converted": 0,
        "classified":             0,
        "classified_by_ai":       0,
        "ai_failed":              0,
        "waiting_for_ai":   0,
        "not_job":                0,
        "no_company_or_role":     0,
        "kept":                   0,
        "kept_without_company":   0,
        "needs_review":           0,
        "saved_new":              0,
        "updated_existing":       0,
        "terminal_protected":     0,
        "manual_protected":       0,
        "transition_blocked":     0,
        "matched_by_thread":      0,
        "matched_by_job_id":      0,
        "matched_by_fingerprint": 0,
        "matched_by_company":     0,
    }
    dropped: list[dict] = []

    new_apps:          list[dict] = []
    new_cache_entries: list[dict] = []
    affected_dates:    set[date]  = set()
    sync_events:       list[dict] = []
    moment_triggers:   list[dict] = []

    new_opportunities: list[dict] = []
    conversions:       list[tuple] = []
    open_list = await open_all(db, user)
    open_opps = {o.thread_id: o for o in open_list if o.thread_id}
    open_by_company = {o.company.lower(): o for o in open_list if o.company and o.company != "Unknown"}
    dismissed = await dismissed_threads(db, user)

    ignored_ids, ignored_threads = await ignored_ids_and_threads(db, user)
    candidates = []
    for email in emails:
        if email.get("id") in ignored_ids or (email.get("thread_id") and email.get("thread_id") in ignored_threads):
            stats["ignored_by_you"] += 1
            continue
        candidates.append(email)

    routed: dict = {}
    emails_to_classify = _prefilter_emails(
        candidates, cached_ids, stats, dropped,
        route=lambda e: route_email(e, existing_by_thread, existing_by_company, open_opps), routed=routed,
    )
    to_classify = [e for e in emails_to_classify if e.get("id", "") not in routed]

    await tracker.stage(STAGE_CLASSIFYING, total=len(to_classify))
    classification_results = await classify_emails_batch(
        to_classify,
        existing_by_thread,
        db=db,
        user=user,
        on_progress=tracker.progress,
    )
    for message_id, route in routed.items():
        if route.kind == CLASSIFIED:
            classification_results[message_id] = route.result
    outcomes = list(classification_results.values())
    stats["classified"] = len(emails_to_classify)
    stats["classified_by_ai"] = sum(
        1 for v in outcomes
        if (isinstance(v, dict) and v.get("source") == "ai") or (isinstance(v, NotJob) and v.by == "ai")
    )
    stats["ai_failed"] = sum(1 for v in outcomes if isinstance(v, dict) and v.get("ai_error"))
    held = {message_id for message_id, v in classification_results.items() if isinstance(v, AiPending)}
    stats["waiting_for_ai"] = len(held)
    await tracker.stage(STAGE_SAVING, total=len(emails_to_classify))
    unprocessed: set[str] = set()
    for idx, email in enumerate(emails_to_classify, start=1):
        if tracker.cancelled:
            unprocessed = {e.get("id", "") for e in emails_to_classify[idx - 1:]}
            break
        try:
            email_id  = email.get("id", "")
            thread_id = email.get("thread_id")
            subject   = clean_text(html.unescape(email.get("subject") or ""))
            sender    = email.get("sender") or ""
            body      = clean_text(email.get("body") or "")[:1000]

            route = routed.get(email_id)
            if route is not None and route.kind != CLASSIFIED:
                when = parse_email_date(email.get("date")) if email.get("date") else utc_now()
                if route.kind == ACCOUNT and route.app is not None:
                    _attach_note(route.app, new_apps, email_id, when, subject, "account or admin mail")
                    stats["account_attached"] += 1
                    logger.info(f"[{idx}] ACCOUNT MAIL attached")
                elif route.kind == ACCOUNT:
                    stats["account_filtered"] += 1
                    dropped.append(_dropped(email, REASON_ACCOUNT, "account or admin mail"))
                    logger.info(f"[{idx}] ACCOUNT MAIL filtered")
                    continue
                elif route.kind == OPPORTUNITY_NOTE:
                    if thread_id in open_opps:
                        _update_opportunity(open_opps[thread_id], new_opportunities, route, subject, sender, when)
                        logger.info(f"[{idx}] OPPORTUNITY updated")
                elif route.kind == OPPORTUNITY and thread_id and thread_id in dismissed:
                    logger.info(f"[{idx}] OPPORTUNITY dismissed earlier")
                elif route.kind == OPPORTUNITY:
                    opportunity_id = uuid_lib.uuid4()
                    row = {
                        "id": opportunity_id, "user_id": user.id, "company": route.company, "role": route.role,
                        "sender": sender[:500], "subject": subject[:500], "date": when, "thread_id": thread_id,
                        "message_id": email_id, "status": "open",
                    }
                    new_opportunities.append(row)
                    placeholder = SimpleNamespace(**row)
                    if thread_id:
                        open_opps[thread_id] = placeholder
                    if route.company:
                        open_by_company[route.company.lower()] = placeholder
                    stats["opportunities"] += 1
                    logger.info(f"[{idx}] OPPORTUNITY")
                if email_id:
                    new_cache_entries.append({"gmail_message_id": email_id, "user_id": user.id, "processed": True})
                continue

            result = classification_results.get(email_id)
            if isinstance(result, AiPending):
                continue
            if not isinstance(result, dict):
                stats["not_job"] += 1
                detail = f"{result.by}: {result.detail}" if isinstance(result, NotJob) else ""
                dropped.append(_dropped(email, REASON_NOT_JOB, detail))
                logger.info(f"[{idx}] NOT JOB RELATED")
                continue

            company        = result.get("company") or "Unknown"
            role           = role_or_unknown(result.get("role"), company)
            status         = result.get("status") or "Applied"
            confidence     = float(result.get("status_confidence", result.get("confidence") or 0.5))
            interview_date = result.get("interview_date")
            job_id         = result.get("job_id") or None
            location       = result.get("location") or None
            applied_date   = parse_email_date(email.get("date")) if email.get("date") else utc_now()
            fingerprint    = make_fingerprint(company, role, applied_date)

            if company == "Unknown" and role == "Unknown":
                clear_status = status in SAVE_WITHOUT_COMPANY and confidence >= SAVE_WITHOUT_COMPANY_CONFIDENCE
                if not (clear_status or result.get("keep_without_company")):
                    stats["no_company_or_role"] += 1
                    dropped.append(_dropped(email, REASON_NO_COMPANY_OR_ROLE, f"status {status}"))
                    logger.info(f"[{idx}] NO COMPANY OR ROLE")
                    continue
                stats["kept_without_company"] += 1

            effective_status = stored_status(status, confidence)
            stats["kept"] += 1
            if effective_status == "Needs Review":
                stats["needs_review"] += 1

            existing = _find_existing(
                thread_id, job_id, fingerprint, company, role,
                effective_status,
                existing_by_thread, existing_by_job_id,
                existing_by_fingerprint, existing_by_company,
                stats,
            )
            if existing and stats["matched_by_company"] and \
            existing_by_company.get(company.lower(), []) and \
            len(existing_by_company.get(company.lower(), [])) == 1:
                logger.info(f"[{idx}] COMPANY MATCH (1 record)")

            action_needed = bool(result.get("action_needed"))
            if existing and (action_needed or result.get("keep_status")):
                effective_status = existing.status

            new_event, raw_metadata = _build_metadata(
                subject, sender, body, result, effective_status, confidence, email_date=applied_date,
                message_id=email_id,
            )

            if existing:
                skip = _apply_to_existing(
                    idx, existing, effective_status, confidence,
                    interview_date, raw_metadata, new_event, email_id,
                    company, role, fingerprint, thread_id, job_id,
                    new_cache_entries, existing_by_thread,
                    existing_by_job_id, existing_by_fingerprint, stats, new_apps=new_apps
                )
                if skip:
                    continue
                if action_needed:
                    _flag_action_needed(existing, new_apps)
                converted_app_id = getattr(existing, "id", None)
                if applied_date:
                    affected_dates.add(local_date(applied_date))
            else:
                _create_new(
                    user, company, role, effective_status,
                    applied_date, interview_date, job_id, location,
                    fingerprint, thread_id, raw_metadata, new_event,
                    new_apps, existing_by_thread, existing_by_job_id,
                    existing_by_fingerprint, existing_by_company, stats, action_needed=action_needed,
                )
                converted_app_id = new_apps[-1]["id"]
                if applied_date:
                    affected_dates.add(local_date(applied_date))
            opportunity = open_opps.get(thread_id) if thread_id else None
            if opportunity is None and company != "Unknown" and effective_status in APPLIED_STATUSES:
                # The same company writing about an interview, assessment or application.
                opportunity = open_by_company.get(company.lower())
            if opportunity is not None and effective_status != "Needs Review" and not result.get("keep_status"):
                conversions.append((opportunity.id, converted_app_id))
                for index in (open_opps, open_by_company):
                    for key in [k for k, v in index.items() if v is opportunity]:
                        del index[key]
                stats["opportunities_converted"] += 1
            TRACKABLE_STATUSES = {"Rejected", "Interview", "Assessment", "Offer"}
            if effective_status in TRACKABLE_STATUSES:
                is_new_event = (
                    not existing or
                    (existing and existing.status != effective_status)
                )
                if is_new_event:
                    sync_events.append({
                        "status": effective_status,
                        "company": company if company != "Unknown" else None,
                        "role": role if role != "Unknown" else None,
                    })
                    if company != "Unknown" or role != "Unknown":
                        moment_triggers.append({
                            "moment_type": MOMENT_TYPE_BY_STATUS[effective_status],
                            "company": company,
                            "role": role,
                        })
            if email_id:
                new_cache_entries.append({
                    "gmail_message_id": email_id,
                    "user_id": user.id,
                    "processed": True,
                })

            match_type = (
                "thread"      if existing and existing_by_thread.get(thread_id) is existing else
                "job_id"      if existing and job_id and existing_by_job_id.get(job_id) is existing else
                "fingerprint" if existing and fingerprint and existing_by_fingerprint.get(fingerprint) is existing else
                "company"     if existing else
                "new"
            )
            logger.info(
                f"[{idx}/{len(emails_to_classify)}] "
                f"status={effective_status} | "
                f"conf={confidence:.2f} | fingerprint={fingerprint} | "
                f"job_id={job_id} | match={match_type}"
            )

        except Exception:
            logger.warning(f"[{idx}] Unexpected error", exc_info=True)
            continue

    try:
        await _batch_save(db, new_apps, new_cache_entries, new_opportunities)
        await mark_converted(db, conversions)
    except Exception:
        await db.rollback()
        logger.error("Batch save failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")

    try:
        await record_dropped(db, user.id, [d for d in dropped if d["gmail_message_id"]])
        await forget_dropped(db, user.id, [e["gmail_message_id"] for e in new_cache_entries])
    except Exception:
        await db.rollback()
        logger.warning("Failed to record dropped emails", exc_info=True)

    # Look applications up by company/role: new ones only get an id once saved,
    # and some were matched mid-batch through an in-memory placeholder.
    for trigger in moment_triggers:
        try:
            app_result = await db.execute(
                select(Application)
                .where(
                    Application.user_id == user.id,
                    Application.company == trigger["company"],
                    Application.role == trigger["role"],
                )
                .order_by(Application.last_updated.desc())
                .limit(1)
            )
            matched_app = app_result.scalar_one_or_none()
            if matched_app:
                await generate_moment(
                    user=user, db=db, application=matched_app,
                    moment_type=trigger["moment_type"],
                )
        except Exception:
            logger.warning("Failed to generate companion moment during sync", exc_info=True)

    # Emails waiting in an AI batch come back on the next sync, so the cursor stops before them.
    cursor = fetched.cursor_without(held | unprocessed)
    if cursor:
        await _save_cursor(db, account, cursor)

    try:
        await update_streak(user=user, db=db)
        await save_goal_record(
            user=user,
            db=db,
            affected_dates=affected_dates if affected_dates else None,
        )
    except Exception:
        logger.warning("Streak/goals update failed", exc_info=True)

    _log_stats(stats, ai_used)
    summary = _build_summary(stats, sync_events)
    ai_error = ERR_AI_UNAVAILABLE if stats["ai_failed"] else None
    if unprocessed:
        await tracker.finish(CANCELLED, funnel=stats, summary=summary)
    elif held:
        await mark_sync_ok(db, user, account, record_time=False)
        await tracker.finish(WAITING_FOR_AI, funnel=stats, summary=summary, error_code=ai_error)
    else:
        await mark_sync_ok(db, user, account)
        await tracker.finish(SUCCEEDED, funnel=stats, summary=summary, error_code=ai_error)

    return {
        "synced":      stats["saved_new"] + stats["updated_existing"],
        "skipped":     stats["already_processed"] + stats["ignored_by_you"] + stats["blocked_by_filter"] + stats["job_alerts"] +
                    stats["social"] + stats["surveys"] + stats["account_filtered"] + stats["not_job"] +
                    stats["no_company_or_role"],
        "stats":       stats,
        "ai_used":     ai_used,
        "message":     f"Saved {stats['saved_new']} new, updated {stats['updated_existing']} existing",
        "error":       False,
        "fetch_failed": fetched.failed,
        "sync_moment": summary["sync_moment"],
        "run_id":      str(tracker.run_id),
        "cancelled":   bool(unprocessed),
    }
