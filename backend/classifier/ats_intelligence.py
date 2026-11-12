"""Rule-based classification: company, role and status from one email, without AI."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterator, Optional

from classifier.normalization import (
    display_role,
    extract_company_from_sender,
    is_platform_domain,
    is_platform_name,
    normalize_company,
)
from classifier.heuristics import is_linkedin_conversation
from classifier.linkedin import parse_linkedin
from classifier.pracuj import parse_pracuj
from classifier.text import clean_text
from constants.app_config import (
    CLASSIFIER_VERSION,
    COMPANY_SCORE_ATS,
    COMPANY_SCORE_DISPLAY_NAME,
    COMPANY_SCORE_SENDER_DOMAIN,
    COMPANY_SCORE_THREAD,
    COMPLETENESS_BONUS,
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    ROLE_SCORE_SUBJECT,
    ROLE_SCORE_THREAD,
    STATUS_SCORE_BODY,
    STATUS_SCORE_SUBJECT,
)
from constants.email_signals import (
    _ROLE_NOISE_PREFIXES,
    APPLICATION_SUBJECT_WORDS,
    ASSESSMENT_PATTERNS,
    ATS_SUBDOMAIN_RULES,
    COMMON_FIRST_NAMES,
    CONDITIONAL_WORDS,
    CONFIRMATION_PATTERNS,
    DISPLAY_NAME_NOISE,
    FEEDBACK_PATTERNS,
    INTERVIEW_PATTERNS,
    OFFER_PATTERNS,
    PROCESS_END_PATTERNS,
    ROLE_NOISE,
    ROLE_PATTERNS,
    STRONG_REJECTION_PATTERNS,
    VALID_ROLE_KEYWORDS,
    WEAK_REJECTION_PATTERNS,
)

# The tests import HIGH_CONFIDENCE and MEDIUM_CONFIDENCE from this module.
__all__ = [
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "looks_like_role",
    "extract_display_name_company",
    "extract_company",
    "extract_role",
    "extract_role_from_subject",
    "extract_role_from_body",
    "classify_status",
    "classify_email_deterministic",
    "get_template_hash",
    "get_cached_result",
    "cache_result",
]

# How sure each kind of status evidence is. Below 0.65 the sync shows Needs Review.
STATUS_CONFIDENCE = {
    "strong_rejection": 0.90,
    "offer": 0.85,
    "assessment": 0.85,
    "interview": 0.80,
    "confirmation": 0.85,
    "process_end_rejection": 0.75,
    "weak_rejection": 0.70,
}

_WORD = r"[A-Z0-9ÀÁÂÄÅĄĆČĘÉŁŃÓÖŚŠŹŻŽ][\w&'\-]*(?:\.[\w&'\-]+)*"
_COMPANY_WORDS = rf"{_WORD}(?:\s+(?:&\s+)?{_WORD}){{0,4}}"
SUBJECT_COMPANY_PATTERNS = [
    re.compile(r"^\s*\[([^\]]{2,60})\]"),
    re.compile(rf"(?i:\b(?:at|with)\s+)({_COMPANY_WORDS})"),
    re.compile(rf"(?i:\b(?:applying|application|applied|apply)\s+to\s+(?:the\s+)?)({_COMPANY_WORDS})"),
    re.compile(r"^\s*([^\-–—:|\[\]]{2,40}?)\s*(?:\s[-–—|]\s|:\s)"),
]
BODY_COMPANY_PATTERN = re.compile(
    rf"(?i:\b(?:interest in|joining|careers? at|position at|role at|here at|opportunity at|team at|"
    rf"job at|work at|working at|applying to|application to|applied to|apply to|w firmie)\s+(?:the\s+)?)"
    rf"({_COMPANY_WORDS})"
)
_COMPANY_STOPWORDS = {
    "application", "applications", "interview", "thank", "thanks", "update", "status",
    "candidate", "invitation", "offer", "assessment", "reminder", "next", "steps", "your",
    "you", "re", "fwd", "fw", "confirmation", "received", "position", "role", "job", "jobs",
    "we", "our", "us", "i", "dear", "hello", "hi", "aplikacja", "rekrutacja", "test",
    "challenge", "action", "required", "important", "new", "message", "call", "phone",
    "meeting", "feedback", "chat",
}
_COMPANY_TRAILING_NOISE = {"team", "careers", "career", "recruiting", "recruitment", "hiring", "talent"}
# "Data Engineer - Brightwave." : a role, a dash, then the company.
_ROLE_DASH_COMPANY = re.compile(r"^\s*(?P<role>.+?)\s+[-–—|]\s+(?P<company>[^\-–—|]{2,40}?)[.!]?\s*$")
# A company name can contain "Software" or "Data"; it just doesn't end in a job title.
_ROLE_NOUNS = {
    "engineer", "developer", "analyst", "manager", "specialist", "scientist", "designer", "architect",
    "intern", "consultant", "administrator", "technician", "officer", "director", "coordinator",
    "tester", "programmer", "lead", "recruiter", "assistant", "trainee", "student", "programista",
    "inżynier", "analityk", "specjalista", "stażysta", "praktykant",
}

_ROLE_REGEXES = [re.compile(p, re.IGNORECASE) for p in ROLE_PATTERNS]
_ROLE_CUT = re.compile(
    r"\s+(?:at|with|in|for|has|have|was|is|are|we|our|here|within|on|from|which|that|who|"
    r"located|based|location|and (?:we|our|you))\b|\s[-–—|]\s|[,;!?]|\.(?:\s|$)",
    re.IGNORECASE,
)

_STRONG_REJECTION = [re.compile(p) for p in STRONG_REJECTION_PATTERNS]
_WEAK_REJECTION = [re.compile(p) for p in WEAK_REJECTION_PATTERNS]
_CONFIRMATION = [re.compile(p) for p in CONFIRMATION_PATTERNS]
_PROCESS_END = [re.compile(p) for p in PROCESS_END_PATTERNS]
_OFFER = [re.compile(p) for p in OFFER_PATTERNS]
_INTERVIEW = [re.compile(p) for p in INTERVIEW_PATTERNS]
_ASSESSMENT = [re.compile(p) for p in ASSESSMENT_PATTERNS]
_FEEDBACK = [re.compile(p) for p in FEEDBACK_PATTERNS]


def looks_like_role(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in VALID_ROLE_KEYWORDS)


def _looks_like_person_name(name: str) -> bool:
    parts = name.lower().split()
    return len(parts) == 2 and parts[0] in COMMON_FIRST_NAMES


_PERSON_WORD = re.compile(r"^[A-ZÀ-ÖØ-ÞĄĆĘŁŃÓŚŹŻ][a-zà-öø-ÿąćęłńóśźż'’.\-]+$")
_COMPANY_WORDS_IN_NAMES = {
    "inc", "ltd", "llc", "gmbh", "corp", "co", "group", "tech", "technologies", "technology", "software",
    "systems", "labs", "lab", "solutions", "consulting", "services", "analytics", "digital", "data", "global",
    "international", "partners", "capital", "bank", "media", "studio", "studios", "works", "industries",
    "holdings", "networks", "cloud", "cyber", "security", "health", "energy", "motors", "foods", "pharma",
    "soft", "it", "ai", "dev", "hub", "team", "careers", "recruiting", "recruitment", "talent", "hiring", "hr",
    "jobs", "agency", "staffing", "outsourcing", "logistics", "finance", "financial", "insurance", "university",
    "academy", "school", "institute", "foundation", "company", "enterprises", "ventures", "robotics", "systems",
    "interactive", "games", "mobile", "telecom", "airlines", "bros", "brothers",
}


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _display_is_person(display: str, domain: str) -> bool:
    """A display name that is a person, not a company: a known first name, or two capitalised words
    without company words. A name the sender's domain spells out ("Bending Spoons") is the company."""
    words = (display or "").replace('"', " ").split()
    if not 2 <= len(words) <= 3 or not all(_PERSON_WORD.match(w) for w in words):
        return False
    key = _alnum("".join(words))
    if key and key in _alnum(domain):
        return False
    if words[0].lower() in COMMON_FIRST_NAMES and len(words) == 2:
        return True
    lowered = {w.lower().strip(".") for w in words}
    return not (lowered & _COMPANY_WORDS_IN_NAMES or lowered & DISPLAY_NAME_NOISE)


