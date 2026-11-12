"""Role cleanup at extraction and for role groups, and the "Other roles" minimum. All titles are made up."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.overview import build_overview, role_minimum
from applications.models import Application
from applications.role_groups import core_title, role_group
from applications.sync_service import sync_applications
from auth.models import User
from classifier.normalization import display_role
from classifier.role_quality import not_a_role, role_or_unknown, tidy_role
from tests.conftest import create_test_application
from tests.test_analytics_overview import NOW, app
from tests.test_applications import _fetched, _open_source, _sample_email, _sync_patches


@pytest.mark.parametrize("raw,tidy", [
    ("Position: Registered Nurse", "Registered Nurse"),
    ("Position of Accountant", "Accountant"),
    ("Role of Head of Sales", "Head of Sales"),
    ("The role: Primary School Teacher", "Primary School Teacher"),
    ("Programme: Graduate Civil Engineer", "Graduate Civil Engineer"),
    ("Programme Graduate Software Engineer", "Graduate Software Engineer"),
    ("Stanowisko: Księgowa", "Księgowa"),
    (": Electrician :", "Electrician"),
    ("Sales_Marketing Coordinator", "Sales / Marketing Coordinator"),
    ("Programme Manager", "Programme Manager"),
    ("Job Coach", "Job Coach"),
])
def test_labels_and_punctuation_are_removed(raw, tidy):
    assert tidy_role(raw) == tidy


@pytest.mark.parametrize("role", [
    # Sentences
    "Please contact us if you have any questions about the process",
    "We may get back to you within two weeks",
    "Thank you for your interest",
    "Prosimy o kontakt w sprawie oferty",
    "Bitte senden Sie uns Ihre Unterlagen",
    "Merci pour votre candidature",
    "One two three four five six seven eight nine words of title here",
    # Kind of position, department or field alone
    "Working student", "Werkstudent", "Intern", "Praktykant", "Stagiaire", "Remote",
    "Digital", "Master Data", "Marketing", "IT", "Sprzedaż", "Vertrieb", "Human Resources",
    # Long, with no job-title word
    "Data and Analytics Center of Excellence",
    "Customer Success and Retention Programme Europe",
])
def test_text_that_is_not_a_role(role):
    assert not_a_role(role)
    assert display_role(role) == "Unknown"
    assert role_group(role) is None


@pytest.mark.parametrize("role", [
    "Nurse", "Chef", "Barista", "Electrician", "Pharmacist", "RN", "Head of Sales",
    "Customer Service Representative", "Warehouse Operative", "Teacher of Primary School Mathematics",
    "Finance Business Partner", "Senior Data Platform Engineering Team Lead", "Marketing Intern",
    "Marketing Internship", "Marketing (Intern)", "Werkstudent Marketing (w/m/d)", "Praktykant - Marketing",
    "Księgowa", "Kierowca kat. C", "Krankenpfleger", "Sachbearbeiter Buchhaltung", "Infirmière",
    "Desarrolladora", "Physiotherapist – Hybrid", "Programme Manager",
])
def test_real_roles_are_kept(role):
    assert not not_a_role(role)
    assert role_group(role) is not None


def test_a_role_equal_to_the_company_is_no_role():
    assert role_group("Brightwave", "Brightwave") is None
    assert role_group("Brightwave Careers", "Brightwave") == "brightwave careers"
    assert role_group("Nurse", "Brightwave") == "nurse"
    assert role_or_unknown("brightwave", "Brightwave") == "Unknown"
    assert role_or_unknown("Barista", "Brightwave") == "Barista"


def test_cleaned_roles_group_with_their_plain_title():
    assert role_group("Position: Registered Nurse") == role_group("Registered Nurse")
    assert role_group("Role of Accountant:") == role_group("Accountant")
    assert core_title("Programme: Graduate Civil Engineer - London") == "Civil Engineer"
    assert core_title("Stanowisko: Młodsza Księgowa") == "Księgowa"


@pytest.mark.asyncio
async def test_group_follows_company_changes(db: AsyncSession, mock_user: User):
    application = await create_test_application(db, mock_user, "Brightwave", "Contoso", "Applied")
    assert application.role_group == "contoso"
    application.company = "Contoso"
    await db.commit()
    assert application.role_group is None


@pytest.mark.asyncio
async def test_sync_does_not_take_the_company_as_role(db: AsyncSession, mock_user_with_gmail: User):
    result = {"email1": {
        "company": "Brightwave", "role": "Brightwave", "status": "Applied", "confidence": 0.9,
        "interview_date": None, "job_id": None, "location": None, "source": "deterministic",
    }}
    patches = _sync_patches(_fetched([_sample_email()], {"history_id": "1"}), result)
    with _open_source(), patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("applications.sync_service._save_cursor", new_callable=AsyncMock):
        await sync_applications(mock_user_with_gmail, db)
    rows = (await db.execute(select(Application.role, Application.role_group))).all()
    assert [tuple(r) for r in rows] == [("Unknown", None)]


@pytest.mark.parametrize("total,minimum", [(0, 3), (50, 3), (150, 3), (151, 4), (400, 8), (1000, 20)])
def test_the_minimum_rises_with_volume(total, minimum):
    assert role_minimum(total) == minimum


def test_small_groups_are_marked_and_rows_sort_by_applied():
    apps = [app(1, role="Dental Nurse") for _ in range(3)]
    apps += [app(1, role="Chef de Partie", status="Rejected", reply_after=1) for _ in range(5)]
    apps += [app(1, role="Plumber") for _ in range(2)]
    apps += [app(1, role="Please contact us for details")]
    overview = build_overview(apps, "30", 0, 5, now=NOW)
    assert overview.role_min_applications == 3
    assert [(r.label, r.applied, r.enough) for r in overview.by_role] == [
        ("Chef de Partie", 5, True), ("Dental Nurse", 3, True), ("Plumber", 2, False), ("Role not found", 1, False),
    ]
