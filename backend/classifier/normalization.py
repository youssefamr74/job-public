from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Optional

from constants.email_signals import (
    COMPANY_OVERRIDES,
    COMPANY_SUFFIX_PATTERNS,
    GENDER_MARKER,
    INVALID_ROLES,
    KNOWN_PLATFORMS,
    LOCATION_SUFFIX,
    PLATFORM_DOMAINS,
    PLATFORM_NAMES,
    ROLE_CANONICAL,
    SENIORITY_PREFIX,
    SUBDOMAIN_PREFIXES_TO_SKIP,
)
from classifier.role_quality import not_a_role, tidy_role
from constants.places import is_place

ROLE_TYPES = {"internship", "intern", "praktyki", "staż", "working student", "werkstudent", "trainee", "graduate"}
ROLE_TRAILING_NOISE = {
    "update", "updates", "application", "applications", "status", "team", "opportunity",
    "position", "role", "vacancy", "job", "offer", "interview", "invitation", "confirmation",
    "received", "submitted", "reminder", "stanowisko",
}
# Parentheses holding a job id or reference, e.g. "(R-12345)" or "(Req #88)".
_ID_IN_PARENS = re.compile(r"\s*[\(\[][^)\]]*\d[^)\]]*[\)\]]")
_TRAILING_ID = re.compile(r"\s+(?:#|no\.?\s*|ref\.?\s*)?[A-Z]{0,4}-?\d{3,}\s*$", re.IGNORECASE)


def domain_matches(domain: str, candidates: set[str]) -> bool:
    domain = (domain or "").lower()
    return any(domain == d or domain.endswith("." + d) for d in candidates)


def is_platform_domain(domain: str) -> bool:
    return domain_matches(domain, PLATFORM_DOMAINS)


def is_platform_name(name: Optional[str]) -> bool:
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return key in PLATFORM_NAMES


def normalize_company(name: Optional[str]) -> str:
    if not name or not name.strip():
        return "Unknown"

    cleaned = name.strip().strip("\"'")

    if cleaned.lower() in COMPANY_OVERRIDES:
        return COMPANY_OVERRIDES[cleaned.lower()]
    if is_place(cleaned):
        return "Unknown"

    # Strip legal/regional suffixes iteratively until stable
    changed = True
    while changed:
        changed = False
        for pattern in COMPANY_SUFFIX_PATTERNS:
            reduced = pattern.sub("", cleaned).strip().rstrip(",")
            if reduced != cleaned and reduced:
                cleaned = reduced
                changed = True

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or is_platform_name(cleaned) or is_place(cleaned):
        return "Unknown"
    return cleaned


# Page text that leaks into a role: "<Company> Careers logo", "<Name> wants to work at ...".
_TEMPLATE_TEXT = re.compile(r"\b(?:(?:careers?|jobs?|hiring)\s+logo|wants\s+to\s+work)\b.*$", re.IGNORECASE)
_ROLE_HEAD_NOUNS = {
    "engineer", "developer", "analyst", "manager", "specialist", "scientist", "designer", "architect", "intern",
    "internship", "consultant", "administrator", "technician", "officer", "director", "coordinator", "tester",
    "programmer", "lead", "recruiter", "assistant", "trainee", "student", "programista", "inżynier", "analityk",
    "specjalista", "stażysta", "praktykant", "devops", "sre", "qa",
}


def _drop_template_text(role: str) -> str:
    """The text before the template phrase, minus the company or name stuck to the end of the role."""
    match = _TEMPLATE_TEXT.search(role)
    if not match:
        return role
    words = role[:match.start()].split()
    heads = [i for i, w in enumerate(words) if w.lower().strip(".,:;()") in _ROLE_HEAD_NOUNS]
    return " ".join(words[: heads[-1] + 1]) if heads else ""


def _strip_trailing_noise(role: str) -> str:
    words = role.split()
    while words and words[-1].lower().strip(".,:;") in ROLE_TRAILING_NOISE:
        words.pop()
    return " ".join(words)