def _parse_email_address(sender: str) -> tuple[str, str]:
    """Returns (display_name, email_address) from 'Display Name <email>' or bare email."""
    sender = sender or ""
    if "<" in sender:
        display = sender[:sender.index("<")].strip().strip('"\'')
        email = sender[sender.index("<") + 1:].split(">")[0].strip().lower()
    else:
        display = ""
        email = sender.strip().lower()
    return display, email


def _valid_company(candidate: str) -> Optional[str]:
    words = candidate.strip(" .,:;!?-–—\"'()[]").split()
    while words and words[-1].lower() in _COMPANY_TRAILING_NOISE:
        words.pop()
    if words and words[0].lower() == "the":
        words = words[1:]
    name = " ".join(words)
    if not (2 <= len(name) <= 60) or len(words) > 6:
        return None
    lowered = {w.lower().strip(".,:;!?'\"") for w in words}
    if lowered & _COMPANY_STOPWORDS or is_platform_name(name):
        return None
    if {w.lower().strip(".,()") for w in words} & _ROLE_NOUNS or _looks_like_person_name(name):
        return None
    company = normalize_company(name)
    return None if company == "Unknown" else company


def _company_from_subject(subject: str) -> Optional[str]:
    bracket = SUBJECT_COMPANY_PATTERNS[0].search(subject)
    if bracket:
        company = _valid_company(bracket.group(1))
        if company:
            return company
    role_dash = _ROLE_DASH_COMPANY.search(subject)
    if role_dash and looks_like_role(role_dash.group("role")) and not re.search(r"[()/@\[\]]", role_dash.group("company")):
        company = _valid_company(role_dash.group("company"))
        if company:
            return company
    for pattern in SUBJECT_COMPANY_PATTERNS[1:]:
        match = pattern.search(subject)
        if match:
            company = _valid_company(match.group(1))
            if company:
                return company
    return None


