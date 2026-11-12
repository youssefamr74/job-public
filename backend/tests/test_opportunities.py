"""Opportunities: listing, dismissing, and a dismissed thread staying dismissed."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from opportunities.models import Opportunity
from tests.conftest import make_client
from tests.test_categories import OUTREACH, _sync, mail


@pytest.mark.asyncio
async def test_dismiss_and_filter_by_status(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail("o1", *OUTREACH, thread="th-1")])
    async with make_client(mock_user, db) as client:
        [opportunity] = (await client.get("/opportunities/")).json()
        assert opportunity["message_id"] == "o1"
        response = await client.post(f"/opportunities/{opportunity['id']}/dismiss")
        assert response.status_code == 200 and response.json()["status"] == "dismissed"
        assert (await client.post(f"/opportunities/{opportunity['id']}/dismiss")).status_code == 409
        assert (await client.post(f"/opportunities/{opportunity['id']}/convert")).status_code == 200
        assert (await client.get("/opportunities/", params={"status": "open"})).json() == []
        assert (await client.get("/opportunities/", params={"status": "nope"})).status_code == 422
        assert (await client.post("/opportunities/00000000-0000-0000-0000-000000000000/dismiss")).status_code == 404


@pytest.mark.asyncio
async def test_a_dismissed_thread_does_not_come_back(db: AsyncSession, mock_user: User, ai_off):
    await _sync(db, mock_user, [mail("o1", *OUTREACH, thread="th-1")])
    async with make_client(mock_user, db) as client:
        [opportunity] = (await client.get("/opportunities/")).json()
        await client.post(f"/opportunities/{opportunity['id']}/dismiss")

    await _sync(db, mock_user, [mail("o2", OUTREACH[0], "Following up: Data Engineer at Contoso", OUTREACH[2],
                                     thread="th-1")])
    rows = (await db.execute(select(Opportunity.message_id, Opportunity.status))).all()
    assert rows == [("o1", "dismissed")]
