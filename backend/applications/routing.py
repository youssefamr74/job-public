"""Where an email goes before normal classification: calendar invites, account mail, recruiter outreach.

These need to know what the user already tracks, so they run in the sync instead of the context-free filter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from classifier.ats_intelligence import classify_email_deterministic, extract_company, extract_role
from classifier.categories import (
    has_interview_word,
    is_account_mail,
    is_calendar_invite,
    is_outreach,
    looks_like_recruiter,
    parse_invite_date,
)
from classifier.text import clean_text
from constants.job_statuses import STATUS_PRIORITY
from applications.service import NEEDS_REVIEW_BELOW

INTERVIEW_CONFIDENCE = 0.9
# An invite never overrides a clear outcome in the same email.
KEEP_STATUSES = {"Rejected", "Offer"}
# "Thanks for applying ... an exciting opportunity at X" is a confirmation, not outreach.
_APPLICATION_SUBJECT = re.compile(r"\b(?:your application|thank you for applying|thanks for applying|you applied)\b", re.IGNORECASE)

ACCOUNT = "account"
CLASSIFIED = "classified"
OPPORTUNITY = "opportunity"
OPPORTUNITY_NOTE = "opportunity_note"


@dataclass
class Route:
    kind: str
    # account: the tracked application to attach the email to, if any.
    app: Any = None
    # classified: the result to use instead of classifying the email again.
    result: Optional[dict] = None
    # opportunity: what the email offers.
    company: Optional[str] = None
    role: Optional[str] = None


def tracked_app(sender: str, subject: str, extra: str, existing_by_company: dict):
    """The application of a company we already track that this email is about, if any."""
    company = extract_company(sender, subject, extra)[0]
    candidates = existing_by_company.get(company.lower()) if company else None
    if not candidates:
        haystack = f"{sender} {subject} {extra}".lower()
        for key, apps in existing_by_company.items():
            if len(key) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack):
                candidates = apps
                break
    return max(candidates, key=lambda a: STATUS_PRIORITY.get(a.status, -1)) if candidates else None


def _classify(email: dict, app) -> dict:
    return classify_email_deterministic(
        sender=email.get("sender") or "", subject=email.get("subject") or "",
        body=(email.get("body") or "")[:3000],
        thread_company=app.company if app else None, thread_role=app.role if app else None,
    )


def _confident(result: dict) -> bool:
    return result.get("status") != "Needs Review" and float(result.get("status_confidence", 0.0)) >= NEEDS_REVIEW_BELOW


def _interview_result(email: dict, app, subject: str, body: str, reason: str, invite: bool) -> dict:
    result = _classify(email, app)
    if result.get("status") not in KEEP_STATUSES:
        result.update(status="Interview", status_confidence=INTERVIEW_CONFIDENCE, status_found=True,
                      reason=reason, source="deterministic")
    if app is not None:
        if result.get("company") in (None, "Unknown"):
            result["company"] = app.company
        if result.get("role") in (None, "Unknown") and app.role not in (None, "Unknown"):
            result["role"] = app.role
    if invite:
        result["interview_date"] = parse_invite_date(subject, body) or result.get("interview_date")
        result["keep_without_company"] = True
    return result


def route_email(email: dict, existing_by_thread: dict, existing_by_company: dict, open_opportunities: dict) -> Optional[Route]:
    sender = email.get("sender") or ""
    subject = clean_text(email.get("subject") or "")
    body = clean_text(email.get("body") or "")
    thread_id = email.get("thread_id")
    thread_app = existing_by_thread.get(thread_id) if thread_id else None

    if is_account_mail(subject):
        return Route(ACCOUNT, app=thread_app or tracked_app(sender, subject, "", existing_by_company))

    tracked = thread_app or tracked_app(sender, subject, body[:500], existing_by_company)
    invite = is_calendar_invite(subject, body)
    if (invite and (tracked or looks_like_recruiter(sender, subject, body))) or (has_interview_word(subject) and tracked):
        reason = "calendar invite" if invite else "interview mentioned in the subject"
        return Route(CLASSIFIED, result=_interview_result(email, tracked, subject, body, reason, invite))

    if thread_app is None and is_outreach(sender, subject) and not _APPLICATION_SUBJECT.search(subject):
        company = extract_company(sender, subject, body)[0]
        role = extract_role(re.sub(r"^\s*message replied:\s*", "", subject, flags=re.IGNORECASE), body)[0]
        if thread_id and thread_id in open_opportunities:
            # A later email in an outreach thread updates its opportunity; it counts as applying only when it says so.
            result = _classify(email, None)
            if _confident(result):
                return Route(CLASSIFIED, result=result)
            return Route(OPPORTUNITY_NOTE, company=company, role=role)
        return Route(OPPORTUNITY, company=company, role=role)
    return None
