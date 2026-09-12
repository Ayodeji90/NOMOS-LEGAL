"""
Quota/limits per-corpus soak test.

Week 6 E6: Quota/limits per-corpus soak test.
This test verifies that rate limiting and quota enforcement work correctly under sustained load for different corpora (ZA and NG).
"""
import asyncio
import time
from httpx import ASGITransport, AsyncClient
from unittest.mock import Mock

import pytest


@pytest.mark.asyncio
async def test_quota_enforcement_per_corpus():
    """Test that quota limits are enforced per corpus (ZA vs NG)."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock requests for different corpora
    request_za = Mock()
    request_za.client = Mock(host="192.168.1.100")
    request_za.headers = {}

    request_ng = Mock()
    request_ng.client = Mock(host="192.168.1.101")
    request_ng.headers = {}

    quota_limit = 5

    # ZA corpus: make quota_limit requests
    for i in range(quota_limit):
        allowed, _ = limiter.check_rate_limit(
            request=request_za,
            key="quota_za",
            limit=quota_limit,
            window=60,
        )
        assert allowed, f"ZA request {i+1} should be allowed"

    # ZA corpus: should be rate limited
    allowed, _ = limiter.check_rate_limit(
        request=request_za,
        key="quota_za",
        limit=quota_limit,
        window=60,
    )
    assert not allowed, "ZA should be rate limited"

    # NG corpus: should still be allowed (separate quota)
    for i in range(quota_limit):
        allowed, _ = limiter.check_rate_limit(
            request=request_ng,
            key="quota_ng",
            limit=quota_limit,
            window=60,
        )
        assert allowed, f"NG request {i+1} should be allowed"

    # NG corpus: should be rate limited
    allowed, _ = limiter.check_rate_limit(
        request=request_ng,
        key="quota_ng",
        limit=quota_limit,
        window=60,
    )
    assert not allowed, "NG should be rate limited"


@pytest.mark.asyncio
async def test_sustained_load_quota_enforcement():
    """Test quota enforcement under sustained load (soak test)."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock request
    request = Mock()
    request.client = Mock(host="192.168.1.100")
    request.headers = {}

    quota_limit = 10
    window = 60  # 60 seconds
    total_requests = 100

    async def make_request(request_num: int):
        allowed, remaining = limiter.check_rate_limit(
            request=request,
            key="soak_test",
            limit=quota_limit,
            window=window,
        )
        return allowed, remaining

    # Make requests over time
    allowed_count = 0
    rate_limited_count = 0

    for i in range(total_requests):
        allowed, remaining = await make_request(i)
        if allowed:
            allowed_count += 1
        else:
            rate_limited_count += 1

        # Small delay between requests
        await asyncio.sleep(0.1)

    # Verify quota was enforced
    assert allowed_count == quota_limit, f"Expected {quota_limit} allowed requests, got {allowed_count}"
    assert rate_limited_count == total_requests - quota_limit


@pytest.mark.asyncio
async def test_quota_window_reset():
    """Test that quota resets after window expires."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock request
    request = Mock()
    request.client = Mock(host="192.168.1.100")
    request.headers = {}

    quota_limit = 5
    window = 2  # 2 seconds for testing

    # Exhaust quota
    for i in range(quota_limit):
        allowed, _ = limiter.check_rate_limit(
            request=request,
            key="reset_test",
            limit=quota_limit,
            window=window,
        )
        assert allowed

    # Should be rate limited
    allowed, _ = limiter.check_rate_limit(
        request=request,
        key="reset_test",
        limit=quota_limit,
        window=window,
    )
    assert not allowed

    # Wait for window to expire
    await asyncio.sleep(window + 0.5)

    # Should be allowed again
    allowed, _ = limiter.check_rate_limit(
        request=request,
        key="reset_test",
        limit=quota_limit,
        window=window,
    )
    assert allowed


@pytest.mark.asyncio
async def test_concurrent_quota_enforcement():
    """Test quota enforcement under concurrent load."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock request
    request = Mock()
    request.client = Mock(host="192.168.1.100")
    request.headers = {}

    quota_limit = 20
    concurrent_requests = 50

    async def make_request(request_num: int):
        allowed, _ = limiter.check_rate_limit(
            request=request,
            key="concurrent_test",
            limit=quota_limit,
            window=60,
        )
        return allowed

    # Make concurrent requests
    results = await asyncio.gather(*[make_request(i) for i in range(concurrent_requests)])

    # Exactly quota_limit should be allowed
    allowed_count = sum(results)
    assert allowed_count == quota_limit, f"Expected {quota_limit} allowed, got {allowed_count}"


@pytest.mark.asyncio
async def test_quota_isolation_by_user_and_corpus():
    """Test that quotas are isolated by both user and corpus."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock requests
    request_user1_za = Mock()
    request_user1_za.client = Mock(host="192.168.1.100")
    request_user1_za.headers = {}

    request_user1_ng = Mock()
    request_user1_ng.client = Mock(host="192.168.1.100")
    request_user1_ng.headers = {}

    request_user2_za = Mock()
    request_user2_za.client = Mock(host="192.168.1.101")
    request_user2_za.headers = {}

    quota_limit = 3

    # User 1, ZA: exhaust quota
    for i in range(quota_limit):
        allowed, _ = limiter.check_rate_limit(
            request=request_user1_za,
            key="user1_za",
            limit=quota_limit,
            window=60,
        )
        assert allowed

    # User 1, ZA: should be rate limited
    allowed, _ = limiter.check_rate_limit(
        request=request_user1_za,
        key="user1_za",
        limit=quota_limit,
        window=60,
    )
    assert not allowed

    # User 1, NG: should be allowed (different corpus)
    allowed, _ = limiter.check_rate_limit(
        request=request_user1_ng,
        key="user1_ng",
        limit=quota_limit,
        window=60,
    )
    assert allowed

    # User 2, ZA: should be allowed (different user)
    allowed, _ = limiter.check_rate_limit(
        request=request_user2_za,
        key="user2_za",
        limit=quota_limit,
        window=60,
    )
    assert allowed


@pytest.mark.asyncio
async def test_quota_exhaustion_recovery():
    """Test that system recovers gracefully when quota is exhausted."""
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock request
    request = Mock()
    request.client = Mock(host="192.168.1.100")
    request.headers = {}

    quota_limit = 5

    # Exhaust quota
    for i in range(quota_limit + 10):
        allowed, remaining = limiter.check_rate_limit(
            request=request,
            key="recovery_test",
            limit=quota_limit,
            window=60,
        )

        if i < quota_limit:
            assert allowed, f"Request {i+1} should be allowed"
            assert remaining == quota_limit - i - 1
        else:
            assert not allowed, f"Request {i+1} should be rate limited"
            assert remaining == 0

    # Verify Redis is still responsive
    # (In production, this would check Redis health)
    assert redis_manager.client is not None
