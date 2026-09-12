import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Ensure app is importable
sys.path.insert(0, str(ROOT))

# Anchor cwd to the backend dir: synonym-dict and fixture loaders use
# relative paths, so tests pass regardless of the invoking directory
# (matches CI, which runs pytest from inside nomos-backend/).
os.chdir(ROOT)

# Set test environment variables before importing app modules
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/nomos_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test-project")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-min-32-chars-long")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENABLE_REQUEST_LOGGING", "false")
os.environ.setdefault("LOG_PROMPTS", "false")
os.environ.setdefault("LOG_RESPONSES", "false")


@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


class _MemorySessionStore:
    """In-memory stand-in for Firestore sessions (tests only).

    Mirrors FirestoreManager return shapes (is_active/expires_at logic)
    so API tests exercise real endpoint code without an emulator.
    """

    def __init__(self) -> None:
        self.store: dict = {}

    async def create_session(self, session_id, user_id, email, expires_in_days=None, metadata=None):
        from datetime import datetime, timedelta

        from app.core.config import settings

        data = {
            "session_id": session_id,
            "user_id": user_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow()
            + timedelta(days=expires_in_days or settings.SESSION_TTL_DAYS),
            "is_active": True,
            "metadata": metadata or {},
        }
        self.store[session_id] = data
        return data

    async def get_session(self, session_id):
        from datetime import datetime

        data = self.store.get(session_id)
        if data and data.get("is_active"):
            if data.get("expires_at") and data["expires_at"] > datetime.utcnow():
                return data
            await self.delete_session(session_id)
        return None

    async def update_session(self, session_id, updates):
        from datetime import datetime

        if session_id not in self.store:
            return False
        self.store[session_id].update(updates or {})
        self.store[session_id]["updated_at"] = datetime.utcnow()
        return True

    async def delete_session(self, session_id):
        self.store.pop(session_id, None)
        return True

    async def delete_user_sessions(self, user_id):
        doomed = [
            k for k, v in self.store.items() if v.get("user_id") == user_id and v.get("is_active")
        ]
        for k in doomed:
            del self.store[k]
        return len(doomed)


@pytest.fixture(scope="session", autouse=True)
def _test_services():
    """Init managers once: real Postgres, fakeredis, stubbed sessions.

    ASGITransport never runs lifespan, so without this every endpoint
    test fails with 'not initialized'. Live-service URLs come from env
    (DATABASE_URL/REDIS_URL); CI provides them via service containers.
    """
    from app.core.firestore import firestore_manager
    from app.core.redis import redis_manager
    from app.db.session import db_manager

    db_manager.initialize()
    redis_manager.initialize(use_fakeredis=True)

    store = _MemorySessionStore()
    firestore_manager.create_session = store.create_session
    firestore_manager.get_session = store.get_session
    firestore_manager.update_session = store.update_session
    firestore_manager.delete_session = store.delete_session
    firestore_manager.delete_user_sessions = store.delete_user_sessions
    yield
