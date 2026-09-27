from collections.abc import Callable
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from ticketward.core.config import Settings
from ticketward.db.base import (
    NAMING_CONVENTION,
    UPDATED_AT_TRIGGER_FUNCTION,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from ticketward.db.session import build_database_url, create_db_engine, create_session_factory


def test_url_is_assembled_from_parts_and_masks_password(
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        db_host="db.internal", db_port=6543, db_name="rf", db_user="tw_app", db_password="p@ss:w/rd"
    )
    url = build_database_url(settings)
    assert url.drivername == "postgresql+asyncpg"
    assert (url.host, url.port, url.database, url.username) == ("db.internal", 6543, "rf", "tw_app")
    assert url.password == "p@ss:w/rd"
    assert "p@ss" not in str(url)
    assert "p@ss" not in repr(url)


def test_url_override_wins(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(
        database_url=SecretStr("postgresql+asyncpg://u:pw@override:5432/other"), db_host="ignored"
    )
    url = build_database_url(settings)
    assert (url.host, url.database) == ("override", "other")


def test_url_without_password(settings_factory: Callable[..., Settings]) -> None:
    assert build_database_url(settings_factory()).password is None


async def test_engine_is_lazy_and_configured(settings_factory: Callable[..., Settings]) -> None:
    engine = create_db_engine(settings_factory(db_pool_size=3, db_max_overflow=2))
    try:
        assert isinstance(engine, AsyncEngine)
        assert engine.pool.size() == 3  # type: ignore[attr-defined]
        assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
        factory = create_session_factory(engine)
        assert factory.kw["expire_on_commit"] is False
        assert factory.kw["autoflush"] is False
    finally:
        await engine.dispose()


def test_base_uses_the_naming_convention() -> None:
    assert dict(Base.metadata.naming_convention) == {
        "ix": NAMING_CONVENTION["ix"],
        "uq": NAMING_CONVENTION["uq"],
        "ck": NAMING_CONVENTION["ck"],
        "fk": NAMING_CONVENTION["fk"],
        "pk": NAMING_CONVENTION["pk"],
    }


class _ProbeBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Probe(UUIDPrimaryKeyMixin, TimestampMixin, _ProbeBase):
    __tablename__ = "probe"
    __table_args__ = (UniqueConstraint("slug"),)

    slug: Mapped[str] = mapped_column(String(64))


def test_mixins_render_spec_conventions() -> None:
    table = _Probe.__table__
    assert isinstance(table, Table)
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    ddl = str(CreateTable(table).compile(dialect=dialect))
    assert "id UUID DEFAULT gen_random_uuid() NOT NULL" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "CONSTRAINT pk_probe PRIMARY KEY (id)" in ddl
    assert "CONSTRAINT uq_probe_slug UNIQUE (slug)" in ddl


def test_trigger_function_name_matches_initial_migration(backend_dir: Path) -> None:
    migration = (backend_dir / "alembic" / "versions" / "0001_extensions.py").read_text("utf-8")
    assert f"FUNCTION {UPDATED_AT_TRIGGER_FUNCTION}()" in migration
