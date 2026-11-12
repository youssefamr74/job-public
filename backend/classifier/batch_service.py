from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional, Union

from ai.classify import classify_with_ai
from ai.service import ai_configured
from classifier.ats_intelligence import (
    cache_result,
    classify_email_deterministic,
    get_cached_result,
)
from classifier.outcomes import AiPending, NotJob
from constants.app_config import MEDIUM_CONFIDENCE

logger = logging.getLogger(__name__)

__all__ = ["AiPending", "NotJob", "Outcome", "classify_emails_batch", "classify_with_rules"]

Outcome = Union[dict, NotJob, AiPending]

# Evidence that an email is about an application even when its status is unclear.
# A company from the sender's name or domain alone isn't enough: every newsletter has one.
_STRONG_COMPANY_SOURCES = {"thread", "platform", "text"}


def _maybe_job(det_result: dict, has_thread: bool) -> bool:
    return bool(
        det_result.get("status_found")
        or det_result.get("keep_without_company")
        or det_result.get("application_subject")
        or has_thread
        or det_result.get("platform_sender")
        or det_result.get("role") not in (None, "Unknown")
        or det_result.get("company_source") in _STRONG_COMPANY_SOURCES
    )


def classify_with_rules(emails: list[dict], existing_by_thread: dict) -> dict[str, Outcome]:
    results: dict[str, Outcome] = {}
    for email in emails:
        email_id = email.get("id", "")
        if not email_id:
            continue

        thread_id = email.get("thread_id")
        subject   = email.get("subject") or ""
        sender    = email.get("sender") or ""
        body      = (email.get("body") or "")[:3000]

        context_app    = existing_by_thread.get(thread_id) if thread_id else None
        thread_company = context_app.company if context_app else None
        thread_role    = context_app.role if context_app else None

        key = (sender, thread_company or "", thread_role or "")
        cached = get_cached_result(subject, body, *key)
        if cached is not None:
            results[email_id] = cached
            continue

        det_result = classify_email_deterministic(
            sender=sender, subject=subject, body=body,
            thread_company=thread_company, thread_role=thread_role,
        )
        confidence = float(det_result.get("confidence", 0.0))

        # Anything that might be an application is kept; with an unclear status it lands
        # in Needs Review rather than being thrown away.
        if _maybe_job(det_result, context_app is not None) or confidence >= MEDIUM_CONFIDENCE:
            cache_result(subject, body, det_result, *key)
            results[email_id] = det_result
        else:
            not_job = NotJob("rules", "no status, role or company found beyond the sender's domain")
            cache_result(subject, body, not_job, *key)
            results[email_id] = not_job
    return results


async def classify_emails_batch(
    emails: list[dict],
    existing_by_thread: dict,
    db=None,
    user=None,
    on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> dict[str, Outcome]:
    """Rules first; then, when AI is configured, AI for what the rules couldn't settle."""
    results = classify_with_rules(emails, existing_by_thread)
    kept = sum(1 for v in results.values() if isinstance(v, dict))
    logger.info(f"Rules classified {len(results)} emails, kept {kept}")

    if db is None or user is None or not ai_configured():
        return results

    return await classify_with_ai(db, user, emails, results, existing_by_thread, on_progress)
