import logging
import uuid
from typing import Optional

from auth.dependencies import get_local_user
from applications.sync_service import sync_applications
from notifications.service import run_checks_safely
from sync_runs.schemas import SyncOptions

logger = logging.getLogger(__name__)


async def run_in_background(session_factory, run_id: uuid.UUID, trigger: str, options: Optional[SyncOptions]) -> None:
    async with session_factory() as session:
        try:
            await sync_applications(
                user=await get_local_user(session), db=session, run_id=run_id, trigger=trigger, options=options,
            )
        except Exception:
            logger.error("Background sync failed", exc_info=True)
    await run_checks_safely(session_factory)
