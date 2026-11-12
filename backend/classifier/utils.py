"""Shared parsing helpers for Claude classification responses."""

from datetime import datetime
from typing import Optional


def extract_json(raw: str) -> str:
    """Pull a JSON object out of a Claude response, stripping markdown fences if present."""
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return part
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        return raw[start:end]
    return raw


def parse_interview_date(raw_date: Optional[str]) -> Optional[datetime]:
    if not raw_date:
        return None
    try:
        return datetime.fromisoformat(raw_date)
    except Exception:
        return None
