"""The API the web app uses: create, edit, the computed list fields, and serving the built app."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from applications.schemas import ApplicationResponse
from auth.models import User
from tests.conftest import create_test_application, make_client
from web_app import mount_web_app


@pytest.mark.asyncio
async def test_create_application_from_json(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.post("/applications/", json={
            "company": " Northwind Labs ", "role": "Data Engineer", "status": "Interview", "applied_date": "2026-10-21",
        })
        assert response.status_code == 201
        body = response.json()
        assert body["company"] == "Northwind Labs"
        assert body["status"] == "Interview"
        assert body["source"] == "manual"
        assert body["applied_date"].startswith("2026-10-21")
        assert body["email_count"] == 0

        again = await client.post("/applications/", json={"company": "Northwind Labs", "role": "Data Engineer"})
        assert again.status_code == 409

        bad = await client.post("/applications/", json={"company": "X", "role": "Y", "status": "Hired"})
        assert bad.status_code == 422
        blank = await client.post("/applications/", json={"company": "  ", "role": "Y"})
        assert blank.status_code == 422


@pytest.mark.asyncio
async def test_status_change_returns_the_application_with_an_edit_on_the_timeline(db: AsyncSession, mock_user: User):
    app = await create_test_application(db, mock_user, "Brightwave", "Backend Engineer", "Applied")
    async with make_client(mock_user, db) as client:
        response = await client.patch(f"/applications/{app.id}", json={"status": "Interview"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "Interview"
        assert body["manually_modified"] is True
        assert body["timeline"][-1]["kind"] == "edit"
        assert body["timeline"][-1]["change"] == "Applied to Interview"

        notes = await client.patch(f"/applications/{app.id}", json={"notes": "Ask about the team"})
        assert notes.json()["notes"] == "Ask about the team"
        assert len(notes.json()["timeline"]) == 1

        invalid = await client.patch(f"/applications/{app.id}", json={"status": "Hired"})
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_metadata_update_is_typed_and_records_the_edit(db: AsyncSession, mock_user: User):
    app = await create_test_application(db, mock_user, "Orchard", "Unknown", "Applied")
    async with make_client(mock_user, db) as client:
        response = await client.patch(f"/applications/{app.id}/metadata", json={"role": "Robotics Engineer"})
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "Robotics Engineer"
        assert body["company"] == "Orchard"
        assert body["timeline"][-1]["subject"] == "Role edited by you"
        assert body["timeline"][-1]["change"] == "Unknown to Robotics Engineer"

        bad_date = await client.patch(f"/applications/{app.id}/metadata", json={"interview_date": "13-11-2026"})
        assert bad_date.status_code == 422
        missing = await client.patch(
            "/applications/00000000-0000-0000-0000-000000000000/metadata", json={"role": "X"},
        )
        assert missing.status_code == 404


def _response(status: str, history: list[dict], applied_days_ago: int = 30) -> ApplicationResponse:
    now = datetime.now(timezone.utc)
    return ApplicationResponse(
        id="00000000-0000-0000-0000-000000000001", company="Kestrel", role="Java Developer", status=status,
        applied_date=now - timedelta(days=applied_days_ago), source="gmail", notes=None,
        raw_metadata={"history": history},
    )


def test_computed_fields_from_history():
    now = datetime.now(timezone.utc)
    history = [
        {"date": (now - timedelta(days=30)).isoformat(), "status": "Applied", "subject": "Thanks for applying"},
        {"date": (now - timedelta(days=20)).isoformat(), "status": "Applied", "subject": "We got your CV"},
        {"date": (now - timedelta(days=18)).isoformat(), "status": "Assessment", "subject": "Your test"},
    ]
    app = _response("Assessment", history)
    assert app.email_count == 3
    assert app.no_reply_days == 18
    assert [e.change for e in app.timeline] == ["Applied", None, "Applied to Assessment"]
    assert abs((app.last_activity_at - (now - timedelta(days=18))).total_seconds()) < 1


def test_no_reply_only_for_waiting_statuses_after_14_days():
    now = datetime.now(timezone.utc)
    recent = [{"date": (now - timedelta(days=3)).isoformat(), "status": "Applied", "subject": "x"}]
    assert _response("Applied", recent).no_reply_days is None
    assert _response("Interview", [], applied_days_ago=40).no_reply_days is None
    assert _response("Applied", [], applied_days_ago=40).no_reply_days == 40


@pytest.mark.asyncio
async def test_sync_endpoint_has_a_typed_answer(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        schema = (await client.get("/openapi.json")).json()
    sync = schema["paths"]["/applications/sync"]["post"]["responses"]["200"]
    assert sync["content"]["application/json"]["schema"]["$ref"].endswith("/SyncStarted")


@pytest.mark.asyncio
async def test_built_web_app_is_served_next_to_the_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Job</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")

    web = FastAPI()

    @web.get("/applications/")
    async def applications():
        return [{"id": 1}]

    mount_web_app(web, tmp_path)
    html = {"accept": "text/html,application/xhtml+xml"}
    async with AsyncClient(transport=ASGITransport(app=web), base_url="http://test") as client:
        assert "<title>Job</title>" in (await client.get("/", headers=html)).text
        assert "<title>Job</title>" in (await client.get("/applications", headers=html)).text
        assert "<title>Job</title>" in (await client.get("/analytics", headers=html)).text
        api = await client.get("/applications/", headers={"accept": "application/json"})
        assert api.json() == [{"id": 1}]
        assert (await client.get("/assets/app.js")).text == "console.log(1)"
        assert (await client.get("/favicon.svg")).text == "<svg/>"
        assert "<title>Job</title>" not in (await client.get("/docs", headers=html)).text
        assert (await client.post("/applications", headers=html)).status_code != 200


def test_nothing_is_mounted_without_a_build(tmp_path):
    web = FastAPI()
    routes = len(web.routes)
    mount_web_app(web, tmp_path)
    assert len(web.routes) == routes
