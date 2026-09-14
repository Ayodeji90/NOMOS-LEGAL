"""Postgres-backed session store (cloud-neutral alternative to Firestore).

Same async API surface as ``FirestoreManager``'s session methods
(create/get/update/delete/delete_user_sessions/cleanup_expired), so the auth
layer can swap stores via the ``SESSION_STORE`` setting with no call-site
changes. Sessions live in the ``auth_sessions`` table (migration 005).

Selected via ``SESSION_STORE=postgres`` — the Azure staging path, where there
is no Firestore.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AuthSession

logger = logging.getLogger(__name__)


class PgSessionStore:
    """Session management against the ``auth_sessions`` Postgres table."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        email: str,
        expires_in_days: int | None = None,
        metadata: dict | None = None,
    ) -> dict:
        expires_in_days = expires_in_days or settings.SESSION_TTL_DAYS
        now = datetime.utcnow()
        expires_at = now + timedelta(days=expires_in_days)

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "email": email,
            "created_at": now,
            "expires_at": expires_at,
            "is_active": True,
            "metadata": metadata or {},
        }

        self._db.add(
            AuthSession(
                session_id=session_id,
                user_id=user_id,
                email=email,
                created_at=now,
                expires_at=expires_at,
                is_active=True,
                metadata_=metadata or {},
            )
        )
        await self._db.flush()
        return session_data

    async def get_session(self, session_id: str) -> dict | None:
        result = await self._db.execute(
            select(AuthSession).where(AuthSession.session_id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.is_active and row.expires_at > datetime.utcnow():
            return {
                "session_id": row.session_id,
                "user_id": row.user_id,
                "email": row.email,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "is_active": row.is_active,
                "metadata": row.metadata_ or {},
            }
        if row.is_active:
            # Mirror FirestoreManager: lazily deactivate expired sessions.
            await self.delete_session(session_id)
        return None

    async def update_session(self, session_id: str, updates: dict) -> bool:
        updates = dict(updates)
        updates["updated_at"] = datetime.utcnow()
        await self._db.execute(
            update(AuthSession).where(AuthSession.session_id == session_id).values(**updates)
        )
        return True

    async def delete_session(self, session_id: str) -> bool:
        await self._db.execute(
            delete(AuthSession).where(AuthSession.session_id == session_id)
        )
        return True

    async def delete_user_sessions(self, user_id: str) -> int:
        result = await self._db.execute(
            delete(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.is_active == True  # noqa: E712
            )
        )
        return result.rowcount or 0

    async def cleanup_expired_sessions(self) -> int:
        result = await self._db.execute(
            update(AuthSession)
            .where(
                AuthSession.expires_at < datetime.utcnow(),
                AuthSession.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )
        return result.rowcount or 0


def new_session_id() -> str:
    """Shared session-id generator (uuid4 hex, same shape as auth.py)."""
    return uuid.uuid4().hex
