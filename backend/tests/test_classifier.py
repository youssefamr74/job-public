"""Tests for the email classifier pipeline."""

from unittest.mock import MagicMock

import pytest

from classifier.ats_intelligence import (
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    classify_email_deterministic,
    extract_role_from_body,
    looks_like_role,
)
from ai.classify import compute_confidence
from classifier.batch_service import classify_emails_batch
from classifier.normalization import normalize_company


def test_looks_like_role_engineer():
    assert looks_like_role("Software Engineer") is True


def test_looks_like_role_developer():
    assert looks_like_role("Backend Developer") is True


def test_looks_like_role_analyst():
    assert looks_like_role("Data Analyst") is True


def test_looks_like_role_noise_only():
    assert looks_like_role("Newsletter Update") is False


def test_looks_like_role_empty_string():
    assert looks_like_role("") is False


def test_extract_role_from_body_position_pattern():
    body = "Thank you for applying for the Software Engineer position at our company."
    result = extract_role_from_body(body)
    assert result != "Unknown"
    assert "Engineer" in result


def test_extract_role_from_body_role_of_pattern():
    body = "We received your application for the role of Data Scientist."
    result = extract_role_from_body(body)
    assert result != "Unknown"
    assert "Scientist" in result


def test_extract_role_from_body_no_match_returns_unknown():
    body = "Please verify your email address to continue."
    assert extract_role_from_body(body) == "Unknown"


def test_extract_role_from_body_noise_rejected():
    """Assessment/programme names must not be returned as a role."""
    body = "applying for the Graduate Programme position."
    assert extract_role_from_body(body) == "Unknown"


def test_extract_role_from_body_none_body():
    assert extract_role_from_body(None) == "Unknown"


def test_deterministic_always_returns_dict():
    result = classify_email_deterministic(
        sender="hr@example.com", subject="some random email", body=""
    )
    assert isinstance(result, dict)
    for field in ("company", "role", "status", "confidence", "source"):
        assert field in result


def test_deterministic_rejected_in_subject():
    result = classify_email_deterministic(
        sender="hr@company.com",
        subject="unfortunately we will not be proceeding",
        body="",
    )
    assert result["status"] == "Rejected"


def test_deterministic_rejected_in_body():
    result = classify_email_deterministic(
        sender="hr@acme.com",
        subject="Update on your application",
        body="We are not moving forward with your candidacy.",
    )
    assert result["status"] == "Rejected"


def test_deterministic_interview_keyword_in_subject():
    result = classify_email_deterministic(
        sender="recruiter@startup.io",
        subject="Interview Invitation – Software Engineer",
        body="",
    )
    assert result["status"] == "Interview"


def test_deterministic_assessment_keyword():
    result = classify_email_deterministic(
        sender="hr@corp.com",
        subject="Next steps: technical assessment",
        body="We'd like you to complete a coding challenge.",
    )
    assert result["status"] == "Assessment"


def test_deterministic_offer_keyword():
    result = classify_email_deterministic(
        sender="hr@finco.com",
        subject="Job offer from FinCo",
        body="We are pleased to offer you the position.",
    )
    assert result["status"] == "Offer"


def test_deterministic_applied_thank_you():
    result = classify_email_deterministic(
        sender="noreply@company.com",
        subject="Thank you for applying to Software Engineer",
        body="We received your application.",
    )
    assert result["status"] == "Applied"


def test_deterministic_none_body_does_not_raise():
    result = classify_email_deterministic(
        sender="hr@example.com", subject="Interview scheduled", body=None
    )
    assert result["status"] == "Interview"


def test_deterministic_thread_memory_both_known_high_confidence():
    """Both company and role from thread → confidence must reach HIGH_CONFIDENCE."""
    result = classify_email_deterministic(
        sender="hr@google.com",
        subject="Interview scheduled",
        body="We'd like to schedule an interview.",
        thread_company="Google",
        thread_role="Software Engineer",
    )
    assert result["company"] == "Google"
    assert result["role"] == "Software Engineer"
    assert result["status"] == "Interview"
    assert result["confidence"] >= HIGH_CONFIDENCE


def test_deterministic_thread_memory_status_from_email_content():
    """Status is extracted from this email, not inherited blindly from thread."""
    result = classify_email_deterministic(
        sender="noreply@tracking.io",
        subject="Your application status update",
        body="Unfortunately we will not be moving forward with your application.",
        thread_company="Spotify",
        thread_role="Backend Engineer",
    )
    assert result["company"] == "Spotify"
    assert result["role"] == "Backend Engineer"
    assert result["status"] == "Rejected"


def test_deterministic_unknown_thread_treated_as_absent():
    """'Unknown' thread_company/role must not be used for scoring."""
    result_with_unknown = classify_email_deterministic(
        sender="hr@company.com",
        subject="Interview scheduled",
        body="",
        thread_company="Unknown",
        thread_role="Unknown",
    )
    result_without_thread = classify_email_deterministic(
        sender="hr@company.com",
        subject="Interview scheduled",
        body="",
    )
    assert result_with_unknown["confidence"] == result_without_thread["confidence"]


def test_deterministic_source_field_is_deterministic():
    result = classify_email_deterministic(
        sender="hr@example.com", subject="Test", body=""
    )
    assert result["source"] == "deterministic"


def test_normalize_company_removes_sp_zoo():
    # "sp. z o.o." stripped, then "Systems" stripped, then override "epam" → "EPAM"
    assert normalize_company("EPAM Systems sp. z o.o.") == "EPAM"


