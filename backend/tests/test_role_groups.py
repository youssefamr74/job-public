"""Role groups in Analytics: core titles for any profession, merges, "Count as" and AI suggestions.
All titles are made up."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.overview import build_overview, role_rows
from analytics.role_groups_service import refresh_role_groups
from applications.models import Application, RoleGroupMerge
from applications.role_groups import SYNONYMS_FILE, core_title, group_key, role_group
from applications.sync_service import sync_applications
from auth.models import User
from tests.conftest import create_test_application, make_client
from tests.fake_ai import FakeOpenAI
from tests.test_analytics_overview import NOW, app
from tests.test_applications import _fetched, _open_source, _sample_email, _sync_patches

# Titles that must land in one group, for many professions and languages.
SAME_GROUP = [
    ["Registered Nurse", "Senior Registered Nurse (Night Shift)", "Registered Nurse - Remote", "RN"],
    ["Nurse", "Junior Nurse (m/w/d) - Berlin", "Nurse | Hybrid", "Nurse, ICU"],
    ["Primary School Teacher", "Primary School Teacher (Maternity Cover)", "Graduate Primary School Teacher"],
    ["Accountant", "Senior Accountant", "Lead Accountant - London", "Accountant #REQ-48213", "Accountant II"],
    ["Electrician", "Apprentice Electrician", "Electrician Apprentice", "Electrician - Job ID 88213"],
    ["Chef de Partie", "Chef de Partie - Manchester", "Junior Chef de Partie"],
    ["Legal Counsel", "Senior Legal Counsel (f/m/x)", "Legal Counsel, EMEA"],
    ["Physiotherapist", "Physiotherapist – Hybrid", "Physiotherapist in Kraków"],
    ["Full-Stack Developer", "Fullstack Developer", "Full Stack Developer", "Senior full-stack developer"],
    ["Marketing Intern", "Marketing Internship", "Marketing (Intern)", "Werkstudent Marketing (w/m/d)"],
    ["Sales Representative", "Sales Rep", "Sales Rep - Remote"],
    ["Księgowy", "Księgowa", "Młodszy Księgowy / Młodsza Księgowa", "Starsza Księgowa"],
    ["Programista Python", "Programista/ka Python", "Stażysta Programista Python"],
    ["Softwareentwickler", "Softwareentwickler*in", "Software-Entwickler (m/w/d) Vollzeit", "Software Entwickler"],
    ["Krankenpfleger", "Krankenschwester", "Krankenschwester / Krankenpfleger", "Krankenpfleger (m/w/d) Teilzeit"],
    ["Infirmier", "Infirmière", "Infirmier H/F"],
    ["UX/UI Designer", "UI/UX Designer", "UI-UX Designer"],
    ["Customer Service Representative", "Customer Service Representative 100% remote"],
]

# Different jobs that must stay apart.
DIFFERENT = [
    ("Nurse", "Dental Nurse"),
    ("Accountant", "Account Manager"),
    ("Head of Sales", "Sales Representative"),
    ("Team Lead", "Accountant"),
    ("Data Analyst", "Data Engineer"),
    ("Mid-Market Account Executive", "Account Executive"),
]


@pytest.mark.parametrize("titles", SAME_GROUP, ids=lambda titles: titles[0])
def test_titles_of_one_job_share_a_group(titles):
    groups = {title: role_group(title) for title in titles}
    assert len(set(groups.values())) == 1, groups
    assert None not in groups.values()


@pytest.mark.parametrize("first,second", DIFFERENT)
def test_different_jobs_stay_apart(first, second):
    assert role_group(first) != role_group(second)


@pytest.mark.parametrize("role,core", [
    ("Senior Nurse (m/w/d) - Berlin", "Nurse"),
    ("Head of Sales, EMEA", "Head of Sales"),
    ("Junior Full-Stack Developer", "Full-Stack Developer"),
    ("Praktykant - Marketing", "Marketing"),
    ("Data Analyst #REQ-12345", "Data Analyst"),
    ("Warehouse Operative, Night Shift", "Warehouse Operative"),
    ("C++ Developer", "C++ Developer"),
])
def test_core_title_keeps_the_roles_own_words(role, core):
    assert core_title(role) == core


@pytest.mark.parametrize("role", [None, "", "Unknown", "unknown", "Warsaw", "Berlin, Germany", "Intern", "Werkstudent"])
def test_no_role_has_no_group(role):
    assert role_group(role) is None


def test_case_spacing_and_hyphens_are_normalised():
    assert group_key("  Full-STACK   developer ") == group_key("full stack Developer") == "fullstack developer"
    assert group_key("Front-End Engineer") == group_key("Frontend Engineer")


def test_synonyms_file_is_valid():
    data = json.loads(SYNONYMS_FILE.read_text(encoding="utf-8"))
    languages = [key for key in data if not key.startswith("_")]
    assert len(languages) >= 3
    for language in languages:
        assert isinstance(data[language], dict) and data[language]
        for variant, spelling in data[language].items():
            assert variant.strip() and spelling.strip() and variant != spelling
            # Written the way they are compared, so the file reads like what it matches.
            assert variant == variant.lower() and spelling == spelling.lower()


# Analytics rows

def test_overview_groups_by_role_group_and_lists_the_exact_titles():
    apps = [app(1, role="Senior Accountant", status="Rejected", reply_after=1) for _ in range(6)]
    apps += [app(2, role="Accountant (m/f/d)") for _ in range(5)]
    apps += [app(3, role="Electrician")]
    apps += [app(3, role="Unknown"), app(3, role=None)]
    rows = build_overview(apps, "30", 0, 5, now=NOW).by_role
    by_key = {row.key: row for row in rows}

    accountant = by_key["accountant"]
    assert (accountant.label, accountant.applied, accountant.replied, accountant.enough) == ("Accountant", 11, 6, True)
    assert [(t.title, t.applied) for t in accountant.titles] == [("Senior Accountant", 6), ("Accountant (m/f/d)", 5)]
    assert by_key["electrician"].enough is False
    assert (by_key[None].label, by_key[None].applied) == ("Role not found", 2)
    assert [row.key for row in rows] == ["accountant", None, "electrician"]


def test_merges_and_count_as_decide_the_group():
    apps = [app(1, role="Registered Nurse") for _ in range(3)]
    apps += [app(1, role="Staff Nurse"), app(1, role="Krankenschwester")]
    apps += [app(1, role="Barista", role_group_override="Registered Nurse")]
    merges = {"staff nurse": "nurse", "nurse": "registered nurse"}
    rows = role_rows(apps, merges, labels={"registered nurse": "Registered Nurse", "staff nurse": "Staff Nurse"})
    by_key = {row.key: row for row in rows}
    assert by_key["registered nurse"].applied == 5
    assert "krankenpfleger" in by_key
    assert [m.key for m in by_key["registered nurse"].merged] == ["nurse"]
    assert {t.title for t in by_key["registered nurse"].titles} == {"Registered Nurse", "Staff Nurse", "Barista"}


def test_a_merge_cycle_does_not_loop():
    rows = role_rows([app(1, role="Cook"), app(1, role="Chef")], {"cook": "chef", "chef": "cook"}, labels={})
    assert sum(row.applied for row in rows) == 2


# Stored role_group and the API

@pytest.mark.asyncio
async def test_role_group_is_stored_and_follows_role_changes(db: AsyncSession, mock_user: User):
    application = await create_test_application(db, mock_user, "Brightwave", "Senior Pharmacist - Remote", "Applied")
    assert application.role_group == "pharmacist"
    async with make_client(mock_user, db) as client:
        response = await client.patch(f"/applications/{application.id}/metadata", json={"role": "Junior Optician"})
        assert response.status_code == 200
        assert response.json()["role_group"] == "optician"
        created = await client.post("/applications/", json={"company": "Contoso", "role": "Lehrerin (m/w/d)"})
        assert created.json()["role_group"] == "lehrer"


@pytest.mark.asyncio
async def test_refresh_fixes_stale_groups(db: AsyncSession, mock_user: User):
    application = await create_test_application(db, mock_user, "Brightwave", "Senior Plumber", "Applied")
    application.role_group = "old rule"
    await db.commit()
    assert await refresh_role_groups(db) == 1
    await db.refresh(application)
    assert application.role_group == "plumber"


@pytest.mark.asyncio
async def test_count_as_is_saved_without_marking_the_application_edited(db: AsyncSession, mock_user: User):
    application = await create_test_application(db, mock_user, "Brightwave", "Barista", "Applied")
    async with make_client(mock_user, db) as client:
        body = (await client.patch(f"/applications/{application.id}/metadata",
                                   json={"role_group_override": "  Coffee   Specialist "})).json()
        assert body["role_group_override"] == "Coffee Specialist"
        assert body["manually_modified"] is False
        assert body["role"] == "Barista"
        cleared = await client.patch(f"/applications/{application.id}/metadata", json={"role_group_override": ""})
        assert cleared.json()["role_group_override"] is None


@pytest.mark.asyncio
async def test_count_as_survives_a_sync(db: AsyncSession, mock_user_with_gmail: User):
    user = mock_user_with_gmail
    application = await create_test_application(db, user, "Google", "Software Engineer", "Applied")
    async with make_client(user, db) as client:
        await client.patch(f"/applications/{application.id}/metadata", json={"role_group_override": "Developer"})
    result = {"email1": {
        "company": "Google", "role": "Software Engineer", "status": "Interview", "confidence": 0.9,
        "interview_date": None, "job_id": None, "location": None, "source": "deterministic",
    }}
    patches = _sync_patches(_fetched([_sample_email()], {"history_id": "456"}), result)
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock):
        await sync_applications(user, db)
    await db.refresh(application)
    assert application.status == "Interview"
    assert application.role_group_override == "Developer"


@pytest.mark.asyncio
async def test_sync_stores_the_group_of_new_applications(db: AsyncSession, mock_user_with_gmail: User):
    result = {"email1": {
        "company": "Brightwave", "role": "Junior Dental Nurse (m/w/d)", "status": "Applied", "confidence": 0.9,
        "interview_date": None, "job_id": None, "location": None, "source": "deterministic",
    }}
    patches = _sync_patches(_fetched([_sample_email()], {"history_id": "1"}), result)
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock):
        await sync_applications(mock_user_with_gmail, db)
    groups = (await db.execute(select(Application.role_group))).scalars().all()
    assert groups == ["dental nurse"]


async def _add(db, user, role, count=1, status="Applied"):
    for i in range(count):
        await create_test_application(db, user, f"Company {role} {i}", role, status,
                                      date_applied=datetime.now(timezone.utc) - timedelta(days=1))


@pytest.mark.asyncio
async def test_merge_applies_to_future_applications_and_can_be_undone(db: AsyncSession, mock_user: User):
    await _add(db, mock_user, "Waiter", 6)
    await _add(db, mock_user, "Waitress", 5)
    async with make_client(mock_user, db) as client:
        groups = (await client.get("/analytics/role-groups")).json()
        assert {g["key"]: g["applied"] for g in groups["groups"]} == {"waiter": 6, "waitress": 5}

        assert (await client.post("/analytics/role-groups/merge",
                                  json={"source": "waitress", "target": "waiter"})).status_code == 204
        await _add(db, mock_user, "Senior Waitress")
        overview = (await client.get("/analytics/overview", params={"range": "30"})).json()
        rows = {row["key"]: row for row in overview["by_role"]}
        assert rows["waiter"]["applied"] == 12 and rows["waiter"]["enough"] is True
        assert rows["waiter"]["merged"] == [{"key": "waitress", "label": "Waitress"}]
        assert "waitress" not in rows

        cycle = await client.post("/analytics/role-groups/merge", json={"source": "waiter", "target": "waitress"})
        assert cycle.status_code == 409

        assert (await client.delete("/analytics/role-groups/merge", params={"source": "waitress"})).status_code == 204
        rows = {row["key"]: row for row in (await client.get("/analytics/overview", params={"range": "30"})).json()["by_role"]}
        assert rows["waitress"]["applied"] == 6
        assert (await client.delete("/analytics/role-groups/merge", params={"source": "waitress"})).status_code == 404
        assert (await client.post("/analytics/role-groups/merge",
                                  json={"source": "waiter", "target": "Waiter"})).status_code == 422


@pytest.mark.asyncio
async def test_suggestions_need_ai(db: AsyncSession, mock_user: User, ai_off):
    async with make_client(mock_user, db) as client:
        assert (await client.post("/analytics/role-groups/suggest")).status_code == 409


@pytest.mark.asyncio
async def test_suggestions_are_checked_and_never_applied(db: AsyncSession, mock_user: User, fake_ai):
    await _add(db, mock_user, "Bookkeeper", 3)
    await _add(db, mock_user, "Book-keeper", 1)
    await _add(db, mock_user, "Accounts Assistant", 2)
    reply = json.dumps({"merges": [
        {"source": "book keeper", "target": "bookkeeper", "reason": "Same job, other spelling"},
        {"source": "made up", "target": "bookkeeper"},
        {"source": "bookkeeper", "target": "bookkeeper"},
    ]})
    server = fake_ai(FakeOpenAI([reply]))
    async with make_client(mock_user, db) as client:
        response = await client.post("/analytics/role-groups/suggest")
    assert response.status_code == 200
    assert response.json()["suggestions"] == [{
        "source": "book keeper", "source_label": "Book-keeper", "target": "bookkeeper",
        "target_label": "Bookkeeper", "reason": "Same job, other spelling",
    }]
    assert "Accounts Assistant" in json.dumps(server.completions[-1])
    assert (await db.execute(select(RoleGroupMerge))).scalars().all() == []