def _company_from_body(body: str) -> Optional[str]:
    for match in BODY_COMPANY_PATTERN.finditer(body[:1500]):
        company = _valid_company(match.group(1))
        if company:
            return company
    return None


def _company_from_ats_address(email: str, domain: str) -> Optional[str]:
    """Workday sends from <company>@myworkday.com; some ATSs use <company>.<ats domain>."""
    local = email.split("@", 1)[0]
    if domain == "myworkday.com" or domain.endswith(".myworkday.com"):
        name = re.sub(r"[._\-]+", " ", local).strip()
        if name and name.lower() not in DISPLAY_NAME_NOISE and not is_platform_name(name):
            return name.upper() if len(name) <= 4 else name.title()
    for ats_domain in ATS_SUBDOMAIN_RULES:
        if domain.endswith("." + ats_domain):
            prefix = domain[: -len(ats_domain) - 1]
            for part in reversed(prefix.split(".")):
                if not part or len(part) < 2 or part in DISPLAY_NAME_NOISE:
                    continue
                if re.fullmatch(r"(?:wd\d*|us|eu|mail|email|my)", part):
                    continue
                company = normalize_company(part.replace("-", " ").title())
                if company != "Unknown":
                    return company
    return None


def extract_display_name_company(sender: str) -> Optional[str]:
    """Company from the sender display name, e.g. "Brightwave Hiring Team" → "Brightwave"."""
    display, _ = _parse_email_address(sender)
    if not display:
        return None
    stripped = normalize_company(display)
    if stripped != "Unknown":
        display = stripped

    words = re.split(r"[\s,_]+|\s[-–|]\s", display)
    meaningful = [
        w for w in words
        if w and len(w) > 1 and w.lower().strip(".:") not in DISPLAY_NAME_NOISE and not is_platform_name(w)
    ]
    result_parts: list[str] = []
    for word in meaningful:
        if len(word) <= 2 and word.isupper():
            break
        result_parts.append(word)
        if len(result_parts) >= 3:
            break
    if not result_parts:
        return None
    name = " ".join(result_parts)
    if _looks_like_person_name(name) or is_platform_name(name) or _display_is_person(
        _parse_email_address(sender)[0], _sender_domain(sender)
    ):
        return None
    company = normalize_company(name)
    return None if company == "Unknown" else company


