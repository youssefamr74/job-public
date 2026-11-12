from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    HOST: str = "127.0.0.1"
    PORT: int = 8000
    BACKEND_URL: str = "http://127.0.0.1:8000"
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]
    # Where Google OAuth sends the browser back to once Gmail is connected (or failed).
    WEB_SETUP_URL: str = "http://localhost:5173/setup"

    DATA_DIR: Path = BACKEND_DIR.parent / "data"
    DATABASE_PATH: Optional[Path] = None
    SQL_ECHO: bool = False
    # Fernet key for stored mail credentials; generated at DATA_DIR/secret.key if empty.
    SECRET_KEY: str = ""
    # The built web app (web/dist). Served at / when it exists.
    WEB_DIST_DIR: Path = BACKEND_DIR.parent / "web" / "dist"


    @field_validator("CORS_ORIGINS")
    @classmethod
    def no_wildcard_origin(cls, origins: List[str]) -> List[str]:
        # The API has no login, so any page allowed here can read and change everything.
        if any("*" in origin for origin in origins):
            raise ValueError("CORS_ORIGINS can't contain a wildcard; list the web app's origin")
        return origins

    @property
    def database_path(self) -> Path:
        return self.DATABASE_PATH or self.DATA_DIR / "job.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"


settings = Settings()
