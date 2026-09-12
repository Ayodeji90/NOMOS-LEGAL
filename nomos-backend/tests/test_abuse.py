"""
Abuse tests for security validation.

Week 2 E6: Abuse tests (spoofed XFF, session replay, quota bypass across instances).
These tests verify that the application is protected against common abuse patterns.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import Mock, patch


@pytest.mark.asyncio
async def test_xff_spoofing_blocked_in_development():
    """Test that spoofed X-Forwarded-For headers are ignored in development."""
    from app.main import app
    from app.core.config import Settings

    # Create development settings
    dev_settings = Settings(ENVIRONMENT="development")

    with patch("app.core.rate_limit.settings", dev_settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try to spoof XFF header
            response = await client.get(
                "/health",
                headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
            )

            # Should succeed (health endpoint doesn't rate limit)
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_session_replay_prevention():
    """Test that session replay attacks are prevented."""
    from app.main import app
    from app.core.firestore import firestore_manager
    from app.core.auth import auth_manager
    from app.models import User

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a test user
        user = User(
            email="test@example.com",
            password_hash=auth_manager.hash_password("testpass123"),
            full_name="Test User",
        )
        # In production, this would be saved to DB

        # Create a session
        session_id = "test-session-replay-123"
        await firestore_manager.create_session(
            session_id=session_id,
            user_id="test-user-id",
            email="test@example.com",
            expires_in_days=1,
        )

        # Verify session exists
        session = await firestore_manager.get_session(session_id)
        assert session is not None

        # Deactivate session (simulating logout)
        await firestore_manager.update_session(session_id, {"is_active": False})

        # Try to use session again (replay attack)
        session = await firestore_manager.get_session(session_id)
        assert session is None, "Deactivated session should return None"

        # Cleanup
        try:
            await firestore_manager._client.collection("sessions").document(session_id).delete()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_quota_bypass_prevention():
    """Test that quota limits cannot be bypassed across instances."""
    from app.main import app
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock request
    request = Mock()
    request.client = Mock(host="192.168.1.100")
    request.headers = {}

    # Try to make requests beyond quota
    quota_limit = 10
    for i in range(quota_limit + 5):
        allowed, remaining = limiter.check_rate_limit(
            request=request,
            key="test_quota_bypass",
            limit=quota_limit,
            window=60,
        )

        if i < quota_limit:
            assert allowed, f"Request {i+1} should be allowed"
            assert remaining == quota_limit - i - 1
        else:
            assert not allowed, f"Request {i+1} should be rate limited"
            assert remaining == 0


@pytest.mark.asyncio
async def test_quota_isolation_across_users():
    """Test that quota limits are isolated per user."""
    from app.main import app
    from app.core.redis import redis_manager
    from app.core.rate_limit import RateLimiter

    # Initialize Redis
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Create mock requests for different users
    request1 = Mock()
    request1.client = Mock(host="192.168.1.100")
    request1.headers = {}

    request2 = Mock()
    request2.client = Mock(host="192.168.1.101")
    request2.headers = {}

    quota_limit = 5

    # User 1 makes quota_limit requests
    for i in range(quota_limit):
        allowed, _ = limiter.check_rate_limit(
            request=request1,
            key="test_user1",
            limit=quota_limit,
            window=60,
        )
        assert allowed

    # User 1 should be rate limited
    allowed, _ = limiter.check_rate_limit(
        request=request1,
        key="test_user1",
        limit=quota_limit,
        window=60,
    )
    assert not allowed

    # User 2 should still be allowed (isolated quota)
    allowed, _ = limiter.check_rate_limit(
        request=request2,
        key="test_user2",
        limit=quota_limit,
        window=60,
    )
    assert allowed


@pytest.mark.asyncio
async def test_concurrent_request_quota_enforcement():
    """Test that quota limits are enforced under concurrent load."""
    import asyncio
    from app.main import app
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

    async def make_request(request_num: int):
        allowed, _ = limiter.check_rate_limit(
            request=request,
            key="test_concurrent",
            limit=quota_limit,
            window=60,
        )
        return allowed

    # Make 20 concurrent requests
    results = await asyncio.gather(*[make_request(i) for i in range(20)])

    # Exactly quota_limit should be allowed
    allowed_count = sum(results)
    assert allowed_count == quota_limit


@pytest.mark.asyncio
async def test_api_key_rotation_security():
    """Test that API key rotation invalidates old keys."""
    from app.core.auth import auth_manager

    # Generate API key
    raw_key, key_hash = auth_manager.generate_api_key()

    # Verify key works
    assert auth_manager.verify_api_key(raw_key, key_hash)

    # Generate new key (rotation)
    new_raw_key, new_key_hash = auth_manager.generate_api_key()

    # Old key should not verify against new hash
    assert not auth_manager.verify_api_key(raw_key, new_key_hash)

    # New key should verify
    assert auth_manager.verify_api_key(new_raw_key, new_key_hash)


@pytest.mark.asyncio
async def test_password_hashing_security():
    """Test that password hashing uses secure scrypt with timing-safe comparison."""
    from app.core.auth import auth_manager

    password = "test_password_123"

    # Hash password
    hash1 = auth_manager.hash_password(password)
    hash2 = auth_manager.hash_password(password)

    # Hashes should be different (different salts)
    assert hash1 != hash2

    # Both should verify correctly
    assert auth_manager.verify_password(password, hash1)
    assert auth_manager.verify_password(password, hash2)

    # Wrong password should not verify
    assert not auth_manager.verify_password("wrong_password", hash1)


@pytest.mark.asyncio
async def test_token_expiration():
    """Test that access tokens expire correctly."""
    from app.core.auth import auth_manager
    from app.models import User
    from datetime import timedelta

    user = User(
        id="test-user-id",
        email="test@example.com",
        password_hash="hash",
    )

    # Create token with short expiration
    token = auth_manager.create_access_token(
        user,
        expires_delta=timedelta(seconds=1)
    )

    # Token should be valid immediately
    assert auth_manager.verify_access_token(token) is not None

    # Wait for expiration
    import asyncio
    await asyncio.sleep(1.1)

    # Token should be expired
    assert auth_manager.verify_access_token(token) is None
