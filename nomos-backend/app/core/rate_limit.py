import logging
import time
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_at: int
    limit: int
    retry_after: int | None = None


class RateLimiter:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def get_client_ip(self, request: Request) -> str:
        """
        Get the real client IP, respecting Cloud Run's proxy configuration.

        In Cloud Run, the real client IP is the leftmost IP in X-Forwarded-For.
        We only trust X-Forwarded-For when running in staging/prod (behind trusted proxy).
        """
        # In staging/prod, trust X-Forwarded-For from Cloud Run's load balancer
        if settings.use_real_redis:  # Indicates we're in staging/prod
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                # Cloud Run puts the real client IP first
                return xff.split(",")[0].strip()

        # In development, use direct connection IP
        return request.client.host if request.client else "unknown"

    def get_rate_limit_key(self, identifier: str, window: str) -> str:
        return f"ratelimit:{window}:{identifier}"

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        key = self.get_rate_limit_key(identifier, f"{window_seconds}s")
        now = int(time.time())
        window_start = now - window_seconds

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()

        current_count = results[1]
        remaining = max(0, limit - current_count - 1)
        allowed = current_count < limit
        reset_at = now + window_seconds

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
            retry_after=window_seconds if not allowed else None,
        )

    async def check_multiple_windows(
        self,
        identifier: str,
        limits: list[tuple[int, int]],  # [(limit, window_seconds), ...]
    ) -> list[RateLimitResult]:
        results = []
        for limit, window in limits:
            result = await self.check_rate_limit(identifier, limit, window)
            results.append(result)
            if not result.allowed:
                break
        return results


class QuotaManager:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def get_quota_key(self, user_id: str, quota_type: str) -> str:
        today = time.strftime("%Y-%m-%d")
        return f"quota:{quota_type}:{user_id}:{today}"

    async def check_quota(
        self,
        user_id: str,
        quota_type: str,
        limit: int,
    ) -> RateLimitResult:
        key = self.get_quota_key(user_id, quota_type)
        now = int(time.time())

        current = await self.redis.get(key)
        current_count = int(current) if current else 0
        remaining = max(0, limit - current_count)
        allowed = current_count < limit

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=int(
                time.mktime(time.strptime(time.strftime("%Y-%m-%d 23:59:59"), "%Y-%m-%d %H:%M:%S"))
            ),
            limit=limit,
            retry_after=86400 if not allowed else None,
        )

    async def consume_quota(self, user_id: str, quota_type: str) -> int:
        key = self.get_quota_key(user_id, quota_type)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        results = await pipe.execute()
        return results[0]

    async def get_quota_status(self, user_id: str) -> dict:
        queries_key = self.get_quota_key(user_id, "queries")
        writer_key = self.get_quota_key(user_id, "writer")

        queries_used = int(await self.redis.get(queries_key) or 0)
        writer_used = int(await self.redis.get(writer_key) or 0)

        return {
            "queries": {
                "used": queries_used,
                "limit": settings.QUOTA_DAILY_QUERIES,
                "remaining": max(0, settings.QUOTA_DAILY_QUERIES - queries_used),
            },
            "writer": {
                "used": writer_used,
                "limit": settings.QUOTA_DAILY_WRITER_CALLS,
                "remaining": max(0, settings.QUOTA_DAILY_WRITER_CALLS - writer_used),
            },
        }


rate_limiter: RateLimiter | None = None
quota_manager: QuotaManager | None = None


def get_rate_limiter() -> RateLimiter:
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = RateLimiter(redis_manager.client)
    return rate_limiter


def get_quota_manager() -> QuotaManager:
    global quota_manager
    if quota_manager is None:
        quota_manager = QuotaManager(redis_manager.client)
    return quota_manager
