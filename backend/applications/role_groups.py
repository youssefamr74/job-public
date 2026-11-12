"""Role groups for Analytics: the core of a job title, so "Senior Nurse (m/w/d) - Berlin" and "Nurse" count
together. Works for any profession: it removes words about seniority, kind of contract, place and job ids, and
never looks a profession up in a list. The role shown to the user is never changed.

A group is stored as a key (lowercase, no accents, see `group_key`). The user can merge one group into another
(a rule, kept in RoleGroupMerge) or say what a single application counts as (Application.role_group_override)."""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from classifier.role_quality import has_sentence_words, is_company, pick_role_part, tidy_role, typed_in_brackets
from constants.places import PLACES, fold

SYNONYMS_FILE = Path(__file__).resolve().parent.parent / "constants" / "role_synonyms.json"
NO_ROLE_LABEL = "Role not found"

# Words about seniority, kind of position, contract and work mode, removed wherever they are in the title.
# Compared folded: lowercase, no accents, hyphens as spaces. "Head of" is a role, so it stays.
_ANYWHERE = {
    # English
    "junior", "jr", "jnr", "senior", "sr", "snr", "regular", "mid level", "midlevel", "mid senior", "entry level",
    "intern", "internship", "working student", "trainee", "graduate", "grad", "apprentice", "apprenticeship",
    "full time", "fulltime", "part time", "parttime", "remote", "fully remote", "hybrid", "on site", "onsite",
    # Polish
    "mlodszy", "mlodsza", "starszy", "starsza", "stazysta", "stazystka", "praktykant", "praktykantka", "staz",
    "praktyki", "samodzielny", "samodzielna", "zdalnie", "zdalna", "zdalny", "hybrydowo", "hybrydowa",
    "hybrydowy", "stacjonarnie", "pelny etat",
    # German
    "praktikant", "praktikantin", "praktikum", "werkstudent", "werkstudentin", "auszubildender", "auszubildende",
    "azubi", "duales studium", "vollzeit", "teilzeit", "home office", "homeoffice", "mobiles arbeiten",
    # French and Spanish
    "stagiaire", "alternant", "alternante", "alternance", "teletravail", "becario", "becaria", "practicas", "remoto",
}
# Only removed as the first word: "Lead Accountant" is an accountant, "Team Lead" is a team lead.
_LEADING = {"lead", "principal", "mid", "leitender", "leitende"}
# Only removed as the last word: "Engineer II", "Analyst Level 2".
_TRAILING = {"i", "ii", "iii", "iv", "l1", "l2", "l3", "l4", "level 1", "level 2", "level 3", "level 4"}
# Left hanging once a place or work mode is gone: "Nurse in Berlin" -> "Nurse in".
_CONNECTORS = {"in", "at", "w", "we", "im", "en", "a", "for", "and", "und", "oraz", "&", "@", "/", "+", "-"}

_DASHES = re.compile(r"[‐-―−]")
_BRACKETS = re.compile(r"\([^)]*(?:\)|$)|\[[^\]]*(?:\]|$)|\{[^}]*(?:\}|$)")
_GENDER = re.compile(
    r"(?<![\w/])[mwfhk]\s*/\s*[mwfhk](?:\s*/\s*(?:d|div|divers|x|i))?(?![\w/])"
    r"|(?<!\w)(?:all genders|alle geschlechter)(?!\w)",
    re.IGNORECASE,
)
# "Entwickler*in", "Lehrer:innen", "Księgowy/a", "Programista/ka".
_GENDER_SUFFIX = re.compile(r"(?<=[^\W\d_])(?:[*:_]innen|[*:_]in|\s*/\s*-?(?:in|innen|a|ka|ini))\b", re.IGNORECASE)
_JOB_ID = re.compile(
    r"#\s*[\w-]+"
    r"|\b(?:req|ref|job\s*id|id|nr|no)\b\.?\s*[:#]?\s*[a-z]{0,4}[-_]?\d[\w-]*"
    r"|\b[a-z]{0,5}[-_]?\d{3,}[\w-]*"
    r"|\b\d+\s*%",
    re.IGNORECASE,
)
_SEPARATORS = re.compile(r"\s+-\s+|\s*\|\s*|\s*,\s*|\s+@\s+")
_TOKEN = re.compile(r"[^\s\-/]+")
_ENDS = " .:;-/&*_+@"


def _plain(word: str) -> str:
    return re.sub(r"[^\w+#&]", "", fold(word))


def _matches(words: list[str], start: int, phrases: set[str]) -> int:
    """How many words from `start` form one of the phrases (longest first), or 0."""
    for size in (3, 2, 1):
        if start + size <= len(words) and " ".join(words[start:start + size]) in phrases:
            return size
    return 0


