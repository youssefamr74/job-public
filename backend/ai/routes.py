from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.clients import AIError, make_client
from ai.estimate import estimate
from ai.models import BATCH_PENDING, AIBatchJob
from ai.prompts import CLASSIFICATION_SCHEMA, parse_classification
from ai.providers import PROVIDERS
from ai.schemas import (
    AIConfigRequest,
    AIStatusResponse,
    AITestResponse,
    EstimateRequest,
    EstimateResponse,
    ModelsRequest,
    ModelsResponse,
    ProviderInfo,
)
from ai import service as ai_service
from ai.service import active, delete_config, get_config, provider_or_error, save_config, stored_api_key
from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from mail.base import MailError

router = APIRouter()

_STATUS_FOR_CODE = {"auth": 400, "api_key_required": 400, "unknown_provider": 400, "not_found": 400,
                    "not_configured": 400, "no_mail": 400}


def ai_error(exc: AIError) -> HTTPException:
    return HTTPException(status_code=_STATUS_FOR_CODE.get(exc.code, 502),
                         detail={"code": exc.code, "message": exc.message})


def _secret(value) -> str | None:
    return value.get_secret_value() if value is not None else None


@router.get("/providers", response_model=list[ProviderInfo])
async def providers() -> list[ProviderInfo]:
    return [ProviderInfo(id=p.id, name=p.name, default_base_url=p.default_base_url,
                         needs_api_key=p.needs_api_key, supports_batch=p.supports_batch)
            for p in PROVIDERS.values()]


@router.post("/models", response_model=ModelsResponse)
async def models(
    body: ModelsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelsResponse:
    try:
        provider = provider_or_error(body.provider)
        api_key = _secret(body.api_key)
        if api_key is None:
            config = await get_config(db, user)
            if config is not None and config.provider == provider.id:
                api_key = stored_api_key(config)
        if provider.needs_api_key and not api_key:
            raise AIError("api_key_required", f"{provider.name} needs an API key.")
        client = make_client(provider, "", api_key, body.base_url, ai_service.new_http())
        try:
            listed = await client.list_models()
        finally:
            await client.aclose()
    except AIError as exc:
        raise ai_error(exc)
    return ModelsResponse(models=sorted(listed, key=lambda m: m["id"]))


@router.post("/config", response_model=AIStatusResponse)
async def set_config(
    body: AIConfigRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIStatusResponse:
    try:
        await save_config(db, user, body.provider, body.model, _secret(body.api_key), body.base_url,
                          body.privacy_mode, body.body_chars, body.use_batch, body.batch_threshold)
    except AIError as exc:
        raise ai_error(exc)
    return await status(user, db)


@router.post("/test", response_model=AITestResponse)
async def test() -> AITestResponse:
    settings = active()
    if settings is None:
        return AITestResponse(ok=False, code="not_configured", message="AI is not configured")
    client = settings.client()
    try:
        completion = await client.complete(
            "Reply with one JSON object that matches the schema. This is a connection test.",
            [{"role": "user", "content": 'Classify: subject "Thank you for applying", from "jobs@example.com".'}],
            300, schema=CLASSIFICATION_SCHEMA,
        )
    except AIError as exc:
        return AITestResponse(ok=False, code=exc.code, message=exc.message)
    finally:
        await client.aclose()
    return AITestResponse(ok=True, structured_output=parse_classification(completion.text) is not None)


@router.get("/status", response_model=AIStatusResponse)
async def status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIStatusResponse:
    config = await get_config(db, user)
    if config is None:
        return AIStatusResponse(configured=False)
    pending = (await db.execute(select(func.count()).select_from(AIBatchJob).where(
        AIBatchJob.user_id == user.id, AIBatchJob.status == BATCH_PENDING,
    ))).scalar_one()
    return AIStatusResponse(
        configured=True, provider=config.provider, model=config.model, base_url=config.base_url,
        has_api_key=bool(stored_api_key(config)), privacy_mode=config.privacy_mode,
        body_chars=config.body_chars, use_batch=config.use_batch, batch_threshold=config.batch_threshold,
        pending_batches=pending,
    )


@router.delete("", response_model=AIStatusResponse)
async def remove(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIStatusResponse:
    await delete_config(db, user)
    return AIStatusResponse(configured=False)


@router.post("/estimate", response_model=EstimateResponse)
async def cost_estimate(
    body: EstimateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EstimateResponse:
    try:
        return EstimateResponse(**await estimate(db, user, body.since_date, body.max_messages))
    except AIError as exc:
        raise ai_error(exc)
    except MailError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": exc.message})