def display_role(role: Optional[str]) -> str:
    """The role as shown to the user: seniority and type ("Junior", "Working student") are kept."""
    if not role or not role.strip():
        return "Unknown"

    cleaned = _drop_template_text(tidy_role(role.strip().strip("\"'“”")))
    if not cleaned or not_a_role(cleaned):
        return "Unknown"
    cleaned = GENDER_MARKER.sub("", cleaned)
    cleaned = _ID_IN_PARENS.sub("", cleaned)
    # "Internship – Full-stack Software Engineer": the type comes first, the role after the dash.
    typed = re.match(r"^(?P<kind>[^-–—|]+?)\s+[-–—|]\s+(?P<rest>.+)$", cleaned)
    if typed and typed.group("kind").strip().lower() in ROLE_TYPES:
        cleaned = f"{typed.group('rest')} ({typed.group('kind').strip()})"
    cleaned = LOCATION_SUFFIX.sub("", cleaned)
    cleaned = _TRAILING_ID.sub("", cleaned)
    cleaned = re.sub(r"^(?:the|a|an|our)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:position|role|job)\s+(?:as|of)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^job as\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:at|with|@)\s+\S.*$", "", cleaned)
    cleaned = re.sub(r"\s+and filling.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\([^)]*$", "", cleaned)
    cleaned = cleaned.rstrip(".,;:!?-–")
    cleaned = _strip_trailing_noise(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Unknown"

    prefix = ""
    core = cleaned
    match = SENIORITY_PREFIX.match(cleaned)
    if match:
        prefix, core = cleaned[:match.end()], cleaned[match.end():]
    if not core or core.lower() in INVALID_ROLES or cleaned.lower() in INVALID_ROLES:
        return "Unknown"
    if core.lower() in ROLE_CANONICAL:
        core = ROLE_CANONICAL[core.lower()]
    role = f"{prefix}{core}".strip()
    return "Unknown" if not_a_role(role) else role


def normalize_role(role: Optional[str]) -> str:
    """The role for matching and fingerprints: seniority, levels and numbering removed."""
    cleaned = display_role(role)
    if cleaned == "Unknown":
        return cleaned

    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = SENIORITY_PREFIX.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+\b(I{1,3}|IV|VI{0,3}|IX|[0-9]+)\b\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s*\([^)]*\)?\s*$", "", cleaned).strip()

    if cleaned.lower() in ROLE_CANONICAL:
        return ROLE_CANONICAL[cleaned.lower()]
    if not cleaned or cleaned.lower() in INVALID_ROLES:
        return "Unknown"
    return cleaned


_ACRONYMS = {"it", "hr", "ai", "qa", "bi", "ux", "ui", "uk", "us", "eu", "sap", "ibm", "bpo", "ict", "erp", "crm"}


def _title_company(name: str) -> str:
    """"acme it" -> "Acme IT"."""
    return " ".join(w.upper() if w in _ACRONYMS else w.title() for w in name.split())


def extract_company_from_sender(sender: str) -> Optional[str]:
    """Probable company from the sender domain; None for platform and personal mail domains."""
    try:
        if "<" in sender:
            email = sender.split("<")[1].split(">")[0].strip().lower()
        else:
            email = sender.strip().lower()

        domain = email.split("@")[-1]

        if domain_matches(domain, KNOWN_PLATFORMS):
            return None

        parts = domain.split(".")
        if len(parts) >= 3 and len(parts[-2]) <= 3:
            parts = parts[:-2]
        elif len(parts) >= 2:
            parts = parts[:-1]

        company_part = None
        for part in parts:
            if part not in SUBDOMAIN_PREFIXES_TO_SKIP and len(part) > 1:
                company_part = part
                break

        if not company_part:
            return None

        company_raw = company_part.replace("-", " ").replace("_", " ")

        if company_raw.lower() in COMPANY_OVERRIDES:
            return COMPANY_OVERRIDES[company_raw.lower()]
        if is_platform_name(company_raw):
            return None

        return _title_company(company_raw) if company_raw.islower() else company_raw

    except Exception:
        return None


def make_fingerprint(
    company: Optional[str],
    role: Optional[str],
    applied_date: Optional[datetime] = None,
) -> Optional[str]:
    norm_company = normalize_company(company)
    norm_role = normalize_role(role)
    if norm_company == "Unknown" or norm_role == "Unknown":
        return None
    c = re.sub(r"[^a-z0-9]", "", norm_company.lower())
    r = re.sub(r"[^a-z0-9]", "", norm_role.lower())
    d = applied_date.strftime("%Y-%m") if applied_date else "nodate"
    raw = f"{c}_{r}_{d}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