def _sender_domain(sender: str) -> str:
    _, email = _parse_email_address(sender)
    return email.split("@", 1)[1] if "@" in email else ""


def extract_company(sender: str, subject: str, body: str) -> tuple[Optional[str], float, Optional[str]]:
    """(company, score, source). Platform senders are never taken as the company themselves.

    source is "platform", "display", "text" or "domain"; a domain-only guess is the weakest."""
    _, email = _parse_email_address(sender)
    domain = _sender_domain(sender)

    if is_platform_domain(domain):
        for find, score, source in (
            (lambda: _company_from_subject(subject), COMPANY_SCORE_ATS, "text"),
            (lambda: _company_from_body(body), COMPANY_SCORE_ATS, "text"),
            (lambda: _company_from_ats_address(email, domain), COMPANY_SCORE_ATS, "platform"),
            (lambda: extract_display_name_company(sender), COMPANY_SCORE_DISPLAY_NAME, "display"),
        ):
            company = find()
            if company:
                return company, score, source
        return None, 0.0, None

    def from_domain() -> Optional[str]:
        name = extract_company_from_sender(sender)
        company = normalize_company(name) if name else "Unknown"
        return None if company == "Unknown" else company

    steps = [
        (lambda: extract_display_name_company(sender), COMPANY_SCORE_DISPLAY_NAME, "display"),
        (lambda: _company_from_subject(subject), COMPANY_SCORE_DISPLAY_NAME, "text"),
        (lambda: _company_from_body(body), COMPANY_SCORE_DISPLAY_NAME, "text"),
        (from_domain, COMPANY_SCORE_SENDER_DOMAIN, "domain"),
    ]
    # A person writing from the company's own domain: the domain names the company.
    if _display_is_person(_parse_email_address(sender)[0], domain):
        steps.insert(0, steps.pop())
    for find, score, source in steps:
        company = find()
        if company:
            return company, score, source
    return None, 0.0, None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _clean_role(raw: str) -> Optional[str]:
    candidate = _ROLE_CUT.split(raw, maxsplit=1)[0]
    role = display_role(candidate)
    if role == "Unknown" or not (3 <= len(role) <= 60) or len(role.split()) > 8:
        return None
    lowered = role.lower()
    if lowered in ROLE_NOISE or any(lowered.startswith(p) for p in _ROLE_NOISE_PREFIXES):
        return None
    return role if looks_like_role(role) else None


def _role_candidates(text: str) -> Iterator[str]:
    for sentence in _sentences(text)[:20]:
        for regex in _ROLE_REGEXES:
            match = regex.search(sentence)
            if match:
                yield match.group("role")


def _find_role(text: str) -> Optional[str]:
    for raw in _role_candidates(text):
        role = _clean_role(raw)
        if role:
            return role
    return None


def extract_role(subject: str, body: str) -> tuple[Optional[str], float]:
    role = _find_role(subject) or _find_role((body or "")[:2000])
    return (role, ROLE_SCORE_SUBJECT) if role else (None, 0.0)


def extract_role_from_subject(subject: str) -> str:
    return _find_role(clean_text(subject or "")) or "Unknown"


