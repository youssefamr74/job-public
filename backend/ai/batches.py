"""Polls AI batches until they finish. Pending batches are rows in ai_batch_jobs, so a restart
picks them up again on the first poll."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.clients import AIError
from ai.models import BATCH_COMPLETED, BATCH_FAILED, BATCH_PENDING, PURPOSE_CLASSIFY, PURPOSE_REVIEW, AIBatchJob
from ai.prompts import parse_classification
from ai.service import active
from constants.app_config import AI_BATCH_POLL_SECONDS
from utils.timeutil import utc_now

logger = logging.getLogger(__name__)

KEEP_FINISHED_JOBS = timedelta(days=30)


async def poll_batches_once(db: AsyncSession) -> list[AIBatchJob]:
    """Checks every pending batch once. Returns the jobs that finished in this round."""
    settings = active()
    jobs = (await db.execute(select(AIBatchJob).where(AIBatchJob.status == BATCH_PENDING))).scalars().all()
    finished: list[AIBatchJob] = []
    for job in jobs:
        if settings is None or settings.provider.id != job.provider:
            job.status = BATCH_FAILED
            job.error = "The AI settings changed before the batch finished."
            continue
        client = settings.client()
        try:
            state = await client.batch_state(job.remote_id)
            if state.status == "pending":
                continue
            if state.status == "failed":
                job.status = BATCH_FAILED
                job.error = state.detail or "The provider reported the batch as failed."
                continue
            texts = await client.batch_results(job.remote_id)
        except AIError as exc:
            logger.warning(f"Couldn't check an AI batch ({exc.code}); will try again")
            continue
        finally:
            await client.aclose()

        results = {}
        for item in job.items:
            parsed = parse_classification(texts.get(item["custom_id"]) or "")
            results[item["message_id"]] = parsed.model_dump() if parsed else None
        job.results = results
        job.status = BATCH_COMPLETED
        finished.append(job)
        answered = sum(1 for value in results.values() if value)
        logger.info(f"AI batch finished: {answered} of {len(results)} answers usable")

    await db.execute(delete(AIBatchJob).where(
        AIBatchJob.status != BATCH_PENDING, AIBatchJob.updated_at < utc_now() - KEEP_FINISHED_JOBS,
    ).execution_options(synchronize_session=False))
    await db.commit()
    return finished


async def run_pending_work(db: AsyncSession) -> None:
    from applications.ai_review import apply_review_job
    from applications.sync_service import sync_applications
    from sync_runs.models import TRIGGER_BATCH_DONE
    from auth.dependencies import get_local_user

    finished = await poll_batches_once(db)
    if not finished:
        return
    user = await get_local_user(db)
    for job in finished:
        if job.purpose == PURPOSE_REVIEW:
            await apply_review_job(db, user, job)
    # Classified emails were held back from the last sync; the next sync picks up the answers.
    if any(job.purpose == PURPOSE_CLASSIFY for job in finished):
        await sync_applications(user, db, trigger=TRIGGER_BATCH_DONE)


async def batch_worker(session_factory) -> None:
    while True:
        try:
            async with session_factory() as db:
                await run_pending_work(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("AI batch polling failed; will try again", exc_info=True)
        await asyncio.sleep(AI_BATCH_POLL_SECONDS)
