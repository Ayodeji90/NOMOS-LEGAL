from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings


class DatabaseManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def initialize(self) -> None:
        if settings.is_production:
            poolclass = None
            pool_size = settings.DATABASE_POOL_SIZE
            max_overflow = settings.DATABASE_MAX_OVERFLOW
        else:
            poolclass = NullPool
            # NullPool doesn't use pool_size, max_overflow, pool_timeout, pool_recycle, or pool_pre_ping
            pool_size = None
            max_overflow = None

        # Prepare engine arguments
        engine_args = {
            "echo": settings.is_development,
            "poolclass": poolclass,
        }

        # Only add pool parameters if not using NullPool
        if poolclass is not NullPool:
            engine_args["pool_size"] = pool_size
            engine_args["max_overflow"] = max_overflow
            engine_args["pool_timeout"] = settings.DATABASE_POOL_TIMEOUT
            engine_args["pool_recycle"] = settings.DATABASE_POOL_RECYCLE
            engine_args["pool_pre_ping"] = True

        self._engine = create_async_engine(str(settings.DATABASE_URL), **engine_args)

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @property
    def engine(self) -> AsyncEngine:
        if not self._engine:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if not self._session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        from sqlalchemy import text

        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session