def extract_role_from_body(body: str) -> str:
    return _find_role(clean_text(body or "")[:2000]) or "Unknown"


@dataclass
class StatusResult:
    status: Optional[str]
    confidence: float
    reason: str
    # True when the email is clearly about the application but the outcome isn't.
    unclear: bool = False
    # The email says nothing about the application, so an existing status must not change.
    keep_status: bool = False


# "Congratulations, you are enrolled in our training programme" is about a course, not a job.
_ENROLLMENT = re.compile(
    r"congratulat\w*.{0,200}?\b(?:enrol\w*|regist\w*|signed up|accepted into|admitted)\b.{0,200}?"
    r"\b(?:training|program(?:me)?|course|bootcamp|workshop|academy|class(?:es)?|cohort)\b|"
    r"\b(?:enrol\w*|regist\w*)\b.{0,100}?\b(?:training|course|bootcamp)\b.{0,100}?congratulat\w*",
    re.IGNORECASE | re.DOTALL,
)


def _matches(patterns: list[re.Pattern], sentences: list[str]) -> bool:
    return any(p.search(s) for s in sentences for p in patterns)


def classify_status(subject: str, body: str) -> StatusResult:
    if _ENROLLMENT.search(f"{subject or ''}. {(body or '')[:1500]}"):
        return StatusResult(None, 0.0, "course enrollment, not an application outcome", unclear=True, keep_status=True)
    # Sentences about what might happen ("if we decide not to move forward") are ignored.
    sentences = [
        s.lower() for s in [subject or ""] + _sentences((body or "")[:3000])
        if s and not CONDITIONAL_WORDS.search(s)
    ]
    if _matches(_STRONG_REJECTION, sentences):
        return StatusResult("Rejected", STATUS_CONFIDENCE["strong_rejection"], "clear rejection")
    if _matches(_FEEDBACK, sentences):
        return StatusResult(None, 0.0, "feedback request, not an outcome", unclear=True)
    if _matches(_OFFER, sentences):
        return StatusResult("Offer", STATUS_CONFIDENCE["offer"], "offer")
    if _matches(_ASSESSMENT, sentences):
        return StatusResult("Assessment", STATUS_CONFIDENCE["assessment"], "assessment invitation")
    if _matches(_INTERVIEW, sentences):
        return StatusResult("Interview", STATUS_CONFIDENCE["interview"], "interview invitation")
    weak_rejection = _matches(_WEAK_REJECTION, sentences)
    if _matches(_PROCESS_END, sentences):
        if weak_rejection:
            return StatusResult("Rejected", STATUS_CONFIDENCE["process_end_rejection"], "process ended with a rejection")
        return StatusResult(None, 0.0, "process ended without a clear outcome", unclear=True)
    if _matches(_CONFIRMATION, sentences):
        return StatusResult("Applied", STATUS_CONFIDENCE["confirmation"], "application confirmation")
    if weak_rejection:
        return StatusResult("Rejected", STATUS_CONFIDENCE["weak_rejection"], "likely rejection")
    return StatusResult(None, 0.0, "no status found")


def _status_score(result: StatusResult) -> float:
    if not result.status:
        return 0.0
    return STATUS_SCORE_SUBJECT if result.confidence >= 0.8 else STATUS_SCORE_BODY


