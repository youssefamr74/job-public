"""AI classification for the emails the rules couldn't settle."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.clients import AIClient, AIError, BatchRequest
from ai.models import BATCH_COMPLETED, BATCH_PENDING, PURPOSE_CLASSIFY, AIBatchJob
from ai.prompts import CLASSIFICATION_SCHEMA, CLASSIFY_SYSTEM, AIClassification, classification_message
from ai.service import ActiveAI, active
from applications.service import NEEDS_REVIEW_BELOW
from auth.models import User
from classifier.normalization import display_role, is_platform_name, normalize_company
from classifier.role_quality import role_or_unknown
from classifier.outcomes import AiPending, NotJob
from classifier.service import classify_email
from classifier.utils import parse_interview_date
from constants.app_config import AI_CLASSIFY_MAX_TOKENS, AI_CONCURRENCY

logger = logging.getLogger(__name__)

AI_STATUS_CONFIDENCE = 0.85


def needs_ai(result) -> bool:
    """The rules left the status unsure, or the company or role unknown."""
    if not isinstance(result, dict):
        return False
    return (
        float(result.get("status_confidence", 0.0)) < NEEDS_REVIEW_BELOW
        or result.get("company") in (None, "Unknown")
        or is_platform_name(result.get("company"))
        or result.get("role") in (None, "Unknown")
    )


def compute_confidence(company: str, role: str, status: str, has_thread: bool) -> float:
    confidence = 0.0
    if company != "Unknown":
        confidence += 0.30
    if role != "Unknown":
        confidence += 0.25
    if status not in ("Needs Review", None):
        confidence += 0.30
    if has_thread:
        confidence += 0.15
    return min(confidence, 1.0)


def merge(rule_result: dict, parsed: Optional[AIClassification], has_thread: bool):
    """The AI only fills in what the rules left open; without an answer the rules result stays."""
    if parsed is None:
        return {**rule_result, "ai_error": True}
    if not parsed.is_job_related:
        return NotJob("ai", "the AI judged it not job-related")

    company = rule_result.get("company") or "Unknown"
    if company == "Unknown" or is_platform_name(company):
        candidate = normalize_company(parsed.company)
        if candidate != "Unknown":
            company = candidate
    role = rule_result.get("role") or "Unknown"
    if role == "Unknown":
        candidate = role_or_unknown(display_role(parsed.role), company)
        if candidate != "Unknown":
            role = candidate

    status = rule_result.get("status") or "Needs Review"
    status_confidence = float(rule_result.get("status_confidence", 0.0))
    if status_confidence < NEEDS_REVIEW_BELOW and not rule_result.get("keep_status"):
        status = parsed.status
        status_confidence = AI_STATUS_CONFIDENCE if status != "Needs Review" else 0.0

    return {
        **rule_result,
        "company": company,
        "role": role,
        "status": status,
        "status_confidence": status_confidence,
        "status_found": True,
        "confidence": compute_confidence(company, role, status, has_thread),
        "interview_date": parse_interview_date(parsed.interview_date) or rule_result.get("interview_date"),
        "job_id": parsed.job_id or rule_result.get("job_id"),
        "location": parsed.location or rule_result.get("location"),
        "source": "ai",
        "reason": f"{rule_result.get('reason', '')}; AI filled the gaps".strip("; "),
    }


def batch_eligible(settings: ActiveAI, count: int) -> bool:
    return settings.use_batch and settings.provider.supports_batch and count >= settings.batch_threshold


async def classify_each(
    settings: ActiveAI, client: AIClient, emails: list[dict], rule_results: dict,
    on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> dict[str, Optional[AIClassification]]:
    """One request per email, a few at a time. A failed email gets None."""
    sem = asyncio.Semaphore(AI_CONCURRENCY)
    stop = asyncio.Event()
    finished = 0

    async def one(email: dict) -> Optional[AIClassification]:
        nonlocal finished
        async with sem:
            if stop.is_set():
                return None
            try:
                return await classify_email(
                    client, email, rule_results.get(email["id"]), settings.privacy_mode, settings.body_chars
                )
            except AIError as exc:
                if exc.code in ("auth", "not_found"):
                    stop.set()
                logger.warning(f"AI classification failed: {exc.code}")
                return None
            finally:
                finished += 1
                if on_progress is not None:
                    await on_progress(finished, len(emails))

    answers = await asyncio.gather(*(one(e) for e in emails))
    return {email["id"]: answer for email, answer in zip(emails, answers)}


async def submit_batch_job(
    db: AsyncSession, user: User, settings: ActiveAI, client: AIClient, emails: list[dict],
    rule_results: dict, purpose: str, application_ids: Optional[dict[str, str]] = None,
) -> AIBatchJob:
    items, requests = [], []
    for i, email in enumerate(emails):
        custom_id = f"m{i}"
        item = {"custom_id": custom_id, "message_id": email["id"]}
        if application_ids:
            item["application_id"] = application_ids[email["id"]]
        items.append(item)
        content = classification_message(email, rule_results.get(email["id"]), settings.privacy_mode, settings.body_chars)
        requests.append(BatchRequest(custom_id, CLASSIFY_SYSTEM, [{"role": "user", "content": content}],
                                     AI_CLASSIFY_MAX_TOKENS, CLASSIFICATION_SCHEMA))
    remote_id = await client.submit_batch(requests)
    job = AIBatchJob(user_id=user.id, provider=settings.provider.id, model=settings.model, remote_id=remote_id,
                     purpose=purpose, items=items, status=BATCH_PENDING)
    db.add(job)
    await db.commit()
    logger.info(f"AI batch submitted with {len(items)} emails")
    return job


async def _jobs(db: AsyncSession, user: User, status: str) -> list[AIBatchJob]:
    return list((await db.execute(select(AIBatchJob).where(
        AIBatchJob.user_id == user.id, AIBatchJob.purpose == PURPOSE_CLASSIFY, AIBatchJob.status == status,
    ))).scalars().all())


async def classify_with_ai(
    db: AsyncSession, user: User, emails: list[dict], rule_results: dict, existing_by_thread: dict,
    on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> dict:
    settings = active()
    if settings is None:
        return rule_results
    results = dict(rule_results)
    candidates = [e for e in emails if e.get("id") and needs_ai(rule_results.get(e["id"]))]
    if not candidates:
        return results

    finished: dict[str, Optional[dict]] = {}
    for job in await _jobs(db, user, BATCH_COMPLETED):
        finished.update(job.results or {})
    waiting = {item["message_id"] for job in await _jobs(db, user, BATCH_PENDING) for item in job.items}

    def has_thread(email: dict) -> bool:
        return bool(email.get("thread_id") and email["thread_id"] in existing_by_thread)

    to_send = []
    for email in candidates:
        if email["id"] in finished:
            answer = finished[email["id"]]
            parsed = AIClassification.model_validate(answer) if answer else None
            results[email["id"]] = merge(rule_results[email["id"]], parsed, has_thread(email))
        elif email["id"] in waiting:
            results[email["id"]] = AiPending()
        else:
            to_send.append(email)
    if not to_send:
        return results

    client = settings.client()
    try:
        if batch_eligible(settings, len(to_send)):
            try:
                await submit_batch_job(db, user, settings, client, to_send, rule_results, PURPOSE_CLASSIFY)
                for email in to_send:
                    results[email["id"]] = AiPending()
                return results
            except AIError as exc:
                logger.warning(f"AI batch could not be created ({exc.code}); classifying one by one")
        answers = await classify_each(settings, client, to_send, rule_results, on_progress)
    finally:
        await client.aclose()

    for email in to_send:
        results[email["id"]] = merge(rule_results[email["id"]], answers.get(email["id"]), has_thread(email))
    failed = sum(1 for e in to_send if answers.get(e["id"]) is None)
    logger.info(f"AI classified {len(to_send) - failed} emails, {failed} kept the rules result")
    return results
