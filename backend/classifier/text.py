"""Cleanup applied to email text before it's classified or stored."""

import html
import re

_BLOCKS = re.compile(
    r"<!--.*?-->|<(head|style|script|title|mj-head|mj-style|mj-attributes|mj-preview)\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_TAG = re.compile(r"</?[a-zA-Z][\w:-]*(?:\s[^<>]*)?/?>|<![^<>]*>")
_LINE_BREAK_TAGS = re.compile(r"<(?:br|/p|/div|/tr|/li|/h\d|/mj-text|/mj-section)\b[^>]*>", re.IGNORECASE)
_INVISIBLE = re.compile(
    "[­͏؜ᅟᅠ឴឵᠎​-‏‪-‮⁠-⁤⁪-⁯ㅤ﻿ﾠ]"
)
_ODD_SPACES = re.compile("[  -   　]")
# Long tokens mixing letters and digits are tracking ids; URLs (with ':' or '.') are kept.
_TRACKING_TOKEN = re.compile(
    r"(?<!\S)(?=[A-Za-z0-9_\-=+/]*\d)(?=[A-Za-z0-9_\-=+/]*[A-Za-z])[A-Za-z0-9_\-=+/]{25,}(?!\S)"
)
# Preheaders often start with stray numbers or symbols before the first real word.
_LEADING_JUNK = re.compile(r"^(?:[\d\W_]{1,6}\s+)+(?=\w)")


def strip_markup(text: str) -> str:
    text = _BLOCKS.sub(" ", text)
    text = _LINE_BREAK_TAGS.sub("\n", text)
    return _TAG.sub(" ", text)


def clean_text(text: str) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        text = strip_markup(text)
    text = html.unescape(text)
    text = _INVISIBLE.sub("", text)
    text = _ODD_SPACES.sub(" ", text)
    text = _TRACKING_TOKEN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _LEADING_JUNK.sub("", text)


READABLE_LIMIT = 50_000


def readable_text(text: str) -> str:
    """Email text for reading: markup, invisible characters and tracking ids removed, paragraphs kept."""
    if not text:
        return ""
    if _TAG.search(text) and "</" in text:
        text = strip_markup(text)
    text = html.unescape(text)
    text = _INVISIBLE.sub("", text)
    text = _ODD_SPACES.sub(" ", text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", _TRACKING_TOKEN.sub(" ", line)).strip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text[:READABLE_LIMIT]