def classify_email_deterministic(
    sender: str,
    subject: str,
    body: str,
    thread_company: Optional[str] = None,
    thread_role: Optional[str] = None,
) -> dict:
    """Always returns a result. status_confidence alone decides Needs Review; the overall
    confidence only decides whether AI should take a look."""
    subject = clean_text(subject or "")
    body = clean_text(body or "")

    board = parse_linkedin(sender, subject, body) or parse_pracuj(sender, subject, body)
    if board is not None:
        return _board_result(board, body)

    usable_thread_company = (
        thread_company and thread_company != "Unknown" and not is_platform_name(thread_company)
    )
    known_company = thread_company if usable_thread_company else None
    known_role = thread_role if thread_role and thread_role != "Unknown" else None

    if known_company:
        company, company_score, company_source = normalize_company(known_company), COMPANY_SCORE_THREAD, "thread"
    else:
        company, company_score, company_source = extract_company(sender, subject, body)

    if known_role:
        role, role_score = display_role(known_role), ROLE_SCORE_THREAD
    else:
        role, role_score = extract_role(re.sub(r"^\s*message replied:\s*", "", subject, flags=re.IGNORECASE), body)

    status = classify_status(subject, body)

    conversation = is_linkedin_conversation(sender, subject)
    if conversation:
        company, company_source = None, None

    confidence = company_score + role_score + _status_score(status)
    if company and role and status.status:
        confidence += COMPLETENESS_BONUS

    return {
        "company":           company or "Unknown",
        "role":              role if role and role != "Unknown" else "Unknown",
        "status":            status.status or "Needs Review",
        "confidence":        min(confidence, 1.0),
        "status_confidence": status.confidence,
        "status_found":      bool(status.status) or status.unclear or conversation,
        "keep_status":       status.keep_status,
        # A recruiter writing on LinkedIn is worth a look even before we know the company.
        "keep_without_company": conversation,
        "application_subject": bool(APPLICATION_SUBJECT_WORDS.search(subject)),
        "company_source":    company_source,
        "platform_sender":   is_platform_domain(_sender_domain(sender)),
        "reason":            ("Thread memory + " if known_company and known_role else "") + status.reason,
        "interview_date":    None,
        "job_id":            None,
        "location":          None,
        "source":            "deterministic",
    }


def _board_result(parsed, body: str) -> dict:
    """Result for a job board's own fixed-format email (LinkedIn, Pracuj.pl)."""
    if parsed.status:
        status = StatusResult(parsed.status, parsed.status_confidence, parsed.reason)
    else:
        status = classify_status("", body)
    confidence = (COMPANY_SCORE_ATS if parsed.company else 0.0) + (ROLE_SCORE_SUBJECT if parsed.role else 0.0)
    confidence += _status_score(status)
    if parsed.company and parsed.role and status.status:
        confidence += COMPLETENESS_BONUS
    return {
        "company":           parsed.company or "Unknown",
        "role":              parsed.role or "Unknown",
        "status":            status.status or "Needs Review",
        "confidence":        min(confidence, 1.0),
        "status_confidence": status.confidence,
        "status_found":      True,
        "keep_without_company": False,
        "company_source":    "text" if parsed.company else None,
        "platform_sender":   True,
        "reason":            f"{parsed.reason}: {status.reason}" if not parsed.status else parsed.reason,
        "action_needed":     getattr(parsed, "action_needed", False),
        "interview_date":    None,
        "job_id":            None,
        "location":          None,
        "source":            "deterministic",
    }


_template_cache: dict[str, Optional[dict]] = {}


def get_template_hash(subject: str, body: str, sender: str = "", thread_company: str = "", thread_role: str = "") -> str:
    """The company and role come from the sender and the thread, so they are part of the key."""
    normalized = re.sub(
        r"\s+", " ",
        f"{CLASSIFIER_VERSION} {_parse_email_address(sender)[1]} {thread_company or ''} {thread_role or ''} "
        f"{subject} {body[:200]}".lower()
    ).strip()
    return hashlib.sha1(normalized.encode()).hexdigest()


def get_cached_result(subject: str, body: str, sender: str = "", thread_company: str = "", thread_role: str = "") -> Optional[dict]:
    return _template_cache.get(get_template_hash(subject, body, sender, thread_company, thread_role))


def cache_result(
    subject: str, body: str, result: Optional[dict], sender: str = "", thread_company: str = "", thread_role: str = "",
) -> None:
    _template_cache[get_template_hash(subject, body, sender, thread_company, thread_role)] = result
