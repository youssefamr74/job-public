import re
from typing import Optional

from classifier.categories import is_marketing, is_survey
from classifier.normalization import domain_matches
from constants.email_signals import (
    ASSESSMENT_PLATFORMS,
    ATS_DOMAINS,
    BLOCKED_BODY_PATTERNS,
    BLOCKED_SENDER_DOMAINS,
    BLOCKED_SUBJECT_KEYWORDS,
    JOB_ALERT_SENDER_DOMAINS,
    JOB_ALERT_SUBJECT_PATTERNS,
    JOB_SIGNALS_BODY,
    JOB_SIGNALS_SUBJECT,
    LINKEDIN_CONVERSATION_SENDERS,
    LINKEDIN_JOB_ALERT_SENDERS,
    LINKEDIN_SOCIAL_SENDERS,
    SOCIAL_SENDER_DOMAINS,
    SOCIAL_SENDER_NAME_WORDS,
    SOCIAL_SUBJECT,
)

FILTERED_OUT = "filtered_out"
JOB_ALERT = "job_alert"
SOCIAL = "social"
SURVEY = "survey"

_JOB_ALERT_SUBJECT = [re.compile(p, re.IGNORECASE) for p in JOB_ALERT_SUBJECT_PATTERNS]


def _address(sender: str) -> str:
    match = re.search(r"<([^>]+)>", sender or "")
    return (match.group(1) if match else (sender or "")).strip().lower()


def is_from_ats(sender: str) -> bool:
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in ATS_DOMAINS)


def is_assessment_platform(sender: str) -> bool:
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in ASSESSMENT_PLATFORMS)


def is_linkedin_conversation(sender: str, subject: str) -> bool:
    return _address(sender) in LINKEDIN_CONVERSATION_SENDERS or (subject or "").lower().startswith("message replied")


def _has_job_signal(subject_lower: str, body_lower: str) -> bool:
    return (
        any(k in subject_lower for k in JOB_SIGNALS_SUBJECT)
        or any(k in body_lower for k in JOB_SIGNALS_BODY)
    )


def filter_reason(sender: str, subject: str, body: str) -> Optional[tuple[str, str]]:
    """(reason, detail) when the filter skips this email, None when it goes on to classification."""
    address = _address(sender)
    domain = address.split("@", 1)[1] if "@" in address else ""
    subject_lower = (subject or "").lower()
    body_lower = (body or "")[:1000].lower()

    if is_linkedin_conversation(sender, subject):
        return None
    if address in LINKEDIN_JOB_ALERT_SENDERS or domain_matches(domain, JOB_ALERT_SENDER_DOMAINS):
        return JOB_ALERT, f"job alert sender {domain}"
    alert = next((p.pattern for p in _JOB_ALERT_SUBJECT if p.search(subject or "")), None)
    if alert:
        return JOB_ALERT, alert
    if is_marketing(sender, subject):
        return JOB_ALERT, "marketing"
    if is_survey(subject):
        return SURVEY, "feedback survey"
    if address in LINKEDIN_SOCIAL_SENDERS or domain_matches(domain, SOCIAL_SENDER_DOMAINS):
        return SOCIAL, domain
    display_name = sender.split("<", 1)[0] if "<" in sender else ""
    if SOCIAL_SENDER_NAME_WORDS.search(display_name) or SOCIAL_SUBJECT.search(subject or ""):
        return SOCIAL, "community or newsletter"
    if is_from_ats(sender) or is_assessment_platform(sender):
        return None
    if any(p in sender.lower() for p in BLOCKED_SENDER_DOMAINS):
        return FILTERED_OUT, "blocked_sender"
    if any(k in subject_lower for k in BLOCKED_SUBJECT_KEYWORDS):
        return FILTERED_OUT, "blocked_subject"
    if any(k in body_lower for k in BLOCKED_BODY_PATTERNS):
        return FILTERED_OUT, "blocked_body"
    if not _has_job_signal(subject_lower, body_lower):
        return FILTERED_OUT, "no_job_signal"
    return None


def quick_filter(sender: str, subject: str, body: str) -> str:
    """Returns "skip" or "needs_ai_review". Only skip what is certainly not job-related:
    missing a real application is worse than classifying an extra email."""
    return "skip" if filter_reason(sender, subject, body) else "needs_ai_review"
