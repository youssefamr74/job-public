"""Let AI review the applications the rules couldn't settle, using the original emails."""

from __future__ import annotations

import html
import logging
import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.classify import batch_eligible, classify_each, submit_batch_job
from ai.clients import AIError
from ai.models import PURPOSE_REVIEW, AIBatchJob
from ai.prompts import AIClassification
from ai.service import active
from applications.models import Application
from applications.service import is_valid_transition
from auth.models import User
from classifier.ats_intelligence import classify_status
from classifier.normalization import display_role, is_platform_name, make_fingerprint, normalize_company
from classifier.role_quality import role_or_unknown
from classifier.text import clean_text
from constants.app_config import MAX_RESULTS
from mail.base import MailMessage
from mail.service import open_mail_source
from utils.timeutil import utc_now

logger = logging.getLogger(__name__)


def _needs_review(app: Application) -> bool:
    return (
        app.status == "Needs Review"
        or app.company in (None, "Unknown")
        or is_platform_name(app.company)
        or app.role in (None, "Unknown")
    )


def _latest_message_id(app: Application) -> Optional[str]:
    for event in reversed((app.raw_metadata or {}).get("history") or []):
        if event.get("message_id"):
            return event["message_id"]
    return None


def _match_key(subject: str, sender: str) -> tuple[str, str]:
    return clean_text(html.unescape(subject or "")).lower(), (sender or "").strip().lower()


async def _find_by_subject(source, apps: list[Application]) -> dict[str, tuple[Application, MailMessage]]:
    """For applications saved before message ids were recorded: find their latest email again."""
    wanted = {}
    for app in apps:
        meta = app.raw_metadata or {}
        if meta.get("subject"):
            wanted[_match_key(meta["subject"], meta.get("sender", ""))] = app
    if not wanted:
        return {}
    since = min(a.applied_date for a in wanted.values() if a.applied_date).date() - timedelta(days=1)
    listing = await source.list_new_messages(None, since, MAX_RESULTS)
    fetched = await source.fetch_messages([ref.id for ref in listing.refs])
    found: dict[str, tuple[Application, MailMessage]] = {}
    for message_id, message in fetched.items():
        if isinstance(message, MailMessage):
            app = wanted.pop(_match_key(message.subject, message.sender), None)
            if app is not None:
                found[message_id] = (app, message)
    return found


def _not_job_item(app: Application) -> dict:
    meta = app.raw_metadata or {}
    return {"id": str(app.id), "subject": meta.get("subject"), "sender": meta.get("sender")}


def _hint(app: Application) -> dict:
    return {"company": app.company, "role": app.role, "status": app.status}


def _keeps_status(app: Application) -> bool:
    """Course enrollment mail says nothing about the application: AI must not change its status."""
    meta = app.raw_metadata or {}
    if (meta.get("classifier_result") or {}).get("keep_status"):
        return True
    return classify_status(meta.get("subject") or "", meta.get("snippet") or "").keep_status


def apply_answer(app: Application, parsed: Optional[AIClassification], taken: dict) -> str:
    """Returns "updated", "unchanged", "not_job" or "failed"."""
    if parsed is None:
        return "failed"
    if not parsed.is_job_related:
        return "not_job"
    before = (app.company, app.role, app.status)
    if app.company in (None, "Unknown") or is_platform_name(app.company):
        company = normalize_company(parsed.company)
        if company != "Unknown":
            app.company = company
    if app.role in (None, "Unknown"):
        role = role_or_unknown(display_role(parsed.role), app.company)
        if role != "Unknown":
            app.role = role
    if parsed.status != "Needs Review" and not _keeps_status(app) and (
        app.status == "Needs Review" or is_valid_transition(app.status, parsed.status)
    ):
        app.status = parsed.status
    if (app.company, app.role, app.status) == before:
        return "unchanged"

    fingerprint = make_fingerprint(app.company, app.role, app.applied_date)
    if fingerprint and taken.get(fingerprint, app.id) != app.id:
        fingerprint = None
    if app.application_fingerprint and taken.get(app.application_fingerprint) == app.id:
        del taken[app.application_fingerprint]
    if fingerprint:
        taken[fingerprint] = app.id
    app.application_fingerprint = fingerprint
    app.raw_metadata = {**(app.raw_metadata or {}), "ai_review": {"at": utc_now().isoformat(), "status": parsed.status}}
    return "updated"


