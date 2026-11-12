import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator


class MailErrorDetail(BaseModel):
    code: str
    message: str


class ImapConnectRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    app_password: SecretStr

    @field_validator("email")
    @classmethod
    def looks_like_email(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter the full Gmail address, like name@gmail.com")
        return v

    @field_validator("app_password")
    @classmethod
    def strip_spaces(cls, v: SecretStr) -> SecretStr:
        value = "".join(v.get_secret_value().split())
        if not value:
            raise ValueError("The app password is required")
        return SecretStr(value)


class OAuthClientRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    client_secret: SecretStr

    @field_validator("client_id")
    @classmethod
    def looks_like_google_client(cls, v: str) -> str:
        v = v.strip()
        if not v.endswith(".apps.googleusercontent.com"):
            raise ValueError("A Google OAuth client ID ends with .apps.googleusercontent.com")
        return v

    @field_validator("client_secret")
    @classmethod
    def secret_not_blank(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("The client secret is required")
        return SecretStr(v.get_secret_value().strip())


class AuthUrlResponse(BaseModel):
    auth_url: str


class RedirectUriResponse(BaseModel):
    redirect_uri: str


class DisconnectResponse(BaseModel):
    disconnected: bool
    revoked: Optional[bool] = None


MailState = Literal["none", "connected", "needs_relink", "error"]
SourceType = Literal["imap", "oauth"]


class MailStatusResponse(BaseModel):
    status: MailState
    source: Optional[SourceType] = None
    email: Optional[str] = None
    last_error: Optional[str] = None
    connected_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MailTestResponse(BaseModel):
    ok: bool
    email: Optional[str] = None
    code: Optional[str] = None
    message: Optional[str] = None


class SetupStatusResponse(BaseModel):
    mail: MailState
    mail_source: Optional[SourceType] = None
    mail_email: Optional[str] = None
    ai_configured: bool
    first_sync_done: bool
    sync_running: bool = False
    last_sync_at: Optional[datetime] = None


class EmailContent(BaseModel):
    """One email as readable text, fetched from the mail source when asked for. Never stored."""

    id: str
    subject: str
    sender: str
    date: Optional[datetime] = None
    body: str
