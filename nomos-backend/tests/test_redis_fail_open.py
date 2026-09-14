"""REDIS_FAIL_OPEN staging flag: rate limiting / quotas fail open when Redis is down.

Guarantees under the flag:
- Redis outage never raises out of the limiter/quota path (search stays up)
- Outages are logged as warnings
Guarantees without the flag (default):
- Redis errors propagate (fail closed) — production behavior unchanged
"""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import settings
from app.core.rate_limit import QuotaManager, RateLimiter


def _make_limiter() -> RateLimiter:
    limiter = RateLimiter(AsyncMock())
    limiter.redis.pipeline = unittest_pipeline_mock
    return limiter


def _make_quota() -> QuotaManager:
    return QuotaManager(AsyncMock())


async def _pipeline_raises(*args, **kwargs):
    raise RedisConnectionError("Connection refused")


class _FailingPipeline:
    """Async context manager: any command is a no-op, execute() raises."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self):
        raise RedisConnectionError("Connection refused")


def unittest_pipeline_mock(transaction=True):
    return _FailingPipeline()


async def test_rate_limit_fails_open_when_flag_set(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_FAIL_OPEN", True)
    limiter = _make_limiter()

    result = await limiter.check_rate_limit("1.2.3.4", limit=30, window_seconds=60)

    assert result.allowed is True
    assert result.remaining == 30


async def test_rate_limit_fails_closed_by_default():
    # Default REDIS_FAIL_OPEN=False: outage must raise, not silently allow.
    limiter = _make_limiter()

    with pytest.raises(RedisConnectionError):
        await limiter.check_rate_limit("1.2.3.4", limit=30, window_seconds=60)


async def test_quota_status_fails_open_when_flag_set(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_FAIL_OPEN", True)
    quota = _make_quota()

    quota.redis.get = AsyncMock(side_effect=RedisConnectionError("Connection refused"))

    status = await quota.get_quota_status("user-1")

    assert status["queries"]["used"] == 0
    assert status["queries"]["remaining"] == settings.QUOTA_DAILY_QUERIES


async def test_quota_status_fails_closed_by_default():
    quota = _make_quota()
    quota.redis.get = AsyncMock(side_effect=RedisConnectionError("Connection refused"))

    with pytest.raises(RedisConnectionError):
        await quota.get_quota_status("user-1")


async def test_consume_quota_fails_open_when_flag_set(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_FAIL_OPEN", True)
    quota = _make_quota()
    quota.redis.pipeline = unittest_pipeline_mock

    used = await quota.consume_quota("user-1", "queries")

    assert used == 0


async def test_consume_quota_fails_closed_by_default():
    quota = _make_quota()
    quota.redis.pipeline = unittest_pipeline_mock

    with pytest.raises(RedisConnectionError):
        await quota.consume_quota("user-1", "queries")
