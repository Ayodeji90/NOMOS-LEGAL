import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import settings

logger = logging.getLogger(__name__)


class FirestoreManager:
    def __init__(self) -> None:
        self._client: AsyncClient | None = None

    def initialize(self, use_emulator: bool = False) -> None:
        if use_emulator:
            import os

            os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8081"
            self._client = firestore.AsyncClient(project=settings.FIRESTORE_PROJECT_ID)
            logger.info("Initialized Firestore emulator client")
            return

        self._client = firestore.AsyncClient(
            project=settings.FIRESTORE_PROJECT_ID,
            database=settings.FIRESTORE_DATABASE,
        )
        logger.info("Initialized Firestore client")

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
        logger.info("Closed Firestore client")

    @property
    def client(self) -> AsyncClient:
        if not self._client:
            raise RuntimeError("Firestore not initialized. Call initialize() first.")
        return self._client

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[firestore.AsyncTransaction, None]:
        async with self._client.transaction() as tx:
            yield tx

    # Session management
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        email: str,
        expires_in_days: int = None,
        metadata: dict = None,
    ) -> dict:
        expires_in_days = expires_in_days or settings.SESSION_TTL_DAYS
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "is_active": True,
            "metadata": metadata or {},
        }

        await self._client.collection("sessions").document(session_id).set(session_data)
        return session_data

    async def get_session(self, session_id: str) -> dict | None:
        doc = await self._client.collection("sessions").document(session_id).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("is_active") and data.get("expires_at", datetime.min) > datetime.utcnow():
                return data
            elif data.get("is_active"):
                await self.delete_session(session_id)
        return None

    async def update_session(self, session_id: str, updates: dict) -> bool:
        updates["updated_at"] = datetime.utcnow()
        result = await self._client.collection("sessions").document(session_id).update(updates)
        return result is not None

    async def delete_session(self, session_id: str) -> bool:
        await self._client.collection("sessions").document(session_id).delete()
        return True

    async def delete_user_sessions(self, user_id: str) -> int:
        sessions = (
            await self._client.collection("sessions")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("is_active", "==", True))
            .stream()
        )
        count = 0
        async for session in sessions:
            await session.reference.delete()
            count += 1
        return count

    async def cleanup_expired_sessions(self) -> int:
        expired = (
            await self._client.collection("sessions")
            .where(filter=FieldFilter("expires_at", "<", datetime.utcnow()))
            .where(filter=FieldFilter("is_active", "==", True))
            .stream()
        )
        count = 0
        async for session in expired:
            await session.reference.update({"is_active": False})
            count += 1
        return count


firestore_manager = FirestoreManager()


async def get_firestore() -> AsyncClient:
    return firestore_manager.client