def test_normalize_company_removes_ltd():
    # "Ltd" (without trailing period) matches the suffix pattern
    result = normalize_company("Acme Ltd")
    assert "ltd" not in result.lower()
    assert "Acme" in result


def test_normalize_company_none_returns_unknown():
    assert normalize_company(None) == "Unknown"


def test_normalize_company_empty_returns_unknown():
    assert normalize_company("") == "Unknown"


def test_compute_confidence_all_known_with_context():
    # company(0.30) + role(0.25) + status(0.30) + context(0.15) = 1.0
    assert compute_confidence("Google", "SWE", "Interview", True) == 1.0


def test_compute_confidence_all_known_no_context():
    # company(0.30) + role(0.25) + status(0.30) = 0.85
    conf = compute_confidence("Google", "SWE", "Applied", False)
    assert abs(conf - 0.85) < 0.001


def test_compute_confidence_unknown_company():
    # role(0.25) + status(0.30) = 0.55
    conf = compute_confidence("Unknown", "SWE", "Applied", False)
    assert abs(conf - 0.55) < 0.001


def test_compute_confidence_needs_review_gives_no_status_score():
    # company(0.30) + role(0.25) = 0.55
    conf = compute_confidence("Google", "SWE", "Needs Review", False)
    assert abs(conf - 0.55) < 0.001


def test_compute_confidence_all_unknown():
    assert compute_confidence("Unknown", "Unknown", "Needs Review", False) == 0.0


def test_compute_confidence_capped_at_one():
    conf = compute_confidence("Google", "SWE", "Offer", True)
    assert conf <= 1.0


def _clear_cache():
    from classifier.ats_intelligence import _template_cache
    _template_cache.clear()


@pytest.mark.asyncio
async def test_no_ai_sends_nothing_to_a_provider(db, mock_user, fake_ai):
    _clear_cache()
    server = fake_ai()
    from ai.service import set_active
    set_active(None)
    emails = [{
        "id": "email1",
        "thread_id": None,
        "subject": "Interview scheduled for Software Engineer",
        "sender": "hr@company.com",
        "body": "We have an opening for the Software Engineer position.",
    }]
    await classify_emails_batch(emails, {}, db=db, user=mock_user)
    assert server.requests == []


@pytest.mark.asyncio
async def test_no_ai_returns_result_for_classifiable_email(ai_off):
    _clear_cache()
    emails = [{
        "id": "email1",
        "thread_id": None,
        "subject": "Interview scheduled for Software Engineer",
        "sender": "hr@company.com",
        "body": "We have an opening for the Software Engineer position.",
    }]
    result = await classify_emails_batch(emails, {})
    assert "email1" in result


@pytest.mark.asyncio
async def test_no_ai_skips_email_with_empty_id(ai_off):
    _clear_cache()
    emails = [{"id": "", "thread_id": None, "subject": "Test", "sender": "x@x.com", "body": ""}]
    result = await classify_emails_batch(emails, {})
    assert result == {}


def _context_app(company="Google", role="Software Engineer"):
    app = MagicMock()
    app.company = company
    app.role = role
    app.status = "Applied"
    app.raw_metadata = {"history": []}
    return app


@pytest.mark.asyncio
async def test_settled_thread_email_is_not_sent_to_ai(db, mock_user, ai_on):
    """A thread email with known company and role and a clear status stays with the rules."""
    _clear_cache()
    emails = [{
        "id": "email1",
        "thread_id": "thread1",
        "subject": "Interview scheduled – Software Engineer",
        "sender": "hr@google.com",
        "body": "We'd like to schedule an interview.",
    }]
    result = await classify_emails_batch(emails, {"thread1": _context_app()}, db=db, user=mock_user)
    assert ai_on.requests == []
    assert result["email1"]["company"] == "Google"
    assert result["email1"]["role"] == "Software Engineer"
    assert result["email1"]["source"] == "deterministic"


@pytest.mark.asyncio
async def test_thread_status_comes_from_email_content(db, mock_user, ai_on):
    _clear_cache()
    emails = [{
        "id": "email1",
        "thread_id": "thread1",
        "subject": "Unfortunately we are not moving forward",
        "sender": "hr@google.com",
        "body": "",
    }]
    result = await classify_emails_batch(emails, {"thread1": _context_app()}, db=db, user=mock_user)
    assert result["email1"]["status"] == "Rejected"


@pytest.mark.asyncio
async def test_unknown_company_in_thread_is_sent_to_ai(db, mock_user, ai_on):
    _clear_cache()
    emails = [{
        "id": "email1",
        "thread_id": "thread1",
        "subject": "Interview scheduled",
        "sender": "recruiter@gmail.com",
        "body": "We'd like to schedule an interview.",
    }]
    await classify_emails_batch(emails, {"thread1": _context_app(company="Unknown")}, db=db, user=mock_user)
    assert len(ai_on.completions) == 1


def test_identical_generic_emails_from_two_companies_are_not_shared_through_the_cache():
    from classifier.ats_intelligence import _template_cache
    from classifier.batch_service import classify_with_rules

    _template_cache.clear()
    generic = dict(subject="Application received", body="Thank you for applying for the Data Analyst position.")
    emails = [
        {"id": "a", "sender": "Brightwave Careers <jobs@brightwave.example>", **generic},
        {"id": "b", "sender": "Northwind Labs Careers <jobs@northwindlabs.example>", **generic},
    ]
    first = classify_with_rules(emails, {})
    again = classify_with_rules(emails, {})
    assert (first["a"]["company"], first["b"]["company"]) == ("Brightwave", "Northwind Labs")
    assert (again["a"]["company"], again["b"]["company"]) == ("Brightwave", "Northwind Labs")
    _template_cache.clear()
