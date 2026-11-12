"""Generic email categories that need special handling: calendar invites, account mail,
surveys, recruiter outreach and marketing. Pure text rules; nothing here touches the database."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

SURVEY = re.compile(
    r"share your (?:experience|opinion|feedback|thoughts)|feedback survey|\bsurvey\b|"
    r"how (?:was|did we do with) your (?:application )?experience|rate your (?:application )?experience",
    re.IGNORECASE,
)

# Subject only: rejection emails often mention GDPR in their body footer.
ACCOUNT = re.compile(
    r"verify your (?:candidate |email |e-mail )?(?:account|address)|"
    r"(?:candidate |career |careers )?account (?:creation|created|activation|confirmation)|"
    r"(?:you(?:'ve| have) )?created an account|\baccount (?:has been )?created\b|"
    r"\bpassword\b|one[- ]time (?:code|password)|\botp\b|verification code|"
    r"\bgdpr\b|data retention|keep your (?:information|data)|data protection|"
    r"privacy (?:notice|policy|notification|and compliance)|candidate (?:account|profile|portal)",
    re.IGNORECASE,
)

MARKETING = re.compile(
    r"\bexplore \d+ (?:new )?(?:roles|jobs|positions)|you(?:'|’)?d be a top applicant|top applicant|"
    r"dream job might be|just a click away|career (?:newsletter|tips|advice)|"
    r"jobs? (?:picked|selected|curated) for you|\bnew (?:roles|jobs) (?:for you|waiting)",
    re.IGNORECASE,
)
MARKETING_SENDER = re.compile(r"flexjobs", re.IGNORECASE)

OUTREACH = re.compile(
    r"\bopportunity at\b|\bjob opportunity\b|\bcontract opportunity\b|\bexciting opportunity\b|"
    r"invitation (?:from .{1,60} )?to apply|\bhas referred you\b|\bhave been referred\b",
    re.IGNORECASE,
)
LINKEDIN_OUTREACH_SENDERS = {"hit-reply@linkedin.com", "inmail-hit-reply@linkedin.com"}

CALENDAR_SUBJECT = re.compile(
    r"^\s*(?:(?:fwd?|re):\s*)*(?:updated invitation(?: from an unknown sender)?|invitation(?: from an unknown sender)?|"
    r"accepted|tentatively accepted|new event)\s*:|"
    r"\s@\s+(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?\d{1,2}\s+[a-z]{3}|"
    r"\s@\s+(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?[a-z]{3,9}\.?\s+\d{1,2}",
    re.IGNORECASE,
)
CALENDAR_BODY = re.compile(r"text/calendar|\.ics\b|BEGIN:VCALENDAR|DTSTART|invitation\.ics|invite\.ics|"
                           r"view all guest info|join with google meet|reply for .{0,60}(?:yes|no|maybe)",
                           re.IGNORECASE)
INTERVIEW_WORD = re.compile(r"\binterview\b", re.IGNORECASE)
RECRUITER_WORDS = re.compile(r"recruit|talent|hiring|\bhr\b|human resources|people team|interview", re.IGNORECASE)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
TIMEZONES = {
    "utc": 0, "gmt": 0, "wet": 0, "west": 1, "cet": 1, "cest": 2, "eet": 2, "eest": 3, "msk": 3,
    "bst": 1, "ist": 5.5, "est": -5, "edt": -4, "cst": -6, "cdt": -5, "mst": -7, "mdt": -6, "pst": -8, "pdt": -7,
}
_MONTH = r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE_DMY = re.compile(rf"\b(?P<day>\d{{1,2}})\s+{_MONTH},?\s+(?P<year>\d{{4}})", re.IGNORECASE)
_DATE_MDY = re.compile(rf"\b{_MONTH}\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})", re.IGNORECASE)
_TIME = re.compile(r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)\b|\b(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)\b",
                   re.IGNORECASE)
_OFFSET = re.compile(r"\b(?:gmt|utc)\s*(?P<sign>[+-])\s*(?P<h>\d{1,2})(?::?(?P<m>\d{2}))?", re.IGNORECASE)
_ZONE_NAME = re.compile(r"\((?P<z>[A-Za-z]{3,4})\)|\b(?P<z2>CEST|CET|EEST|EET|BST|MSK|EST|EDT|CST|CDT|MST|MDT|PST|PDT|UTC|GMT)\b")
_ICS = re.compile(r"DTSTART(?:;[^:\r\n]*)?:(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})T(?P<h>\d{2})(?P<mi>\d{2})\d{2}(?P<z>Z?)")


def _address(sender: str) -> str:
    match = re.search(r"<([^>]+)>", sender or "")
    return (match.group(1) if match else (sender or "")).strip().lower()


def is_survey(subject: str) -> bool:
    return bool(SURVEY.search(subject or ""))


def is_account_mail(subject: str) -> bool:
    return bool(ACCOUNT.search(subject or ""))


def is_marketing(sender: str, subject: str) -> bool:
    return bool(MARKETING.search(subject or "") or MARKETING_SENDER.search(_address(sender).split("@")[-1]))


def is_outreach(sender: str, subject: str) -> bool:
    return bool(OUTREACH.search(subject or "")) or _address(sender) in LINKEDIN_OUTREACH_SENDERS


def is_calendar_invite(subject: str, body: str) -> bool:
    return bool(CALENDAR_SUBJECT.search(subject or "")) or bool(
        re.search(r"BEGIN:VCALENDAR|DTSTART|text/calendar|\.ics\b", body or "", re.IGNORECASE)
    )


def has_interview_word(subject: str) -> bool:
    return bool(INTERVIEW_WORD.search(subject or ""))


def looks_like_recruiter(sender: str, subject: str, body: str) -> bool:
    return bool(RECRUITER_WORDS.search(f"{sender} {subject} {(body or '')[:600]}"))


def _offset_hours(text: str) -> Optional[float]:
    match = _OFFSET.search(text)
    if match:
        hours = int(match.group("h")) + int(match.group("m") or 0) / 60
        return -hours if match.group("sign") == "-" else hours
    for match in _ZONE_NAME.finditer(text):
        name = (match.group("z") or match.group("z2") or "").lower()
        if name in TIMEZONES:
            return TIMEZONES[name]
    return None


def parse_invite_date(subject: str, body: str = "") -> Optional[datetime]:
    """The start time of a calendar invite, as UTC. Understands the Google and Outlook subject
    formats ("... @ Fri 9 Oct 2026 5:30pm - 5:45pm (GMT+3)") and an iCalendar DTSTART."""
    for text in (subject or "", body or ""):
        ics = _ICS.search(text)
        if ics:
            moment = datetime(int(ics["y"]), int(ics["mo"]), int(ics["d"]), int(ics["h"]), int(ics["mi"]))
            return moment.replace(tzinfo=timezone.utc)
        date = _DATE_DMY.search(text) or _DATE_MDY.search(text)
        if not date:
            continue
        rest = text[date.end():]
        time = _TIME.search(rest)
        hour, minute = 0, 0
        if time:
            if time["ap"]:
                hour = int(time["h"]) % 12 + (12 if time["ap"].lower() == "pm" else 0)
                minute = int(time["m"] or 0)
            else:
                hour, minute = int(time["h24"]), int(time["m24"])
        try:
            moment = datetime(int(date["year"]), MONTHS[date["mon"].lower()[:3]], int(date["day"]), hour, minute)
        except ValueError:
            continue
        offset = _offset_hours(rest[: time.end() + 60] if time else rest[:60]) or 0
        return (moment - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
    return None
