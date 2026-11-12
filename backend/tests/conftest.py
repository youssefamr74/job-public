"""Shared test fixtures. Each test gets a fresh in-memory SQLite database."""

import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

# Every setting is fixed here, so a developer's backend/.env or environment can't change test results.
# Environment variables win over the .env file.
_DATA_DIR = tempfile.mkdtemp(prefix="job-tests-")  # keeps logs and the default database out of data/
os.environ.update({
    "DATA_DIR": _DATA_DIR,
    "DATABASE_PATH": os.path.join(_DATA_DIR, "job.db"),
    "HOST": "127.0.0.1",
    "PORT": "8000",
    "BACKEND_URL": "http://127.0.0.1:8000",
    "WEB_SETUP_URL": "http://localhost:5173/setup",
    "CORS_ORIGINS": '["http://localhost:5173"]',
    "SECRET_KEY": "",
    "SQL_ECHO": "false",
    # The app adds the web app's middleware only when web/dist is built, and that middleware changes how
    # requests and background-task errors behave. An empty folder makes tests run the same with or without
    # a build (tests/test_web_api.py mounts a web app of its own).
    "WEB_DIST_DIR": tempfile.mkdtemp(prefix="job-tests-web-"),
})

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from config import settings  # noqa: E402
from database import Base, enable_sqlite_foreign_keys, get_db  # noqa: E402
from main import app  # noqa: E402
from auth.models import User  # noqa: E402
from auth.dependencies import get_current_user  # noqa: E402
from applications.models import Application  # noqa: E402
from goals.models import Goal  # noqa: E402
from mail.models import SOURCE_OAUTH, MailAccount  # noqa: E402
from mail.crypto import encrypt_json  # noqa: E402
from ai.service import set_active  # noqa: E402
from tests.fake_ai import FakeAnthropic, FakeOpenAI, fake_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _no_external_services(monkeypatch):
    """Tests never depend on keys or URLs from the environment or a local .env file."""
    monkeypatch.setattr(settings, "BACKEND_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(settings, "WEB_SETUP_URL", "http://localhost:5173/setup")
    set_active(None)
    yield
    set_active(None)


@pytest.fixture
def fake_ai(monkeypatch):
    """Configures AI against a fake provider server. Returns a function: use(server, provider, **settings)."""
    monkeypatch.setattr("mail.retry.sleep", AsyncMock())

    def use(server=None, provider="openai", **overrides):
        server = server or (FakeAnthropic() if provider == "anthropic" else FakeOpenAI())
        monkeypatch.setattr("ai.service.new_http", server.http)
        set_active(fake_settings(provider, **overrides))
        return server

    return use


@pytest.fixture
def ai_on(fake_ai):
    return fake_ai()


@pytest.fixture
def ai_off():
    set_active(None)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(engine.sync_engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def mock_user(db: AsyncSession) -> User:
    """User without Gmail connected."""
    user = User(id=uuid.uuid4(), email="user@example.com", daily_goal=5, streak_count=0)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def mock_user_with_gmail(db: AsyncSession) -> User:
    """User with a Gmail OAuth account connected using fake credentials."""
    user = User(id=uuid.uuid4(), email="gmailuser@example.com", daily_goal=5, streak_count=0)
    db.add(user)
    await db.flush()
    db.add(MailAccount(
        user_id=user.id,
        source_type=SOURCE_OAUTH,
        email="gmailuser@example.com",
        credentials=encrypt_json({
            "client_id": "client-id", "client_secret": "client-secret",
            "access_token": "fake_access_token", "refresh_token": "fake_refresh_token",
        }),
    ))
    await db.commit()
    await db.refresh(user)
    return user


async def create_test_application(
    db: AsyncSession,
    user: User,
    company: str,
    role: str,
    status: str,
    date_applied: datetime | None = None,
) -> Application:
    obj = Application(
        user_id=user.id,
        company=company,
        role=role,
        status=status,
        applied_date=date_applied or datetime.now(timezone.utc),
        source="manual",
        raw_metadata=None,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def create_test_goal(
    db: AsyncSession,
    user: User,
    date_val: date,
    achieved: int,
    goal_met: bool,
) -> Goal:
    goal = Goal(
        user_id=user.id,
        date=date_val,
        target=user.daily_goal,
        achieved=achieved,
        goal_met=goal_met,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


@asynccontextmanager
async def make_client(user: User, db: AsyncSession):
    """httpx test client whose requests run as `user`, using the test database."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000",
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