def _strip_words(text: str) -> str:
    tokens = list(_TOKEN.finditer(text))
    words = [_plain(t.group()) for t in tokens]
    keep = [bool(w) or t.group() in "&+" for t, w in zip(tokens, words)]

    i = 0
    while i < len(words):
        size = _matches(words, i, _ANYWHERE | PLACES)
        if size:
            keep[i:i + size] = [False] * size
            i += size
        else:
            i += 1

    def kept() -> list[int]:
        return [i for i, k in enumerate(keep) if k]

    while (left := kept()) and len(left) > 1:
        first = left[0]
        if words[first] in _LEADING and not (words[first] == "mid" and first + 1 < len(words)
                                             and words[first + 1] == "market"):
            keep[first] = False
        elif words[first] in _CONNECTORS or tokens[first].group() in _CONNECTORS:
            keep[first] = False
        else:
            break
    while (left := kept()) and len(left) > 1:
        last = left[-1]
        two = f"{words[left[-2]]} {words[last]}"
        if two in _TRAILING:
            keep[left[-2]] = keep[last] = False
        elif words[last] in _TRAILING or words[last] in _CONNECTORS or tokens[last].group() in _CONNECTORS:
            keep[last] = False
        else:
            break

    out = ""
    previous_end = None
    for index in kept():
        token = tokens[index]
        if previous_end is not None:
            gap = text[previous_end:token.start()]
            out += "/" if "/" in gap else "-" if gap.strip() == "-" else " "
        out += token.group()
        previous_end = token.end()
    return out


def _tidy(text: str) -> str:
    return " ".join(text.split()).strip(_ENDS).strip()


def core_title(role: Optional[str], company: Optional[str] = None) -> Optional[str]:
    """The title without seniority, contract, place, job ids and gender markers, in the role's own case.
    None when there is no role, or the text isn't one (classifier/role_quality.py)."""
    text = tidy_role(role)
    if not text or fold(text) in ("unknown", "n/a", "none"):
        return None
    if has_sentence_words(text) or is_company(text, company):
        return None
    text = _DASHES.sub("-", text)
    typed = typed_in_brackets(text)
    text = _BRACKETS.sub(" ", text)
    text = _GENDER.sub(" ", text)
    text = _GENDER_SUFFIX.sub("", text)
    text = _JOB_ID.sub(" ", text)
    part = pick_role_part([_tidy(p) for p in _SEPARATORS.split(text)], company, typed)
    core = _core_of(part) if part else None
    return _capitalised(core) if core else None


def _core_of(text: str) -> Optional[str]:
    # "Księgowy / Księgowa", "Krankenschwester / Krankenpfleger": the same role written twice.
    alternatives = [c for part in re.split(r"\s+/\s+", text) if (c := _tidy(_strip_words(part)))]
    if len(alternatives) > 1 and len({group_key(c) for c in alternatives}) == 1:
        return alternatives[0]
    core = _tidy(_strip_words(text))
    return core if core and re.search(r"[^\W\d_]", core) else None


def _capitalised(text: str) -> str:
    return text[0].upper() + text[1:] if text.islower() else text


@lru_cache(maxsize=1)
def _synonyms() -> tuple[dict[str, str], Optional[re.Pattern]]:
    data = json.loads(SYNONYMS_FILE.read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for language, entries in data.items():
        if language.startswith("_") or not isinstance(entries, dict):
            continue
        for variant, spelling in entries.items():
            table[_fold_key(variant)] = _fold_key(spelling)
    table = {k: v for k, v in table.items() if k and k != v}
    if not table:
        return table, None
    alternatives = "|".join(re.escape(k) for k in sorted(table, key=len, reverse=True))
    return table, re.compile(rf"(?<!\S)(?:{alternatives})(?!\S)")


def _fold_key(text: str) -> str:
    text = fold(text).replace("/", " ")
    return " ".join(re.sub(r"[^\w+#& ]", " ", text).split())


def group_key(text: Optional[str]) -> Optional[str]:
    """The comparable form of a title: lowercase, no accents, one spacing, hyphens as spaces, and the
    spellings from role_synonyms.json. "Full-Stack Developer" and "fullstack developer" give the same key."""
    if not text:
        return None
    key = _fold_key(text)
    table, pattern = _synonyms()
    if pattern is not None:
        key = pattern.sub(lambda m: table[m.group()], key)
    key = " ".join(key.split())
    return key or None


def role_group(role: Optional[str], company: Optional[str] = None) -> Optional[str]:
    """What Application.role_group stores. None means "Role not found"."""
    return group_key(core_title(role, company))


def resolve(key: Optional[str], merges: dict[str, str]) -> Optional[str]:
    """Follows merge rules (source -> target) to the group a key ends up in."""
    seen = set()
    while key in merges and key not in seen:
        seen.add(key)
        key = merges[key]
    return key


def effective_group(role: Optional[str], stored: Optional[str], override: Optional[str],
                    merges: dict[str, str], company: Optional[str] = None) -> Optional[str]:
    """The group an application counts in: its "Count as" override, or its role's group, after merges.
    `stored` is Application.role_group; without it the group is worked out from the role."""
    if override and (key := group_key(override)):
        return resolve(key, merges)
    return resolve(stored if stored is not None else role_group(role, company), merges)


def group_labels(entries: Iterable[tuple[Optional[str], Optional[str], Optional[str]]]) -> dict[str, str]:
    """A display name per group key, from (role, company, override): the most common core title of the
    applications in it, or the user's own "Count as" text."""
    counts: dict[str, Counter] = {}
    for role, company, override in entries:
        for title in (core_title(role, company), " ".join(override.split()) if override else None):
            if title and (key := group_key(title)):
                counts.setdefault(key, Counter())[title] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in counts.items()}


def label_for(key: Optional[str], labels: dict[str, str]) -> str:
    if key is None:
        return NO_ROLE_LABEL
    return labels.get(key) or key[:1].upper() + key[1:]
