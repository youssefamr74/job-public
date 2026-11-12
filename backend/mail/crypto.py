"""Encryption for secrets kept in the database: app passwords, OAuth client secrets and tokens."""

import json
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import settings


class CredentialsError(Exception):
    pass


def key_path() -> Path:
    return settings.DATA_DIR / "secret.key"


def _load_or_create_key() -> bytes:
    path = key_path()
    if path.exists():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.SECRET_KEY.encode() if settings.SECRET_KEY else _load_or_create_key()
    try:
        return Fernet(key)
    except ValueError as exc:
        raise CredentialsError(
            "The secret key is not a valid Fernet key (32 url-safe base64-encoded bytes)."
        ) from exc


def ensure_key() -> None:
    _fernet()


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise CredentialsError(
            "Stored mail credentials can't be decrypted. The secret key changed; reconnect Gmail."
        ) from exc
