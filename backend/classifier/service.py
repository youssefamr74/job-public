"""The single-call AI path: one email, one request, one retry on invalid output."""

from __future__ import annotations

from typing import Optional

from ai.clients import AIClient
from ai.prompts import (
    CLASSIFICATION_SCHEMA,
    CLASSIFY_SYSTEM,
    RETRY_NOTE,
    AIClassification,
    classification_message,
    parse_classification,
)
from constants.app_config import AI_CLASSIFY_MAX_TOKENS


async def classify_email(
    client: AIClient, email: dict, rule_result: Optional[dict], privacy_mode: str, body_chars: int,
) -> Optional[AIClassification]:
    """None when the provider twice returned something that isn't the schema. Raises AIError."""
    content = classification_message(email, rule_result, privacy_mode, body_chars)
    for attempt in range(2):
        completion = await client.complete(
            CLASSIFY_SYSTEM, [{"role": "user", "content": content + (RETRY_NOTE if attempt else "")}],
            AI_CLASSIFY_MAX_TOKENS, schema=CLASSIFICATION_SCHEMA,
        )
        parsed = parse_classification(completion.text)
        if parsed is not None:
            return parsed
    return None
