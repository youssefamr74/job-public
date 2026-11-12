"""LinkedIn sends application emails in a fixed format, so they're parsed directly."""

import re
from dataclasses import dataclass
from typing import Optional

from classifier.normalization import display_role, normalize_company

_LINKEDIN_SENDER = re.compile(r"@(?:[\w-]+\.)*linkedin\.com\b", re.IGNORECASE)
# "<Name>, your application was sent to <Company>" (Easy Apply)
_EASY_APPLY = re.compile(r"your application was sent to\s+(?P<company>.+?)\s*[.!]?\s*$", re.IGNORECASE)
# "Your application to <Role> at <Company>" (status update)
_STATUS_UPDATE = re.compile(r"your application to\s+(?P<role>.+)\s+at\s+(?P<company>.+?)\s*[.!]?\s*$", re.IGNORECASE)

EASY_APPLY_CONFIDENCE = 0.9


@dataclass
class LinkedInParse:
    company: Optional[str]
    role: Optional[str]
    # None means the status has to come from the body.
    status: Optional[str]
    status_confidence: float
    reason: str


def _role(text: str) -> Optional[str]:
    role = display_role(text)
    return None if role == "Unknown" else role


def _company(text: str) -> Optional[str]:
    company = normalize_company(text)
    return None if company == "Unknown" else company


def parse_linkedin(sender: str, subject: str, body: str) -> Optional[LinkedInParse]:
    if not _LINKEDIN_SENDER.search(sender or ""):
        return None

    easy_apply = _EASY_APPLY.search(subject or "")
    if easy_apply:
        raw_company = easy_apply.group("company")
        # The body repeats the company around the role: "sent to <Company> <Role> <Company> <Location>".
        between = re.search(
            rf"sent to\s+{re.escape(raw_company)}\s+(?P<role>.+?)\s+{re.escape(raw_company)}\b",
            body or "", re.IGNORECASE,
        )
        return LinkedInParse(
            company=_company(raw_company),
            role=_role(between.group("role")) if between else None,
            status="Applied",
            status_confidence=EASY_APPLY_CONFIDENCE,
            reason="LinkedIn Easy Apply confirmation",
        )

    update = _STATUS_UPDATE.search(subject or "")
    if update:
        return LinkedInParse(
            company=_company(update.group("company")),
            role=_role(update.group("role")),
            status=None,
            status_confidence=0.0,
            reason="LinkedIn application update",
        )
    return None