async def _fingerprints(db: AsyncSession, user: User) -> dict:
    rows = await db.execute(select(Application.application_fingerprint, Application.id).where(
        Application.user_id == user.id, Application.application_fingerprint.is_not(None)
    ))
    return {fingerprint: app_id for fingerprint, app_id in rows.all()}


async def ai_review(db: AsyncSession, user: User) -> dict:
    settings = active()
    if settings is None:
        raise AIError("not_configured", "AI is not configured")

    apps = (await db.execute(select(Application).where(Application.user_id == user.id))).scalars().all()
    counts = {"checked": 0, "updated": 0, "unchanged": 0, "not_job": 0, "failed": 0,
              "skipped_manual": 0, "no_message": 0, "queued_in_batch": 0, "not_job_items": []}
    targets: dict[str, Application] = {}
    without_id: list[Application] = []
    apps_to_review: list[Application] = []
    for app in apps:
        if not _needs_review(app):
            continue
        if app.manually_modified:
            counts["skipped_manual"] += 1
            continue
        apps_to_review.append(app)
        message_id = _latest_message_id(app)
        if message_id:
            targets[message_id] = app
        else:
            without_id.append(app)
    if not targets and not without_id:
        return counts

    connection = await open_mail_source(db, user)
    if connection is None:
        raise AIError("no_mail", "Connect a mail account first.")
    try:
        fetched = await connection.source.fetch_messages(list(targets)) if targets else {}
        found = await _find_by_subject(connection.source, without_id) if without_id else {}
    finally:
        await connection.source.close()
    messages = {mid: m for mid, m in fetched.items() if isinstance(m, MailMessage)}
    for message_id, (app, message) in found.items():
        if message_id not in targets:
            targets[message_id] = app
            messages[message_id] = message
    emails = [m.as_email_dict() for m in messages.values()]
    counts["no_message"] = len(apps_to_review) - len(emails)
    counts["checked"] = len(emails)
    if not emails:
        return counts
    hints = {e["id"]: _hint(targets[e["id"]]) for e in emails}

    client = settings.client()
    try:
        if batch_eligible(settings, len(emails)):
            await submit_batch_job(db, user, settings, client, emails, hints, PURPOSE_REVIEW,
                                   {e["id"]: str(targets[e["id"]].id) for e in emails})
            counts["queued_in_batch"] = len(emails)
            return counts
        answers = await classify_each(settings, client, emails, hints)
    finally:
        await client.aclose()

    taken = await _fingerprints(db, user)
    for email in emails:
        app = targets[email["id"]]
        outcome = apply_answer(app, answers.get(email["id"]), taken)
        counts[outcome] += 1
        if outcome == "not_job":
            counts["not_job_items"].append(_not_job_item(app))
    await db.commit()
    logger.info(f"AI review: {counts['updated']} updated of {counts['checked']} checked")
    return counts


async def apply_review_job(db: AsyncSession, user: User, job: AIBatchJob) -> dict:
    counts = {"updated": 0, "unchanged": 0, "not_job": 0, "failed": 0, "skipped_manual": 0, "not_job_items": []}
    taken = await _fingerprints(db, user)
    for item in job.items:
        if not item.get("application_id"):
            continue
        app = (await db.execute(select(Application).where(
            Application.user_id == user.id, Application.id == uuid.UUID(item["application_id"])
        ))).scalar_one_or_none()
        if app is None:
            continue
        if app.manually_modified:
            counts["skipped_manual"] += 1
            continue
        answer = (job.results or {}).get(item["message_id"])
        outcome = apply_answer(app, AIClassification.model_validate(answer) if answer else None, taken)
        counts[outcome] += 1
        if outcome == "not_job":
            counts["not_job_items"].append(_not_job_item(app))
    await db.commit()
    logger.info(f"AI review batch applied: {counts['updated']} updated")
    return counts
