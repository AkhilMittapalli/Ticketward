-- Ticketward: first-initialization script for the Postgres container.
--
-- Runs ONCE, when the data volume is empty, via /docker-entrypoint-initdb.d, as the
-- bootstrap superuser (POSTGRES_USER) against POSTGRES_DB. It creates the extensions the
-- schema needs (spec §10): pgcrypto, vector, citext and pg_trgm (GIN trigram search on
-- tickets.message_masked). Alembic revision 0001 re-asserts them with
-- CREATE EXTENSION IF NOT EXISTS (a no-op here), so migrations never need superuser.
--
-- To re-run it, recreate the volume: docker compose down -v (destroys local data).
-- Least-privilege roles (tw_migrator, tw_app, tw_readonly) arrive with the P4 schema.

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Defense in depth (PG15+ default): nobody but the owner may create objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
