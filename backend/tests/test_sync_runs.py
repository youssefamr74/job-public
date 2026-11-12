"""Sync runs: lifecycle, endpoints, cancel, interruption, AI waiting, error codes, scheduler, options, retention."""

import uuid
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from ai.batches import run_pending_work
from ai.models import PURPOSE_CLASSIFY
from applications.models import Application, EmailCache
from applications.sync_service import sync_applications
from auth.dependencies import LOCAL_USER_ID
from auth.models import User
from classifier.batch_service import classify_with_rules
from classifier.ats_intelligence import _template_cache
from classifier.outcomes import AiPending
from constants.app_config import FULL_SYNC_DAYS, MAX_RESULTS
from mail.base import MailAuthError, MailError, MessageList, MessageRef
from mail.fetch import FetchResult, fetch_new_emails
from mail.models import MailAccount
from mail.service import save_account
from sync_runs import scheduler, service
from sync_runs.models import (
    KEEP_RUNS,
    RUNNING,
    SyncRun,
    TRIGGER_BATCH_DONE,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
)
from sync_runs.schemas import SyncOptions
from tests.conftest import make_client

DATE = "Mon, 15 Jan 2024 10:00:00 +0000"
COMPANIES = [("Brightwave", "brightwave"), ("Northwind Labs", "northwindlabs"), ("Fabrikam", "fabrikam")]


@pytest.fixture(autouse=True)
def isolated_state():
    _template_cache.clear()
    service.cancel_requests.clear()
    scheduler.next_run_at = None
    yield
    service.cancel_requests.clear()
    _template_cache.clear()


@pytest_asyncio.fixture
async def local_user(db) -> User:
    user = User(id=LOCAL_USER_ID, email="local@example.com", daily_goal=5, streak_count=0)
    db.add(user)
    await db.commit()
    await save_account(db, user, "imap", "me@gmail.com", {"app_password": "x"})
    return user


class _Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def sessions(db):
    return lambda: _Session(db)


def email(n: int) -> dict:
    name, domain = COMPANIES[n % len(COMPANIES)]
    return {"id": f"e{n}", "thread_id": f"t{n}", "date": DATE, "sender": f"{name} Careers <jobs@{domain}.example>",
            "subject": f"Application received - {name}",
            "body": f"Thank you for applying to {name} for the Data Analyst position."}


def fetched(count: int) -> FetchResult:
    emails = [email(n) for n in range(count)]
    refs = [MessageRef(e["id"], {"uid": i + 1}) for i, e in enumerate(emails)]
    return FetchResult(
        emails=emails, cursor={"uid": count}, failed=0,
        listing=MessageList(refs=refs, final_cursor={"uid": count}), processed={e["id"] for e in emails},
    )


class Harness:
    def __init__(self, fetch_result=None, fetch_error=None, classify=None, cursor=None, open_error=None, no_account=False):
        self.connection = MagicMock()
        self.connection.source.close = AsyncMock()
        self.connection.cursor = cursor
        self.connection.account = MagicMock()
        self.fetch = AsyncMock(return_value=fetch_result or fetched(0), side_effect=fetch_error)
        self.classify = classify
        self.save_cursor = AsyncMock()
        self.stack = ExitStack()
        opened = AsyncMock(return_value=None if no_account else self.connection, side_effect=open_error)
        self.stack.enter_context(patch("applications.sync_service.open_mail_source", new=opened))
        self.stack.enter_context(patch("applications.sync_service.fetch_new_emails", new=self.fetch))
        self.stack.enter_context(patch("applications.sync_service._save_cursor", new=self.save_cursor))
        if classify is not None:
            self.stack.enter_context(patch("applications.sync_service.classify_emails_batch", new=classify))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stack.close()


async def start(db, user, trigger=TRIGGER_MANUAL) -> SyncRun:
    return await service.create_run(db, user, trigger)


async def reload(db, run: SyncRun) -> SyncRun:
    await db.refresh(run)
    return run


