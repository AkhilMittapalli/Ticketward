"""Async engine and session factory (ADR-0006).

Nothing connects at import time: the application lifespan (and Alembic) create the
engine explicitly from ``Settings`` and dispose of it on shutdown.
"""

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ticketward.core.config import Settings

_POOL_RECYCLE_S = 1800


def build_database_url(settings: Settings) -> URL:
    """Build the SQLAlchemy URL from settings.

    ``TW_DATABASE_URL`` wins when set; otherwise the URL is assembled from the
    ``TW_DB_*`` parts (the password typically comes from the ``tw_db_password``
    secret file). ``URL`` renders the password as ``***`` in ``repr``/``str``.

    Args:
        settings: Application settings.

    Returns:
        A ``postgresql+asyncpg`` URL.
    """
    if settings.database_url is not None:
        return make_url(settings.database_url.get_secret_value())
    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value() if settings.db_password else None,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Create the process-wide async engine (lazy: no connection is opened here).

    Args:
        settings: Application settings.

    Returns:
        A pooled ``AsyncEngine`` with pre-ping, connect/statement timeouts and an
        ``application_name`` for ``pg_stat_activity``.
    """
    return create_async_engine(
        build_database_url(settings),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
        pool_recycle=_POOL_RECYCLE_S,
        connect_args={
            "timeout": settings.db_connect_timeout_s,
            "command_timeout": settings.db_command_timeout_s,
            "server_settings": {"application_name": settings.service_name},
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory used by repositories (P4).

    Args:
        engine: Application engine.

    Returns:
        A factory producing ``AsyncSession`` objects that do not expire on commit.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
