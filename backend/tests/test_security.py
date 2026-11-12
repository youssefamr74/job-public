"""Local-only request checks: Host (DNS rebinding), cross-site changes (CSRF), CORS, secrets and logs."""
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from ai.service import save_config
from applications.sync_service import sync_applications
from auth.dependencies import get_current_user
from config import Settings
from database import get_db
from main import app
from security import RedactQueryParams
from tests.conftest import make_client
from tests.test_sync_runs import Harness, fetched, local_user  # noqa: F401

WEB = "http://localhost:5173"
CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def raw_client(host: str = "127.0.0.1:8000", **headers) -> AsyncClient:
    """A client that sends exactly these headers (and this Host), like a browser on another site would."""
    return AsyncClient(transport=ASGITransport(app=app), base_url=f"http://{host}", headers=headers)


@pytest.fixture
def as_user(db, mock_user):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield mock_user
    app.dependency_overrides.clear()


# --- Host header (DNS rebinding) -----------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "LOCALHOST:8000", "localhost:5173"])
async def test_local_hosts_are_served(host):
    async with raw_client(host) as client:
        assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "localhost", "localhost:9999",
                                  "127.0.0.1.evil.example:8000", "localhost:8000@evil", ""])
async def test_other_hosts_are_refused(host, as_user):
    async with raw_client("127.0.0.1:8000") as client:
        for request in (client.build_request("GET", "/applications/"), client.build_request("GET", "/")):
            request.headers["host"] = host
            response = await client.send(request)
            assert response.status_code == 421
            assert response.text == "Unknown host"


@pytest.mark.asyncio
async def test_configured_backend_url_counts_as_local(monkeypatch):
    monkeypatch.setattr("config.settings.BACKEND_URL", "http://job.lan:9000")
    async with raw_client("job.lan:9000") as client:
        assert (await client.get("/health")).status_code == 200


# --- cross-site changes (CSRF) -------------------------------------------------------------------------

def change_routes():
    for route in app.routes:
        for method in sorted(getattr(route, "methods", None) or ()):
            if method in CHANGE_METHODS:
                yield method, route.path.replace("{", "").replace("}", "")


def test_there_are_change_routes_to_protect():
    assert len(list(change_routes())) > 30


@pytest.mark.asyncio
async def test_every_change_route_needs_the_header(as_user):
    async with raw_client() as client:
        for method, path in change_routes():
            response = await client.request(method, path, json={})
            assert (response.status_code, response.text) == (403, "Missing X-Requested-With header"), (method, path)


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},
    {"Origin": "http://localhost:5173.evil.example"},
    {"Origin": "http://localhost:8001"},
    {"Origin": "null"},
    {"Referer": "https://evil.example/page"},
])
async def test_changes_from_other_sites_are_refused_even_with_the_header(headers, as_user):
    async with raw_client(**{"X-Requested-With": "XMLHttpRequest"}, **headers) as client:
        response = await client.post("/notifications/read-all")
        assert (response.status_code, response.text) == (403, "Cross-site request")


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {},
    {"Origin": WEB},
    {"Origin": "http://127.0.0.1:8000"},
    {"Referer": f"{WEB}/notifications"},
])
async def test_changes_from_the_web_app_go_through(headers, as_user):
    async with raw_client(**{"X-Requested-With": "XMLHttpRequest"}, **headers) as client:
        response = await client.post("/notifications/read-all")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_reads_need_no_header(as_user):
    async with raw_client(Origin="https://evil.example") as client:
        assert (await client.get("/notifications/unread-count")).status_code == 200


# --- CORS ----------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cors_allows_only_the_web_origin():
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-requested-with"}
    async with raw_client() as client:
        ours = await client.options("/applications/", headers={"Origin": WEB, **preflight})
        theirs = await client.options("/applications/", headers={"Origin": "https://evil.example", **preflight})
        read = await client.get("/health", headers={"Origin": "https://evil.example"})
    assert ours.headers["access-control-allow-origin"] == WEB
    assert "x-requested-with" in ours.headers["access-control-allow-headers"].lower()
    assert theirs.status_code == 400
    assert "access-control-allow-origin" not in theirs.headers
    assert "access-control-allow-origin" not in read.headers


@pytest.mark.parametrize("origins", [["*"], [WEB, "*"], ["https://*.example"]])
def test_a_wildcard_cors_origin_is_rejected(origins):
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(CORS_ORIGINS=origins)


# --- secrets -------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_get_endpoint_returns_stored_secrets(db, mock_user_with_gmail):
    await save_config(db, mock_user_with_gmail, "openai", "model-small", "sk-secret-api-key", None,
                      "full", 2000, False, 20)
    secrets = ["client-secret", "fake_access_token", "fake_refresh_token", "sk-secret-api-key"]
    paths = [r.path for r in app.routes if "GET" in (getattr(r, "methods", None) or ()) and "{" not in r.path
             and r.path not in ("/mail/oauth/callback",)]
    async with make_client(mock_user_with_gmail, db) as client:
        for path in paths:
            response = await client.get(path)
            assert response.status_code < 500, path
            for secret in secrets:
                assert secret not in response.text, (path, secret)


@pytest.mark.asyncio
async def test_docs_are_reachable_locally():
    async with raw_client() as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200


# --- logs ----------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_logs_no_email_content(db, local_user, caplog):  # noqa: F811
    result = fetched(3)
    markers = []
    for n, mail in enumerate(result.emails):
        marker = f"zqmarker{n}"
        mail["subject"] += f" ref {marker}subject"
        mail["body"] += f" Your reference is {marker}body."
        mail["sender"] = f"Recruiter {marker}sender <talent@{marker}mail.example>"
        markers += [f"{marker}subject", f"{marker}body", f"{marker}sender"]
    result.emails.append({"id": "news", "thread_id": "tn", "date": result.emails[0]["date"],
                          "sender": "Weekly zqnewssender <news@digest.example>",
                          "subject": "Your weekly digest zqnewssubject", "body": "Unsubscribe zqnewsbody"})
    markers += ["zqnewssender", "zqnewssubject", "zqnewsbody"]

    caplog.set_level(logging.DEBUG)
    with Harness(fetch_result=result):
        outcome = await sync_applications(local_user, db)
    assert outcome.get("error") is False
    assert caplog.records
    for marker in markers:
        assert marker not in caplog.text, marker


def test_oauth_codes_are_redacted_from_the_access_log():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', (
        "127.0.0.1:5000", "GET", "/mail/oauth/callback?state=st4te&code=4/c0de&scope=gmail", "1.1", 303,
    ), None)
    RedactQueryParams().filter(record)
    message = record.getMessage()
    assert "st4te" not in message and "4/c0de" not in message
    assert "state=[redacted]&code=[redacted]&scope=gmail" in message
