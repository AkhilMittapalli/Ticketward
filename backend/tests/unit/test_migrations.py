"""Migration checks that need no database: revision graph and offline SQL rendering."""

import importlib.util
import io
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_EXTENSIONS = ("pgcrypto", "vector", "citext", "pg_trgm")


def alembic_config(backend_dir: Path, sql_output: io.StringIO | None = None) -> Config:
    config = Config(
        str(backend_dir / "alembic.ini"), output_buffer=sql_output, stdout=io.StringIO()
    )
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def load_revision(backend_dir: Path) -> ModuleType:
    path = backend_dir / "alembic" / "versions" / "0001_extensions.py"
    spec = importlib.util.spec_from_file_location("tw_migration_0001", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph_is_linear_from_0001(backend_dir: Path) -> None:
    scripts = ScriptDirectory.from_config(alembic_config(backend_dir))
    assert scripts.get_heads() == ["0001"]
    base = scripts.get_revision("0001")
    assert base is not None
    assert base.down_revision is None


def test_upgrade_and_downgrade_statements(
    backend_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_revision(backend_dir)
    executed: list[str] = []

    class FakeOp:
        @staticmethod
        def execute(statement: str) -> None:
            executed.append(" ".join(statement.split()))

    monkeypatch.setattr(module, "op", FakeOp)
    module.upgrade()
    assert executed[:4] == [
        'CREATE EXTENSION IF NOT EXISTS "pgcrypto"',
        'CREATE EXTENSION IF NOT EXISTS "vector"',
        'CREATE EXTENSION IF NOT EXISTS "citext"',
        'CREATE EXTENSION IF NOT EXISTS "pg_trgm"',
    ]
    assert any("CREATE OR REPLACE FUNCTION tw_set_updated_at()" in sql for sql in executed)
    assert all("IF NOT EXISTS" in sql for sql in executed if "EXTENSION" in sql)
    executed.clear()
    module.downgrade()
    # Extensions are owned by infra/postgres/init.sql (superuser); never dropped here.
    assert executed == ["DROP FUNCTION IF EXISTS tw_set_updated_at()"]


def test_init_sql_creates_every_extension_the_migration_guards(
    backend_dir: Path, repo_root: Path
) -> None:
    init_sql = (repo_root / "infra" / "postgres" / "init.sql").read_text("utf-8")
    migration = (backend_dir / "alembic" / "versions" / "0001_extensions.py").read_text("utf-8")
    for extension in REQUIRED_EXTENSIONS:
        statement = f'CREATE EXTENSION IF NOT EXISTS "{extension}"'
        assert statement in init_sql
        assert statement in migration
    assert "ON_ERROR_STOP" in init_sql


def test_offline_sql_renders_without_credentials(
    backend_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TW_ENV", "test")
    monkeypatch.setenv("TW_DB_HOST", "db.invalid")
    monkeypatch.setenv("TW_DB_PASSWORD", "offline-secret-value")
    monkeypatch.setenv("TW_LOG_LEVEL", "WARNING")
    output = io.StringIO()
    command.upgrade(alembic_config(backend_dir, output), "head", sql=True)
    sql = output.getvalue()
    assert 'CREATE EXTENSION IF NOT EXISTS "vector"' in sql
    assert "tw_set_updated_at" in sql
    assert "INSERT INTO alembic_version" in sql
    assert "offline-secret-value" not in sql
