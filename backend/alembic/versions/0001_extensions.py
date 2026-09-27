"""Guard required extensions and create the shared updated_at trigger function.

Revision ID: 0001
Revises:
Create Date: 2026-09-26

Extensions (spec §10): pgcrypto (gen_random_uuid, digests), vector (pgvector
embeddings), citext (case-insensitive e-mail) and pg_trgm (GIN trigram index on
tickets.message_masked, spec §10 tickets table).

Ownership model: the extensions are created by ``infra/postgres/init.sql`` at first
database initialization, running as the bootstrap superuser. This revision only guards
them with ``CREATE EXTENSION IF NOT EXISTS`` (a no-op when present, so a non-superuser
migrator role works) and does not drop them on downgrade: they belong to the
infrastructure, not to the schema history. No business tables yet; they arrive with
the P4 core schema. Static DDL only.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tw_set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "COMMENT ON FUNCTION tw_set_updated_at() IS "
        "'Sets updated_at on UPDATE; attach with BEFORE UPDATE ... FOR EACH ROW.'"
    )


def downgrade() -> None:
    # Extensions are infrastructure-owned (init.sql); only schema objects are removed.
    op.execute("DROP FUNCTION IF EXISTS tw_set_updated_at()")
