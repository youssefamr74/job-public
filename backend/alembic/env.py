from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from config import settings
from database import Base
import applications.models  # noqa: F401
import auth.models  # noqa: F401
import companion.models  # noqa: F401
import cv.models  # noqa: F401
import goals.models  # noqa: F401
import mail.models  # noqa: F401
import diagnostics.models  # noqa: F401
import ai.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
sync_url = settings.database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Foreign keys stay off here: batch migrations rebuild tables by dropping them,
    # and with foreign keys on, dropping a parent table would cascade-delete its rows.
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