# --- lifecycle ---------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_lifecycle_records_funnel_summary_and_last_sync(db, local_user):
    run = await start(db, local_user)
    assert (run.status, run.trigger, run.finished_at) == (RUNNING, TRIGGER_MANUAL, None)

    seen = {}

    async def classify(emails, existing_by_thread, db=None, user=None, on_progress=None):
        row = (await db.execute(select(SyncRun).where(SyncRun.id == run.id))).scalar_one()
        seen["stage"], seen["total"] = row.stage, row.progress_total
        return classify_with_rules(emails, existing_by_thread)

    with Harness(fetch_result=fetched(3), classify=classify):
        result = await sync_applications(local_user, db, run_id=run.id)

    await reload(db, run)
    assert seen == {"stage": "classifying", "total": 3}
    assert result["run_id"] == str(run.id)
    assert run.status == "succeeded" and run.finished_at is not None and run.stage == "saving"
    assert run.funnel["fetched"] == 3 and run.funnel["saved_new"] == 3
    assert {"new_applications", "updated", "new_rejections", "new_interviews", "needs_review", "new_opportunities",
            "sync_moment"} == set(run.summary)
    assert run.summary["new_applications"] == 3
    assert local_user.last_sync_at is not None
    assert run.error_code is None


@pytest.mark.asyncio
async def test_an_empty_sync_succeeds(db, local_user):
    with Harness():
        result = await sync_applications(local_user, db)
    [run] = (await db.execute(select(SyncRun))).scalars().all()
    assert (run.status, run.trigger) == ("succeeded", TRIGGER_MANUAL)
    assert result["synced"] == 0 and local_user.last_sync_at is not None


