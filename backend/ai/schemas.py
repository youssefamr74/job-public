from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator

from constants.app_config import AI_BATCH_THRESHOLD_DEFAULT, AI_BODY_CHARS_DEFAULT, AI_BODY_CHARS_MAX, MAX_RESULTS


def _check_url(v: Optional[str]) -> Optional[str]:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not v.startswith(("http://", "https://")):
        raise ValueError("The base URL must start with http:// or https://")
    return v.rstrip("/")


class ProviderInfo(BaseModel):
    id: str
    name: str
    default_base_url: str
    needs_api_key: bool
    supports_batch: bool


class ModelsRequest(BaseModel):
    provider: str
    api_key: Optional[SecretStr] = None
    base_url: Optional[str] = None

    _url = field_validator("base_url")(classmethod(lambda cls, v: _check_url(v)))


class ModelInfo(BaseModel):
    id: str
    name: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


class AIConfigRequest(BaseModel):
    provider: str
    model: str = Field(min_length=1, max_length=200)
    api_key: Optional[SecretStr] = None
    base_url: Optional[str] = None
    privacy_mode: Literal["subject_sender", "with_body"] = "subject_sender"
    body_chars: int = Field(AI_BODY_CHARS_DEFAULT, ge=100, le=AI_BODY_CHARS_MAX)
    use_batch: bool = True
    batch_threshold: int = Field(AI_BATCH_THRESHOLD_DEFAULT, ge=1, le=50_000)

    _url = field_validator("base_url")(classmethod(lambda cls, v: _check_url(v)))


class AIStatusResponse(BaseModel):
    configured: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    has_api_key: bool = False
    privacy_mode: Optional[str] = None
    body_chars: Optional[int] = None
    use_batch: Optional[bool] = None
    batch_threshold: Optional[int] = None
    pending_batches: int = 0


class AITestResponse(BaseModel):
    ok: bool
    structured_output: bool = False
    code: Optional[str] = None
    message: Optional[str] = None


class EstimateRequest(BaseModel):
    since_date: date
    max_messages: int = Field(MAX_RESULTS, ge=1, le=MAX_RESULTS)


class PricePerMillion(BaseModel):
    input: float
    output: float


class EstimateResponse(BaseModel):
    estimate: bool
    note: str
    emails_checked: int
    already_processed: int
    filtered_out: int
    settled_by_rules: int
    would_send_to_ai: int
    privacy_mode: str
    input_tokens: int
    output_tokens: int
    would_use_batch: bool
    provider: Optional[str]
    model: Optional[str]
    price_per_million: Optional[PricePerMillion]
    estimated_cost_usd: Optional[float]
    prices_last_checked: Optional[str]


class NotJobItem(BaseModel):
    id: str
    subject: Optional[str] = None
    sender: Optional[str] = None


class AIReviewResponse(BaseModel):
    checked: int
    updated: int
    unchanged: int
    not_job: int
    not_job_items: list[NotJobItem] = []
    failed: int
    skipped_manual: int
    no_message: int
    queued_in_batch: int
