"""Pracuj.pl "Status aplikacji" notifications: "<Role>: <what happened>", with the offer in the body."""

import re
from dataclasses import dataclass
from typing import Optional

from classifier.normalization import display_role, normalize_company

_SENDER = re.compile(r"@(?:[\w-]+\.)*pracuj\.pl\b", re.IGNORECASE)
_SUBJECT = re.compile(r"^(?P<role>.+?):\s+(?P<event>.+)$")
# The offer line is "<Role> <Company> <City> [(gm./pow. …)], <voivodeship>".
_VOIVODESHIPS = (
    r"(?:dolnośląskie|kujawsko-pomorskie|lubelskie|lubuskie|łódzkie|małopolskie|mazowieckie|opolskie|"
    r"podkarpackie|podlaskie|pomorskie|śląskie|świętokrzyskie|warmińsko-mazurskie|wielkopolskie|"
    r"zachodniopomorskie|zagranica)"
)
_CITY_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż\-]+"
# A second city word only counts before "(gm. …)", so "Lumen Analytics Kraków" isn't read as a city.
_LOCATION = rf"\s+{_CITY_WORD}(?:\s+{_CITY_WORD}(?=\s+\())?(?:\s+\([^)]*\))?,\s+{_VOIVODESHIPS}\b"
_OFFER_END = rf"(?:{_LOCATION}|\s+(?:Zarządzaj|Pracodawca|Sprawdź|Kolejni|Zobacz)\b|\s*$)"
MAX_COMPANY_LENGTH = 60
# The company ends right after its legal form when it has one.
_LEGAL_FORM = re.compile(
    r"^(?P<name>.+?\b(?:sp\.\s*z\s*o\.\s*o\.?|sp[oó]łka\s+z\s+ograniczon\w*\s+odpowiedzialno\w*|"
    r"sp[oó]łka\s+akcyjna|S\.A\.|GmbH|Ltd\.?|Inc\.?|B\.V\.|AG|SE|LLC))(?!\w)",
    re.IGNORECASE,
)

# Pracuj.pl's own notices about an application. None of them is an outcome, but all of
# them confirm that the application exists.
_APPLIED_EVENTS = [
    r"twoja aplikacja jest już u pracodawcy",
    r"aplikacja została (?:wysłana|dostarczona|przekazana)",
    r"pracodawca udziela bezpośrednich informacji",
    r"zobacz kompetencje (?:pozostałych|innych) kandydatów",
    r"pracodawca (?:otrzymał|wyświetlił|zobaczył) (?:twoją )?aplikację",
]


# The employer closed the process: the application is over.
_PROCESS_ENDED = re.compile(r"pracodawca zakończył rekrutację")
# The employer is waiting for the candidate: the status stays, the application needs an action.
_ACTION_NEEDED = re.compile(r"pracodawca czeka na dodatkowe informacje")
PROCESS_ENDED_CONFIDENCE = 0.75


@dataclass
class PracujParse:
    company: Optional[str]
    role: Optional[str]
    # None means the status has to come from the body.
    status: Optional[str]
    status_confidence: float
    reason: str
    action_needed: bool = False


def _company_after_role(role_text: str, body: str) -> Optional[str]:
    # The role can appear earlier in the text too; the first mention followed by a short
    # company name and a location is the offer line.
    pattern = rf"{re.escape(role_text)}\s+(?P<company>.{{2,{MAX_COMPANY_LENGTH}}}?){_OFFER_END}"
    for match in re.finditer(pattern, body or ""):
        raw = match.group("company").strip()
        legal = _LEGAL_FORM.match(raw)
        if legal:
            raw = legal.group("name")
        if len(raw.split()) > 10:
            continue
        company = normalize_company(raw)
        if company != "Unknown":
            return company
    return None


def parse_pracuj(sender: str, subject: str, body: str) -> Optional[PracujParse]:
    if not _SENDER.search(sender or ""):
        return None
    match = _SUBJECT.search(subject or "")
    if not match:
        return None
    role_text = match.group("role").strip()
    event = match.group("event").lower()
    role = display_role(role_text)
    applied = any(re.search(p, event) for p in _APPLIED_EVENTS)
    if _PROCESS_ENDED.search(event):
        return PracujParse(
            company=_company_after_role(role_text, body), role=None if role == "Unknown" else role,
            status="Rejected", status_confidence=PROCESS_ENDED_CONFIDENCE,
            reason="Pracuj.pl: the employer ended the process",
        )
    if _ACTION_NEEDED.search(event):
        return PracujParse(
            company=_company_after_role(role_text, body), role=None if role == "Unknown" else role,
            status=None, status_confidence=0.0, reason="Pracuj.pl: the employer is waiting for more information",
            action_needed=True,
        )
    return PracujParse(
        company=_company_after_role(role_text, body),
        role=None if role == "Unknown" else role,
        status="Applied" if applied else None,
        status_confidence=0.85 if applied else 0.0,
        reason="Pracuj.pl application notice",
    )
