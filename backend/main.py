import logging
import asyncio
from contextlib import asynccontextmanager, suppress
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from config import settings

# Import all models before routers so SQLAlchemy mapper is fully configured
import auth.models  # noqa: F401
import applications.models  # noqa: F401
import goals.models  # noqa: F401
import cv.models  # noqa: F401
import companion.models  # noqa: F401
import mail.models  # noqa: F401
import diagnostics.models  # noqa: F401
import ai.models  # noqa: F401
import opportunities.models  # noqa: F401
import sync_runs.models  # noqa: F401
import notifications.models  # noqa: F401

from users.routes import router as users_router
from mail.routes import router as mail_router
from setup_wizard.routes import router as setup_router
from diagnostics.routes import router as debug_router
from ai.routes import router as ai_router
from ai.batches import batch_worker
from ai.service import load_active
from applications.routes import router as applications_router
from analytics.routes import router as analytics_router
from companion.routes import router as companion_router
from goals.routes import router as goals_router
from opportunities.routes import router as opportunities_router
from sync_runs.routes import router as sync_router, settings_router
from sync_runs.scheduler import sync_scheduler
from notifications.checker import notification_checker
from notifications.routes import router as notifications_router
from user_data.routes import router as data_router
from sync_runs.service import fail_interrupted_runs
from analytics.role_groups_service import refresh_role_groups
from cv.routes import router as cv_router
from auth.dependencies import get_local_user
from database import AsyncSessionLocal
from mail.crypto import ensure_key
from web_app import mount_web_app
from security import CSRF_HEADER, LocalRequestGuard, RedactQueryParams

APP_NAME = "Jōb"
APP_VERSION = "0.1.0"

LOG_DIR = settings.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            LOG_DIR / "job.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("uvicorn.access").addFilter(RedactQueryParams())
# Their debug output has SQL parameters (email text) and request headers (tokens), so never show it.
for _name in ("aiosqlite", "httpcore", "hpack"):
    logging.getLogger(_name).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_key()
    async with AsyncSessionLocal() as db:
        try:
            user = await get_local_user(db)
            await load_active(db, user)
            await refresh_role_groups(db)
            interrupted = await fail_interrupted_runs(db)
            if interrupted:
                logger.warning(f"Marked {interrupted} interrupted sync run(s) as failed")
        except OperationalError as exc:
            raise RuntimeError(
                f"The database at {settings.database_path} is not set up. "
                "Run `alembic upgrade head` in the backend folder first."
            ) from exc
    tasks = [
        asyncio.create_task(batch_worker(AsyncSessionLocal)),
        asyncio.create_task(sync_scheduler(AsyncSessionLocal)),
        asyncio.create_task(notification_checker(AsyncSessionLocal)),
    ]
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Accept", "Content-Type", CSRF_HEADER],
)

app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(setup_router, prefix="/setup", tags=["setup"])
app.include_router(mail_router, prefix="/mail", tags=["mail"])
app.include_router(applications_router, prefix="/applications", tags=["applications"])
app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
app.include_router(companion_router, prefix="/companion", tags=["companion"])
app.include_router(goals_router, prefix="/goals", tags=["goals"])
app.include_router(cv_router, prefix="/cv", tags=["cv"])
app.include_router(debug_router, prefix="/debug", tags=["debug"])
app.include_router(ai_router, prefix="/ai", tags=["ai"])
app.include_router(opportunities_router, prefix="/opportunities", tags=["opportunities"])
app.include_router(sync_router, prefix="/sync", tags=["sync"])
app.include_router(settings_router, prefix="/settings", tags=["settings"])
app.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
app.include_router(data_router, prefix="/data", tags=["data"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Errors from field validators carry the raw ValueError in "ctx", which JSON can't encode.
    # The submitted values are dropped: they can be secrets such as an app password.
    errors = [
        {k: v for k, v in error.items() if k not in ("input", "url")}
        for error in jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    ]
    logger.warning(
        "Validation error on %s: %s", request.url.path, [(e["loc"], e["msg"]) for e in errors]
    )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": APP_VERSION}


mount_web_app(app, settings.WEB_DIST_DIR)
# Added last so it runs first, before CORS and before the web app pages.
app.add_middleware(LocalRequestGuard)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT)
