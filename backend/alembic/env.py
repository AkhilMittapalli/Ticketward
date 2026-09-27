"""Alembic environment: async migrations using the application settings.

``alembic upgrade head`` runs in the one-shot ``migrate`` Compose service, never at
application startup (spec §10).
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ticketward.core.config import get_settings
from ticketward.core.logging import configure_logging
from ticketward.db.base import Base
from ticketward.db.session import build_database_url

settings = get_settings()
configure_logging(level=settings.log_level, json_logs=settings.log_json)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=build_database_url(settings),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations over an async connection (NullPool: one connection, then exit)."""
    engine = create_async_engine(
        build_database_url(settings),
        poolclass=pool.NullPool,
        connect_args={"timeout": settings.db_connect_timeout_s},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
