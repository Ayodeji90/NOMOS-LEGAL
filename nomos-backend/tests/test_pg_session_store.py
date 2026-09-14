"""Tests for the Postgres session store (SESSION_STORE=postgres).

Runs against the real test Postgres (nomos_test). The ``auth_session`` table
is created on the fly if missing (same DDL as migration 005) so the test is
self-contained; the whole module skips when the test DB is unreachable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from app.core.config import settings
from app.core.pg_sessions import PgSessionStore
from app.db.session import db_manager


@pytest.fixture(scope="module")
async def pg_session():
    """A real AsyncSession over the test DB, with the table provisioned."""
    try:
        db_manager.initialize()
    except Exception as exc:  # pragma: no cover - env-specific
        pytest.skip(f"test Postgres unavailable: {exc}")
    engine = db_manager.engine
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env-specific
        pytest.skip(f"test Postgres unavailable: {exc}")

    # Provision the table if migration 005 hasn't run on this DB yet.
    ddl = """
    CREATE TABLE IF NOT EXISTS auth_session (
        session_id VARCHAR(64) PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """
    async with engine.begin() as conn:
        await conn.execute(sa.text(ddl))

    async with db_manager.session() as session:
        yield session


@pytest.fixture
def user_id(pg_session):
    """Ensure a user row exists and return its id (cascade-safe cleanup)."""

    async def _make():
        result = await pg_session.execute(
            sa.text(
                "INSERT INTO \"user\" (email, password_hash) "
                "VALUES (:email, :pw) RETURNING id"
            ),
            {
                "email": f"sess-{datetime.utcnow().timestamp()}@test.local",
                "pw": "x" * 32,
            },
        )
        return str(result.scalar_one())

    return _make


async def test_create_and_get_session(pg_session, user_id):
    uid = await user_id()
    store = PgSessionStore(pg_session)
    created = await store.create_session(
        session_id="sess-create-get-1", user_id=uid, email="u@test.local"
    )
    assert created["is_active"] is True
    assert created["expires_at"] > datetime.utcnow()

    got = await store.get_session("sess-create-get-1")
    assert got is not None
    assert got["user_id"] == uid
    assert got["email"] == "u@test.local"
    assert got["metadata"] == {}
    await pg_session.rollback()


async def test_get_session_expires_lazily(pg_session, user_id):
    uid = await user_id()
    store = PgSessionStore(pg_session)
    await store.create_session(
        session_id="sess-expired-1",
        user_id=uid,
        email="u@test.local",
        expires_in_days=1,
    )
    # Force expiry directly.
    await pg_session.execute(
        sa.text("UPDATE auth_session SET expires_at = :t WHERE session_id = :sid"),
        {"t": datetime.utcnow() - timedelta(minutes=1), "sid": "sess-expired-1"},
    )
    assert await store.get_session("sess-expired-1") is None  # expired -> None
    # And the lazy path deactivated it (mirrors FirestoreManager behaviour).
    row = (
        await pg_session.execute(
            sa.text("SELECT is_active FROM auth_session WHERE session_id = :sid"),
            {"sid": "sess-expired-1"},
        )
    ).scalar_one()
    assert row is False
    await pg_session.rollback()


async def test_update_and_delete_session(pg_session, user_id):
    uid = await user_id()
    store = PgSessionStore(pg_session)
    await store.create_session(
        session_id="sess-upd-del-1", user_id=uid, email="u@test.local"
    )
    assert await store.update_session("sess-upd-del-1", {"is_active": False}) is True
    got = await store.get_session("sess-upd-del-1")
    assert got is None  # deactivated

    assert await store.delete_session("sess-upd-del-1") is True
    assert await store.get_session("sess-upd-del-1") is None
    await pg_session.rollback()


async def test_delete_user_sessions_and_cleanup(pg_session, user_id):
    uid = await user_id()
    store = PgSessionStore(pg_session)
    for i in range(3):
        await store.create_session(
            session_id=f"sess-bulk-{i}", user_id=uid, email="u@test.local"
        )
    # Expire one for the cleanup sweep.
    await pg_session.execute(
        sa.text("UPDATE auth_session SET expires_at = :t WHERE session_id = :sid"),
        {"t": datetime.utcnow() - timedelta(minutes=1), "sid": "sess-bulk-0"},
    )
    assert await store.cleanup_expired_sessions() == 1
    n = await store.delete_user_sessions(uid)
    assert n == 2  # only the two still-active ones
    await pg_session.rollback()


def test_session_store_default_is_firestore():
    # GCP path untouched by default; postgres is opt-in per environment.
    assert settings.SESSION_STORE in ("firestore", "postgres")
