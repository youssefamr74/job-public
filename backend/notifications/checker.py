import asyncio

from notifications.service import run_checks_safely

CHECK_EVERY_SECONDS = 60 * 60


async def notification_checker(session_factory) -> None:
    """Date-based checks (interview tomorrow, no reply, weekly summary) at startup and every hour."""
    while True:
        await run_checks_safely(session_factory)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
