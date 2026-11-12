"""The user's AI settings and access to their provider.

The active settings are kept in memory (loaded at startup and on every change), so checking
whether AI is configured never needs a database round trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.clients import AIClient, AIError, make_client
from ai.models import AIConfig
from ai.providers import PROVIDERS, Provider
from auth.models import User
from constants.app_config import AI_TIMEOUT
from mail.crypto import CredentialsError, decrypt_json, encrypt_json


@dataclass(frozen=True)
class ActiveAI:
    provider: Provider
    model: str
    api_key: Optional[str]
    base_url: Optional[str]
    privacy_mode: str
    body_chars: int
    use_batch: bool
    batch_threshold: int

    def client(self) -> AIClient:
        return make_client(self.provider, self.model, self.api_key, self.base_url, new_http())


_active: Optional[ActiveAI] = None


def new_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=AI_TIMEOUT)


def active() -> Optional[ActiveAI]:
    return _active


def ai_configured() -> bool:
    return _active is not None


def set_active(value: Optional[ActiveAI]) -> None:
    global _active
    _active = value


def provider_or_error(provider_id: str) -> Provider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise AIError("unknown_provider", f"Unknown AI provider '{provider_id}'.")
    return provider


async def get_config(db: AsyncSession, user: User) -> Optional[AIConfig]:
    return (await db.execute(select(AIConfig).where(AIConfig.user_id == user.id))).scalar_one_or_none()


def stored_api_key(config: Optional[AIConfig]) -> Optional[str]:
    if config is None:
        return None
    try:
        return decrypt_json(config.credentials).get("api_key")
    except CredentialsError:
        return None


def _to_active(config: AIConfig) -> ActiveAI:
    return ActiveAI(
        provider=provider_or_error(config.provider),
        model=config.model,
        api_key=stored_api_key(config),
        base_url=config.base_url,
        privacy_mode=config.privacy_mode,
        body_chars=config.body_chars,
        use_batch=config.use_batch,
        batch_threshold=config.batch_threshold,
    )


async def load_active(db: AsyncSession, user: User) -> Optional[ActiveAI]:
    config = await get_config(db, user)
    set_active(_to_active(config) if config else None)
    return _active


async def save_config(
    db: AsyncSession, user: User, provider_id: str, model: str, api_key: Optional[str], base_url: Optional[str],
    privacy_mode: str, body_chars: int, use_batch: bool, batch_threshold: int,
) -> AIConfig:
    provider = provider_or_error(provider_id)
    config = await get_config(db, user)
    if api_key is None and config is not None and config.provider == provider_id:
        api_key = stored_api_key(config)
    if provider.needs_api_key and not api_key:
        raise AIError("api_key_required", f"{provider.name} needs an API key.")
    if config is None:
        config = AIConfig(user_id=user.id)
        db.add(config)
    config.provider = provider_id
    config.model = model
    config.base_url = base_url or None
    config.credentials = encrypt_json({"api_key": api_key} if api_key else {})
    config.privacy_mode = privacy_mode
    config.body_chars = body_chars
    config.use_batch = use_batch
    config.batch_threshold = batch_threshold
    await db.commit()
    await db.refresh(config)
    set_active(_to_active(config))
    return config


async def delete_config(db: AsyncSession, user: User) -> bool:
    config = await get_config(db, user)
    set_active(None)
    if config is None:
        return False
    await db.delete(config)
    await db.commit()
    return True


async def complete_text(system: str, messages: list[dict], max_tokens: int, pdf: Optional[bytes] = None) -> str:
    """One plain-text completion with the configured provider. Raises AIError."""
    settings = active()
    if settings is None:
        raise AIError("not_configured", "AI is not configured")
    client = settings.client()
    try:
        return (await client.complete(system, messages, max_tokens, pdf=pdf)).text.strip()
    finally:
        await client.aclose()
