"""
Shared pytest fixtures.

database.service raises at IMPORT TIME if DATABASE_URL isn't set (by design
— Argus has no local-file fallback). That means even the pure-logic tests
(test_serializer, test_whitelist) can't be collected without *some* value
present. We set a harmless placeholder here so imports succeed; tests that
actually need a live connection use the `pg` fixture below, which skips
itself unless DATABASE_URL points at a real, reachable Postgres.

Safety: DB-backed tests never touch pre-existing rows. Every row they create
uses a `TEST-PYTEST-` prefixed id and is deleted in a fixture teardown, pass
or fail, so pointing DATABASE_URL at the live Supabase database used by the
deployed HF Space is safe — tests are additive-then-cleaned, never
destructive to real alerts/decisions/whitelist entries.
"""
import os
import uuid

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql://placeholder:placeholder@localhost:5432/placeholder"
)


def _db_reachable(dsn: str) -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def pg_available() -> bool:
    """True only if DATABASE_URL is a real, reachable Postgres (not the placeholder)."""
    return _db_reachable(os.environ["DATABASE_URL"])


@pytest.fixture
def pg(pg_available):
    """The database.service module, with schema/migrations applied. Skips if no live DB."""
    if not pg_available:
        pytest.skip(
            "DATABASE_URL is not set to a reachable Postgres — "
            "export it (see .env.example) to run DB-backed tests."
        )
    from database import service as db
    db.init_db()
    return db


@pytest.fixture
def test_id():
    """A unique TEST-PYTEST- prefixed id, safe to insert into a live/shared DB."""
    return f"TEST-PYTEST-{uuid.uuid4().hex[:12]}"
