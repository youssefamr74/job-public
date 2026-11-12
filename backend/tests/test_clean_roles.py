"""The one-off cleanup of stored roles. Made-up data only."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from applications.clean_roles import clean_stored_roles
from applications.models import Application
from auth.models import User


async def _add(db, user, company, role, source="gmail", edits=None, fingerprint=None):
    app = Application(user_id=user.id, company=company, role=role, status="Applied", source=source,
                      raw_metadata={"history": [], "edits": edits or []}, application_fingerprint=fingerprint)
    db.add(app)
    await db.commit()
    return app


@pytest.mark.asyncio
async def test_cleans_rejects_and_skips_user_roles(db: AsyncSession, mock_user: User):
    tidied = await _add(db, mock_user, "Brightwave", "Position: Registered Nurse")
    sentence = await _add(db, mock_user, "Contoso", "Please contact us if you have questions")
    company = await _add(db, mock_user, "Fabrikam", "Fabrikam")
    department = await _add(db, mock_user, "Northwind", "Master Data")
    polish = await _add(db, mock_user, "Zielona Sp.", "Stanowisko: Księgowa")
    fine = await _add(db, mock_user, "Tailspin", "Elektriker (m/w/d)")
    typed = await _add(db, mock_user, "Litware", "Digital", source="manual")
    edited = await _add(db, mock_user, "Adatum", "Role of Barista",
                        edits=[{"field": "role", "from": "Barista", "to": "Role of Barista", "date": "2026-11-01"}])

    dry = await clean_stored_roles(db, mock_user)
    assert (dry["rewritten"], dry["rejected"], dry["skipped_user_edited"]) == (2, 3, 2)
    await db.refresh(tidied)
    assert tidied.role == "Position: Registered Nurse"

    report = await clean_stored_roles(db, mock_user, apply=True)
    assert report["before"]["Unknown roles"] == 0 and report["after"]["Unknown roles"] == 3
    for app in (tidied, sentence, company, department, polish, fine, typed, edited):
        await db.refresh(app)
    assert (tidied.role, tidied.role_group) == ("Registered Nurse", "registered nurse")
    assert tidied.raw_metadata["role_before_cleanup"] == "Position: Registered Nurse"
    assert (polish.role, polish.role_group) == ("Księgowa", "ksiegowy")
    assert [a.role for a in (sentence, company, department)] == ["Unknown"] * 3
    assert all(a.role_group is None for a in (sentence, company, department))
    assert fine.role == "Elektriker (m/w/d)"
    assert (typed.role, edited.role) == ("Digital", "Role of Barista")
    assert (await clean_stored_roles(db, mock_user))["changes"] == []


@pytest.mark.asyncio
async def test_keeps_fingerprints_unique(db: AsyncSession, mock_user: User):
    from classifier.normalization import make_fingerprint
    taken = make_fingerprint("Brightwave", "Pharmacist", None)
    await _add(db, mock_user, "Brightwave", "Pharmacist", fingerprint=taken)
    other = await _add(db, mock_user, "Brightwave", "Position: Pharmacist", fingerprint="old")
    await clean_stored_roles(db, mock_user, apply=True)
    await db.refresh(other)
    assert other.role == "Pharmacist" and other.application_fingerprint is None