@pytest.mark.asyncio
async def test_progress_is_written_at_most_every_two_seconds(db, local_user, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(service, "clock", lambda: now[0])
    run = await start(db, local_user)
    tracker = service.RunTracker(db, run.id)
    await tracker.stage("fetching", total=10)

    now[0] += 0.5
    await tracker.progress(3, 10)
    assert (await reload(db, run)).progress_done == 0
    now[0] += 2.0
    await tracker.progress(7, 10)
    assert (await reload(db, run)).progress_done == 7


@pytest.mark.asyncio
async def test_fetch_reports_progress_per_chunk():
    refs = [MessageRef(f"m{i}", {"uid": i}) for i in range(120)]
    source = SimpleNamespace(
        list_new_messages=AsyncMock(return_value=MessageList(refs=refs, final_cursor={"uid": 120})),
        fetch_messages=AsyncMock(side_effect=lambda ids: {i: _message(i) for i in ids}),
    )
    seen = []

    async def progress(done, total):
        seen.append((done, total))

    result = await fetch_new_emails(source, None, date.today(), 2000, on_progress=progress)
    assert seen == [(50, 120), (100, 120), (120, 120)]
    assert len(result.emails) == 120 and not result.stopped


def _message(message_id):
    from mail.base import MailMessage
    return MailMessage(message_id, None, "s", "a@b.example", DATE, "body")


# --- endpoints ---------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_sync_returns_a_run_id_and_runs_in_the_background(db, local_user):
    with Harness(fetch_result=fetched(2)), patch("applications.routes.AsyncSessionLocal", new=sessions(db)):
        async with make_client(local_user, db) as client:
            response = await client.post("/applications/sync")
            run_id = response.json()["run_id"]
            detail = (await client.get(f"/sync/runs/{run_id}")).json()
            status = (await client.get("/sync/status")).json()
            runs = (await client.get("/sync/runs", params={"limit": 5})).json()
            missing = await client.get(f"/sync/runs/{uuid.uuid4()}")

    assert response.status_code == 200 and set(response.json()) == {"run_id"}
    assert detail["status"] == "succeeded" and detail["trigger"] == "manual"
    assert status["running_run"] is None and status["last_run"]["id"] == run_id
    assert status["last_success_at"] is not None and status["next_scheduled_at"] is None
    assert [r["id"] for r in runs] == [run_id]
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_a_concurrent_sync_gets_409(db, local_user):
    await start(db, local_user)
    async with make_client(local_user, db) as client:
        response = await client.post("/applications/sync")
        status = (await client.get("/sync/status")).json()
    assert response.status_code == 409
    assert status["running_run"]["status"] == "running"

    with Harness():
        again = await sync_applications(local_user, db)
    assert again == {"synced": 0, "message": "Sync already in progress", "error": False}
    assert (await db.execute(select(func.count(SyncRun.id)))).scalar() == 1


@pytest.mark.asyncio
async def test_status_exposes_the_next_scheduled_time(db, local_user):
    when = datetime.now(timezone.utc) + timedelta(minutes=30)
    scheduler.next_run_at = when
    async with make_client(local_user, db) as client:
        data = (await client.get("/sync/status")).json()
    assert datetime.fromisoformat(data["next_scheduled_at"]) == when


@pytest.mark.asyncio
async def test_setup_status_reports_the_sync(db, local_user):
    async with make_client(local_user, db) as client:
        before = (await client.get("/setup/status")).json()
        run = await start(db, local_user)
        during = (await client.get("/setup/status")).json()
        with Harness():
            await sync_applications(local_user, db, run_id=run.id)
        local_user.last_sync_at = None
        await db.commit()
        after = (await client.get("/setup/status")).json()
    assert (before["first_sync_done"], before["sync_running"]) == (False, False)
    assert during["sync_running"] is True
    assert (after["first_sync_done"], after["sync_running"]) == (True, False)
    assert after["last_sync_at"] is not None


# --- cancel ------------------------------------------------------------------------------------------

class _CancelAfterFirstEmail(dict):
    def __init__(self, results, run_id):
        super().__init__(results)
        self.run_id = run_id
        self.reads = 0

    def get(self, key, default=None):
        self.reads += 1
        if self.reads == 1:
            service.request_cancel(self.run_id)
        return super().get(key, default)


@pytest.mark.asyncio
async def test_cancel_mid_run_saves_what_is_done_and_keeps_the_cursor_behind_the_rest(db, local_user):
    run = await start(db, local_user)

    async def classify(emails, existing_by_thread, db=None, user=None, on_progress=None):
        return _CancelAfterFirstEmail(classify_with_rules(emails, existing_by_thread), run.id)

    with Harness(fetch_result=fetched(3), classify=classify) as harness:
        result = await sync_applications(local_user, db, run_id=run.id)

    await reload(db, run)
    assert run.status == "cancelled" and result["cancelled"] is True
    assert harness.save_cursor.await_args.args[2] == {"uid": 1}
    assert [a.company for a in (await db.execute(select(Application))).scalars().all()] == ["Brightwave"]
    cached = {row.gmail_message_id for row in (await db.execute(select(EmailCache))).scalars().all()}
    assert cached == {"e0"}
    assert local_user.last_sync_at is None
    assert run.id not in service.cancel_requests
    assert run.summary["new_applications"] == 1


@pytest.mark.asyncio
async def test_cancel_endpoint(db, local_user):
    run = await start(db, local_user)
    async with make_client(local_user, db) as client:
        response = await client.post(f"/sync/runs/{run.id}/cancel")
        unknown = await client.post(f"/sync/runs/{uuid.uuid4()}/cancel")
    assert response.status_code == 200 and response.json()["cancel_requested"] is True
    assert run.id in service.cancel_requests
    assert unknown.status_code == 404

    with Harness(fetch_result=fetched(2)):
        await sync_applications(local_user, db, run_id=run.id)
    await reload(db, run)
    assert run.status == "cancelled"
    async with make_client(local_user, db) as client:
        assert (await client.post(f"/sync/runs/{run.id}/cancel")).status_code == 409


@pytest.mark.asyncio
async def test_cancel_during_fetching_leaves_the_cursor_before_unfetched_messages():
    refs = [MessageRef(f"m{i}", {"uid": i + 1}) for i in range(120)]
    source = SimpleNamespace(
        list_new_messages=AsyncMock(return_value=MessageList(refs=refs, final_cursor={"uid": 120})),
        fetch_messages=AsyncMock(side_effect=lambda ids: {i: _message(i) for i in ids}),
    )
    calls = []

    result = await fetch_new_emails(source, None, date.today(), 2000, should_stop=lambda: calls.append(1) or len(calls) > 1)
    assert result.stopped and len(result.emails) == 50
    assert result.cursor == {"uid": 50}


@pytest.mark.asyncio
async def test_cancel_before_processing_saves_nothing_and_does_not_move_the_cursor(db, local_user):
    run = await start(db, local_user)
    result = fetched(2)
    result.stopped = True
    with Harness(fetch_result=result) as harness:
        await sync_applications(local_user, db, run_id=run.id)
    await reload(db, run)
    assert run.status == "cancelled"
    harness.save_cursor.assert_not_awaited()
    assert (await db.execute(select(func.count(Application.id)))).scalar() == 0


# --- interruption, retention -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_run_left_running_is_marked_interrupted_and_the_next_sync_resumes(db, local_user):
    stale = await start(db, local_user)
    assert await service.fail_interrupted_runs(db) == 1
    await reload(db, stale)
    assert (stale.status, stale.error_code) == ("failed", "interrupted")
    assert stale.finished_at is not None and "crash" in stale.error_message

    with Harness(cursor={"uid": 41}) as harness:
        await sync_applications(local_user, db)
    assert harness.fetch.await_args.args[1] == {"uid": 41}


@pytest.mark.asyncio
async def test_only_the_last_100_runs_are_kept(db, local_user):
    start_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for n in range(KEEP_RUNS + 5):
        db.add(SyncRun(user_id=local_user.id, trigger="manual", status="succeeded",
                       started_at=start_time + timedelta(minutes=n), finished_at=start_time + timedelta(minutes=n)))
    await db.commit()

    await service.create_run(db, local_user, TRIGGER_MANUAL)

    runs = (await db.execute(select(SyncRun).order_by(SyncRun.started_at))).scalars().all()
    assert len(runs) == KEEP_RUNS
    assert runs[0].started_at.replace(tzinfo=timezone.utc) == start_time + timedelta(minutes=6)
    assert runs[-1].status == "running"


# --- waiting for AI ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pending_ai_batch_ends_as_waiting_and_batch_done_starts_a_follow_up(db, local_user):
    pending = AsyncMock(return_value={"e0": AiPending(), "e1": AiPending()})
    run = await start(db, local_user)
    with Harness(fetch_result=fetched(2), classify=pending) as harness:
        await sync_applications(local_user, db, run_id=run.id)

    await reload(db, run)
    assert run.status == "waiting_for_ai"
    assert run.funnel["waiting_for_ai"] == 2
    assert local_user.last_sync_at is None
    harness.save_cursor.assert_not_awaited()

    job = SimpleNamespace(purpose=PURPOSE_CLASSIFY)
    with Harness(fetch_result=fetched(2)), \
         patch("ai.batches.poll_batches_once", new=AsyncMock(return_value=[job])), \
         patch("auth.dependencies.get_local_user", new=AsyncMock(return_value=local_user)):
        await run_pending_work(db)

    follow_up = (await db.execute(select(SyncRun).where(SyncRun.trigger == TRIGGER_BATCH_DONE))).scalar_one()
    assert follow_up.status == "succeeded"
    assert local_user.last_sync_at is not None


# --- errors ------------------------------------------------------------------------------------------

async def only_run(db) -> SyncRun:
    return (await db.execute(select(SyncRun))).scalar_one()


@pytest.mark.asyncio
async def test_no_mail_account(db, local_user):
    with Harness(no_account=True):
        result = await sync_applications(local_user, db)
    run = await only_run(db)
    assert result["error"] is True
    assert (run.status, run.error_code) == ("failed", "mail_not_connected")


@pytest.mark.asyncio
async def test_account_that_needs_relinking(db, local_user):
    with Harness(open_error=MailAuthError("needs_relink", "Reconnect Gmail to continue.")):
        await sync_applications(local_user, db)
    assert (await only_run(db)).error_code == "mail_needs_relink"


@pytest.mark.asyncio
async def test_rejected_credentials_during_fetch(db, local_user):
    with Harness(fetch_error=MailAuthError("auth", "Subject: Secret offer for Jordan"), ) as harness:
        harness.stack.enter_context(patch("applications.sync_service.record_mail_failure", new=AsyncMock()))
        await sync_applications(local_user, db)
    run = await only_run(db)
    assert (run.status, run.error_code) == ("failed", "mail_auth_failed")
    assert "Secret" not in run.error_message


@pytest.mark.asyncio
async def test_unreachable_mail_provider(db, local_user):
    with Harness(fetch_error=MailError("network", "Connecting to alice@example.com failed")) as harness:
        harness.stack.enter_context(patch("applications.sync_service.record_mail_failure", new=AsyncMock()))
        await sync_applications(local_user, db)
    run = await only_run(db)
    assert run.error_code == "mail_unreachable" and "alice" not in run.error_message


@pytest.mark.asyncio
async def test_an_unexpected_failure_is_internal_and_never_leaks_content(db, local_user):
    with Harness(fetch_error=RuntimeError("body: hello Jordan, your offer is attached")):
        with pytest.raises(RuntimeError):
            await sync_applications(local_user, db)
    run = await only_run(db)
    assert (run.status, run.error_code) == ("failed", "internal")
    assert "Jordan" not in run.error_message
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_ai_failure_keeps_the_rules_result_and_is_reported(db, local_user):
    async def classify(emails, existing_by_thread, db=None, user=None, on_progress=None):
        results = classify_with_rules(emails, existing_by_thread)
        return {key: {**value, "ai_error": True} for key, value in results.items()}

    with Harness(fetch_result=fetched(1), classify=classify):
        await sync_applications(local_user, db)
    run = await only_run(db)
    assert (run.status, run.error_code) == ("succeeded", "ai_unavailable")
    assert (await db.execute(select(func.count(Application.id)))).scalar() == 1


# --- scheduler and settings --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduled_tick_skips_while_a_run_is_running(db, local_user):
    await start(db, local_user)
    with Harness() as harness:
        assert await scheduler.scheduled_tick(sessions(db)) is None
    harness.fetch.assert_not_awaited()
    assert (await db.execute(select(func.count(SyncRun.id)))).scalar() == 1


@pytest.mark.asyncio
async def test_scheduled_tick_starts_a_scheduled_run(db, local_user):
    with Harness():
        run_id = await scheduler.scheduled_tick(sessions(db))
    run = await only_run(db)
    assert str(run.id) == run_id and (run.trigger, run.status) == (TRIGGER_SCHEDULED, "succeeded")


@pytest.mark.asyncio
async def test_scheduled_tick_needs_a_mail_account(db):
    db.add(User(id=LOCAL_USER_ID))
    await db.commit()
    assert await scheduler.scheduled_tick(sessions(db)) is None
    assert (await db.execute(select(func.count(SyncRun.id)))).scalar() == 0


@pytest.mark.asyncio
async def test_scheduler_loop_syncs_every_interval(db, local_user, monkeypatch):
    import asyncio

    monkeypatch.setattr(scheduler, "SECONDS_PER_MINUTE", 0.01)
    local_user.sync_interval_minutes = 1
    await db.commit()
    ticks = []

    async def tick(session_factory):
        ticks.append(1)
        if len(ticks) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(scheduler, "scheduled_tick", tick)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(scheduler.sync_scheduler(sessions(db)), timeout=5)
    assert len(ticks) == 2


@pytest.mark.asyncio
async def test_scheduler_is_off_at_zero_until_the_setting_changes(db, local_user, monkeypatch):
    import asyncio

    local_user.sync_interval_minutes = 0
    await db.commit()
    ticks = []
    monkeypatch.setattr(scheduler, "scheduled_tick", AsyncMock(side_effect=lambda f: ticks.append(1)))
    scheduler.settings_changed.clear()
    task = asyncio.create_task(scheduler.sync_scheduler(sessions(db)))
    await asyncio.sleep(0.05)
    assert scheduler.next_run_at is None and ticks == []
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_sync_settings(db, local_user):
    async with make_client(local_user, db) as client:
        assert (await client.get("/settings/sync")).json() == {"interval_minutes": 60}
        assert (await client.put("/settings/sync", json={"interval_minutes": 15})).json() == {"interval_minutes": 15}
        assert (await client.get("/settings/sync")).json() == {"interval_minutes": 15}
        assert (await client.put("/settings/sync", json={"interval_minutes": 0})).status_code == 200
        assert (await client.put("/settings/sync", json={"interval_minutes": -5})).status_code == 422
        assert (await client.put("/settings/sync", json={"interval_minutes": 99999})).status_code == 422
    assert scheduler.settings_changed.is_set()
    scheduler.settings_changed.clear()


# --- first sync options ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_options_apply_to_the_first_sync_only(db, local_user):
    options = SyncOptions(since_date=date(2026, 1, 1), max_messages=25)
    with Harness() as first:
        await sync_applications(local_user, db, options=options)
    assert first.fetch.await_args.args[2:4] == (date(2026, 1, 1), 25)

    with Harness(cursor={"uid": 9}) as later:
        await sync_applications(local_user, db, options=options)
    assert later.fetch.await_args.args[2:4] == (date.today() - timedelta(days=FULL_SYNC_DAYS), MAX_RESULTS)

    with Harness() as default:
        await sync_applications(local_user, db)
    assert default.fetch.await_args.args[2:4] == (date.today() - timedelta(days=FULL_SYNC_DAYS), MAX_RESULTS)


@pytest.mark.asyncio
async def test_sync_body_is_optional_and_validated(db, local_user):
    with Harness(), patch("applications.routes.AsyncSessionLocal", new=sessions(db)):
        async with make_client(local_user, db) as client:
            ok = await client.post("/applications/sync", json={"since_date": "2026-01-01", "max_messages": 10})
            future = await client.post("/applications/sync", json={"since_date": "2999-01-01"})
            too_many = await client.post("/applications/sync", json={"max_messages": 0})
    assert ok.status_code == 200
    assert future.status_code == 422 and too_many.status_code == 422
