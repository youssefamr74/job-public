import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from sync_runs.models import (
    ERR_INTERRUPTED,
    ERROR_MESSAGES,
    FAILED,
    KEEP_RUNS,
    RUNNING,
    SUCCEEDED,
    SyncRun,
)
from utils.timeutil import utc_now

PROGRESS_INTERVAL_SECONDS = 2.0
MAX_INTERVAL_MINUTES = 24 * 60

clock = time.monotonic
cancel_requests: set[uuid.UUID] = set()


class SyncAlreadyRunning(Exception):
    pass


async def get_running(db: AsyncSession, user: User) -> Optional[SyncRun]:
    return (await db.execute(select(SyncRun).where(
        SyncRun.user_id == user.id, SyncRun.status == RUNNING
    ))).scalars().first()


async def create_run(db: AsyncSession, user: User, trigger: str) -> SyncRun:
    if await get_running(db, user) is not None:
        raise SyncAlreadyRunning()
    run = SyncRun(user_id=user.id, trigger=trigger, status=RUNNING)
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise SyncAlreadyRunning()
    await prune_runs(db, user)
    return run


async def prune_runs(db: AsyncSession, user: User) -> None:
    newest = (
        select(SyncRun.id).where(SyncRun.user_id == user.id)
        .order_by(SyncRun.started_at.desc(), SyncRun.id).limit(KEEP_RUNS)
    )
    await db.execute(delete(SyncRun).where(SyncRun.user_id == user.id, SyncRun.id.not_in(newest)))
    await db.commit()


async def fail_interrupted_runs(db: AsyncSession) -> int:
    result = await db.execute(update(SyncRun).where(SyncRun.status == RUNNING).values(
        status=FAILED, finished_at=utc_now(), error_code=ERR_INTERRUPTED, error_message=ERROR_MESSAGES[ERR_INTERRUPTED],
    ))
    await db.commit()
    return result.rowcount or 0


async def list_runs(db: AsyncSession, user: User, limit: int) -> list[SyncRun]:
    return list((await db.execute(
        select(SyncRun).where(SyncRun.user_id == user.id)
        .order_by(SyncRun.started_at.desc(), SyncRun.id).limit(limit)
    )).scalars().all())


async def get_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> Optional[SyncRun]:
    return (await db.execute(select(SyncRun).where(
        SyncRun.id == run_id, SyncRun.user_id == user.id
    ))).scalar_one_or_none()


async def last_success_at(db: AsyncSession, user: User) -> Optional[datetime]:
    return (await db.execute(select(func.max(SyncRun.finished_at)).where(
        SyncRun.user_id == user.id, SyncRun.status == SUCCEEDED
    ))).scalar()


async def first_sync_done(db: AsyncSession, user: User) -> bool:
    return await last_success_at(db, user) is not None or user.last_sync_at is not None


def request_cancel(run_id: uuid.UUID) -> None:
    cancel_requests.add(run_id)


class RunTracker:
    """Keeps a run's stage and progress in the database while the sync works."""

    def __init__(self, db: AsyncSession, run_id: uuid.UUID):
        self.db = db
        self.run_id = run_id
        self._last_write = 0.0
        self._lock = asyncio.Lock()

    @classmethod
    async def begin(cls, db: AsyncSession, user: User, trigger: str, run_id: Optional[uuid.UUID]) -> Optional["RunTracker"]:
        if run_id is None:
            try:
                run_id = (await create_run(db, user, trigger)).id
            except SyncAlreadyRunning:
                return None
        return cls(db, run_id)

    @property
    def cancelled(self) -> bool:
        return self.run_id in cancel_requests

    async def _write(self, **values) -> None:
        async with self._lock:
            await self.db.execute(update(SyncRun).where(SyncRun.id == self.run_id).values(**values))
            await self.db.commit()
            self._last_write = clock()

    async def stage(self, name: str, done: int = 0, total: Optional[int] = None) -> None:
        await self._write(stage=name, progress_done=done, progress_total=total)

    async def progress(self, done: int, total: Optional[int] = None) -> None:
        if clock() - self._last_write < PROGRESS_INTERVAL_SECONDS:
            return
        async with self._lock:
            if clock() - self._last_write < PROGRESS_INTERVAL_SECONDS:
                return
            await self.db.execute(update(SyncRun).where(SyncRun.id == self.run_id).values(
                progress_done=done, progress_total=total))
            await self.db.commit()
            self._last_write = clock()

    async def finish(
        self, status: str, funnel: Optional[dict] = None, summary: Optional[dict] = None,
        error_code: Optional[str] = None,
    ) -> None:
        cancel_requests.discard(self.run_id)
        await self._write(
            status=status, finished_at=utc_now(), funnel=funnel, summary=summary, error_code=error_code,
            error_message=ERROR_MESSAGES.get(error_code) if error_code else None,
        )
