import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self) -> None:
        self._client: Redis | None = None
        self._pool: redis.ConnectionPool | None = None

    def initialize(self, use_fakeredis: bool = False) -> None:
        if use_fakeredis:
            import fakeredis.aioredis

            self._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
            logger.info("Initialized fakeredis for testing")
            return

        self._pool = redis.ConnectionPool.from_url(
            str(settings.REDIS_URL),
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            decode_responses=True,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        logger.info("Initialized Redis connection pool")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Closed Redis connections")

    @property
    def client(self) -> Redis:
        if not self._client:
            raise RuntimeError("Redis not initialized. Call initialize() first.")
        return self._client

    async def health_check(self) -> bool:
        try:
            return await self._client.ping()
        except RedisError:
            return False

    @asynccontextmanager
    async def pipeline(self) -> AsyncGenerator["redis.client.Pipeline", None]:
        async with self._client.pipeline(transaction=True) as pipe:
            try:
                yield pipe
                await pipe.execute()
            except Exception:
                await pipe.reset()
                raise


redis_manager = RedisManager()


async def get_redis() -> Redis:
    return redis_manager.client
