"""
Test X-Forwarded-For spoofing protection.

This test verifies that:
1. In staging/prod, X-Forwarded-For is trusted (from Cloud Run)
2. In development, X-Forwarded-For is ignored
3. Spoofed X-Forwarded-For cannot bypass rate limits
"""
from unittest.mock import Mock

import pytest
from fastapi import Request

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.redis import redis_manager


@pytest.mark.asyncio
async def test_xff_trusted_in_staging():
    """Test that X-Forwarded-For is trusted in staging environment."""
    # Create staging settings
    staging_settings = Settings(ENVIRONMENT="staging")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = staging_settings

    try:
        # Create a mock request with X-Forwarded-For
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "203.0.113.42, 10.0.0.1"}
        request.client = Mock(host="192.168.1.100")

        # Should use the leftmost IP from X-Forwarded-For
        client_ip = limiter.get_client_ip(request)
        assert client_ip == "203.0.113.42", f"Expected 203.0.113.42, got {client_ip}"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_xff_ignored_in_development():
    """Test that X-Forwarded-For is ignored in development."""
    # Create development settings
    dev_settings = Settings(ENVIRONMENT="development")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = dev_settings

    try:
        # Create a mock request with X-Forwarded-For
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "203.0.113.42, 10.0.0.1"}
        request.client = Mock(host="192.168.1.100")

        # Should ignore X-Forwarded-For and use direct connection IP
        client_ip = limiter.get_client_ip(request)
        assert client_ip == "192.168.1.100", f"Expected 192.168.1.100, got {client_ip}"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_xff_spoofing_protection():
    """Test that spoofed X-Forwarded-For cannot bypass rate limits in development."""
    dev_settings = Settings(ENVIRONMENT="development")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = dev_settings

    try:
        # Create two mock requests with different X-Forwarded-For but same client IP
        request1 = Mock(spec=Request)
        request1.headers = {"X-Forwarded-For": "203.0.113.42"}
        request1.client = Mock(host="192.168.1.100")

        request2 = Mock(spec=Request)
        request2.headers = {"X-Forwarded-For": "203.0.113.99"}  # Different spoofed IP
        request2.client = Mock(host="192.168.1.100")  # Same real IP

        # Both should resolve to the same IP (ignoring X-Forwarded-For)
        ip1 = limiter.get_client_ip(request1)
        ip2 = limiter.get_client_ip(request2)

        assert ip1 == ip2, "X-Forwarded-For spoofing should be prevented in development"
        assert ip1 == "192.168.1.100", f"Expected 192.168.1.100, got {ip1}"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_rate_limit_with_xff_in_staging():
    """Test that rate limiting uses X-Forwarded-For IP in staging."""
    staging_settings = Settings(ENVIRONMENT="staging")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = staging_settings

    try:
        # Create requests from the same real IP (via X-Forwarded-For)
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "203.0.113.42"}
        request.client = Mock(host="10.0.0.1")

        # Verify the IP used for rate limiting is from X-Forwarded-For
        client_ip = limiter.get_client_ip(request)
        assert client_ip == "203.0.113.42", "Should use X-Forwarded-For IP for rate limiting"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_different_xff_ips_separate_limits_in_staging():
    """Test that different X-Forwarded-For IPs are treated separately."""
    staging_settings = Settings(ENVIRONMENT="staging")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = staging_settings

    try:
        # Request from IP1
        request1 = Mock(spec=Request)
        request1.headers = {"X-Forwarded-For": "203.0.113.42"}
        request1.client = Mock(host="10.0.0.1")
        ip1 = limiter.get_client_ip(request1)

        # Request from IP2
        request2 = Mock(spec=Request)
        request2.headers = {"X-Forwarded-For": "203.0.113.99"}
        request2.client = Mock(host="10.0.0.1")
        ip2 = limiter.get_client_ip(request2)

        # Verify they are treated as different IPs
        assert ip1 == "203.0.113.42", "IP1 should be from X-Forwarded-For"
        assert ip2 == "203.0.113.99", "IP2 should be from X-Forwarded-For"
        assert ip1 != ip2, "Different X-Forwarded-For IPs should be treated separately"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_xff_multiple_ips_parsing():
    """Test that multiple IPs in X-Forwarded-For are parsed correctly."""
    staging_settings = Settings(ENVIRONMENT="staging")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = staging_settings

    try:
        # Cloud Run format: client, proxy1, proxy2
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "203.0.113.42, 10.0.0.1, 10.0.0.2"}
        request.client = Mock(host="192.168.1.100")

        # Should use the leftmost (client) IP
        client_ip = limiter.get_client_ip(request)
        assert client_ip == "203.0.113.42", f"Expected 203.0.113.42, got {client_ip}"
    finally:
        rate_limit_module.settings = original_settings


@pytest.mark.asyncio
async def test_xff_whitespace_handling():
    """Test that whitespace in X-Forwarded-For is handled correctly."""
    staging_settings = Settings(ENVIRONMENT="staging")
    redis_manager.initialize(use_fakeredis=True)
    limiter = RateLimiter(redis_manager.client)

    # Temporarily replace settings
    import app.core.rate_limit as rate_limit_module
    original_settings = rate_limit_module.settings
    rate_limit_module.settings = staging_settings

    try:
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "  203.0.113.42  ,  10.0.0.1  "}
        request.client = Mock(host="192.168.1.100")

        # Should strip whitespace and use leftmost IP
        client_ip = limiter.get_client_ip(request)
        assert client_ip == "203.0.113.42", f"Expected 203.0.113.42, got {client_ip}"
    finally:
        rate_limit_module.settings = original_settings
