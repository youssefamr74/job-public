"""Is this text a job title at all? Shared by role extraction (classifier/normalization.py) and role groups
(applications/role_groups.py). Works for any profession: it looks for the shape of a title (a word for a
person doing a job), not for a list of professions.

Words are compared folded: lowercase, no accents, hyphens as spaces."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from constants.places import PLACES, fold

WORDS_FILE = Path(__file__).resolve().parent.parent / "constants" / "role_words.json"
_WORDS = json.loads(WORDS_FILE.read_text(encoding="utf-8"))

# Seniority, kind of position and work mode. A role made only of these ("Working student", "Remote") is no role.
TYPE_WORDS = set(_WORDS["type_words"])
# Departments, fields and other generic words. A role made only of these ("Digital", "Master Data") is no role.
GENERIC_WORDS = set(_WORDS["generic_words"])
_GENERIC_ENDINGS = tuple(_WORDS["generic_endings"])
# Words for a person doing a job, and endings that catch most others ("-ist", "-er", "-eur", "-ista").
TITLE_WORDS = set(_WORDS["title_words"])
_TITLE_ENDINGS = tuple(_WORDS["title_endings"])
_NOT_TITLES = set(_WORDS["not_titles"])
# Words that only appear in sentences, not in titles: "Please contact us", "We may get back to you".
_SENTENCE_WORDS = set(_WORDS["sentence_words"])
MAX_TITLE_WORDS = 8

# "Position: Nurse", "The role of Accountant", "Programme: Graduate Engineer". A bare "Programme" only goes
# when more than one word follows, so "Programme Manager" stays.
_SEP = r"(?:\s*[:.\-–—|]\s*|\s+)"
_LEADING_LABELS = [
    re.compile(rf"^(?:the\s+|a\s+|an\s+)?(?:position|role|job|vacancy|stelle|poste|puesto)\s+(?:of|as|for|als|de)\b{_SEP}", re.I),
    re.compile(rf"^(?:the\s+)?(?:position|role|stanowisko)\b{_SEP}", re.I),
    re.compile(r"^(?:job|vacancy|programme|program)\s*[:\-–—|]\s*", re.I),
    re.compile(r"^(?:programme|program)\s+(?=\S+\s+\S)", re.I),
]
_EDGE_PUNCTUATION = " \t:;,.!?-–—|*\"'“”„"


def _words(text: str) -> list[str]:
    return [w for w in (re.sub(r"[^\w+#&]", "", part) for part in fold(text).replace("/", " ").split()) if w]


def tidy_role(text: Optional[str]) -> str:
    """Underscores as " / ", no leading label like "Position:" and no punctuation at the ends."""
    text = " ".join((text or "").replace("_", " / ").split()).strip(_EDGE_PUNCTUATION)
    changed = True
    while changed:
        changed = False
        for label in _LEADING_LABELS:
            rest = label.sub("", text, count=1).strip(_EDGE_PUNCTUATION)
            if rest and rest != text:
                text, changed = rest, True
    return text


def is_title_word(word: str) -> bool:
    if word in TITLE_WORDS:
        return True
    if word in _NOT_TITLES or word in GENERIC_WORDS or len(word) < 5:
        return False
    return word.endswith(_TITLE_ENDINGS)


def _all_in(words: list[str], phrases: set[str]) -> bool:
    i = 0
    while i < len(words):
        for size in (3, 2, 1):
            if " ".join(words[i:i + size]) in phrases:
                i += size
                break
        else:
            return False
    return True


def has_sentence_words(text: str) -> bool:
    return any(w in _SENTENCE_WORDS for w in _words(text))


def too_long(text: str) -> bool:
    return len(_words(text)) > MAX_TITLE_WORDS


def is_type_only(text: str) -> bool:
    words = _words(text)
    return bool(words) and _all_in(words, TYPE_WORDS | PLACES)


def is_generic_only(text: str) -> bool:
    """Departments and fields only: "Digital", "Master Data". With a kind of position it's a role ("Marketing
    Internship")."""
    words = _words(text)
    return bool(words) and not any(is_title_word(w) for w in words) and all(
        w in GENERIC_WORDS or w in PLACES or w.endswith(_GENERIC_ENDINGS) for w in words
    )


def lacks_title_word(text: str) -> bool:
    """Longer than 3 words and no word for a person doing a job."""
    words = _words(text)
    return len(words) > 3 and not any(is_title_word(w) for w in words)


def is_company(text: str, company: Optional[str]) -> bool:
    if not company or fold(company) in ("", "unknown"):
        return False
    return _words(text) == _words(company)


SEPARATORS = re.compile(r"\s+[-–—]\s+|\s*\|\s*|\s*,\s*|\s+@\s+")
_BRACKETS = re.compile(r"\([^)]*(?:\)|$)|\[[^\]]*(?:\]|$)|\{[^}]*(?:\}|$)")


def typed_in_brackets(text: str) -> bool:
    """"Marketing (Intern)": the brackets say what kind of position it is."""
    return any(is_type_only(b[1:].rstrip(")]}")) for b in _BRACKETS.findall(text))


def pick_role_part(parts: list[str], company: Optional[str] = None, typed: bool = False) -> Optional[str]:
    """The first part of a title split at " - ", "|" or "," that is a role. A department on its own counts
    with a kind of position: "Praktykant - Marketing" and "Marketing (Intern)" are marketing interns."""
    for part in parts:
        part = tidy_role(part)
        if not part or not re.search(r"[^\W\d_]", part):
            continue
        if is_type_only(part):
            typed = True
        elif is_company(part, company) or too_long(part) or lacks_title_word(part):
            continue
        elif not is_generic_only(part) or typed:
            return part
    return None


def not_a_role(text: Optional[str], company: Optional[str] = None) -> bool:
    """Text that was extracted as a role but isn't one: a sentence, the company's name, a department or a
    kind of position on its own, or a long phrase without any job-title word."""
    text = tidy_role(text)
    if not text or fold(text) in ("unknown", "n/a", "none"):
        return True
    if has_sentence_words(text) or is_company(text, company):
        return True
    return pick_role_part(SEPARATORS.split(_BRACKETS.sub(" ", text)), company, typed_in_brackets(text)) is None


def role_or_unknown(role: Optional[str], company: Optional[str]) -> str:
    """For extraction, once the company is known: "Unknown" when the role is the company's name."""
    if role and role != "Unknown" and is_company(tidy_role(role), company):
        return "Unknown"
    return role or "Unknown"
