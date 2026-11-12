import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from auth.dependencies import get_local_user
from mail.models import STATUS_NEEDS_RELINK
from mail.service import get_mail_account
from sync_runs import service
from sync_runs.models import TRIGGER_SCHEDULED
from sync_runs.runner import run_in_background
from utils.timeutil import utc_now

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60
settings_changed = asyncio.Event()
next_run_at: Optional[datetime] = None


async def scheduled_tick(session_factory) -> Optional[str]:
    """Starts a scheduled sync unless one is running or there is no usable mail account. Returns the run id."""
    async with session_factory() as db:
        user = await get_local_user(db)
        account = await get_mail_account(db, user)
        if account is None or account.status == STATUS_NEEDS_RELINK:
            return None
        try:
            run = await service.create_run(db, user, TRIGGER_SCHEDULED)
        except service.SyncAlreadyRunning:
            logger.info("Scheduled sync skipped: a sync is already running")
            return None
    await run_in_background(session_factory, run.id, TRIGGER_SCHEDULED, None)
    return str(run.id)


async def sync_scheduler(session_factory) -> None:
    global next_run_at
    while True:
        try:
            async with session_factory() as db:
                minutes = (await get_local_user(db)).sync_interval_minutes
            if minutes <= 0:
                next_run_at = None
                await settings_changed.wait()
                settings_changed.clear()
                continue
            seconds = minutes * SECONDS_PER_MINUTE
            next_run_at = utc_now() + timedelta(seconds=seconds)
            try:
                await asyncio.wait_for(settings_changed.wait(), timeout=seconds)
                settings_changed.clear()
                continue
            except asyncio.TimeoutError:
                pass
            next_run_at = None
            await scheduled_tick(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Scheduled sync failed; will try again", exc_info=True)
            await asyncio.sleep(SECONDS_PER_MINUTE)
