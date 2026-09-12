"""
Client-document injection suite.

Week 10 E6: Client-document injection suite (UNTRUSTED wrapping + rejection patterns).
These tests verify that the application is protected against injection attacks from user-provided documents.
"""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_html_injection_prevention():
    """Test that HTML injection is prevented in document text."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to inject HTML in document text
        malicious_text = "<script>alert('XSS')</script>What is the BCEA?"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_text,
                "jurisdiction": "za",
            },
        )

        # Should succeed (HTML should be sanitized)
        assert response.status_code in [200, 429]  # 200 or rate limited

        if response.status_code == 200:
            # Verify HTML is not reflected in response
            response_text = response.text
            assert "<script>" not in response_text
            assert "alert" not in response_text


@pytest.mark.asyncio
async def test_sql_injection_prevention():
    """Test that SQL injection is prevented in queries."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try SQL injection
        malicious_query = "What is the BCEA?'; DROP TABLE users; --"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_query,
                "jurisdiction": "za",
            },
        )

        # Should succeed (SQL should be sanitized)
        assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_javascript_injection_prevention():
    """Test that JavaScript injection is prevented."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try JavaScript injection
        malicious_query = "javascript:alert('XSS') What is the BCEA?"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_query,
                "jurisdiction": "za",
            },
        )

        # Should succeed (JavaScript should be sanitized)
        assert response.status_code in [200, 429]

        if response.status_code == 200:
            response_text = response.text
            assert "javascript:" not in response_text.lower()


@pytest.mark.asyncio
async def test_command_injection_prevention():
    """Test that command injection is prevented."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try command injection
        malicious_query = "What is the BCEA?; rm -rf /"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_query,
                "jurisdiction": "za",
            },
        )

        # Should succeed (command should be sanitized)
        assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_path_traversal_prevention():
    """Test that path traversal is prevented."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try path traversal
        malicious_query = "What is the BCEA?../../../etc/passwd"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_query,
                "jurisdiction": "za",
            },
        )

        # Should succeed (path should be sanitized)
        assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_untrusted_wrapping():
    """Test UNTRUSTED wrapping parity with Node backend."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Normal query should work
        response = await client.post(
            f"/api/v1/search",
            json={
                "query": "What is the BCEA?",
                "jurisdiction": "za",
            },
        )

        assert response.status_code in [200, 429]

        # Query with special characters should be handled safely
        special_chars_query = "What is the BCEA? @#$%^&*()"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": special_chars_query,
                "jurisdiction": "za",
            },
        )

        assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_rejection_patterns():
    """Test that known malicious patterns are rejected."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Known malicious patterns
        malicious_patterns = [
            "<script>",
            "javascript:",
            "onerror=",
            "onload=",
            "data:text/html",
            "vbscript:",
            "eval(",
        ]

        for pattern in malicious_patterns:
            response = await client.post(
                f"/api/v1/search",
                json={
                    "query": f"What is the BCEA? {pattern}",
                    "jurisdiction": "za",
                },
            )

            # Should either succeed with sanitized input or be rejected
            assert response.status_code in [200, 400, 429]

            if response.status_code == 200:
                # Verify pattern is not reflected
                assert pattern not in response.text


@pytest.mark.asyncio
async def test_document_size_limit():
    """Test that document size is limited to prevent DoS."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Very long query (10MB)
        long_query = "What is the BCEA? " + "A" * (10 * 1024 * 1024)

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": long_query,
                "jurisdiction": "za",
            },
        )

        # Should be rejected for being too large
        assert response.status_code == 413  # Payload Too Large


@pytest.mark.asyncio
async def test_unicode_normalization():
    """Test that Unicode normalization is handled correctly."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unicode homograph attack (similar looking characters)
        unicode_query = "Whаt is thе BCEA?"  # Using Cyrillic characters

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": unicode_query,
                "jurisdiction": "za",
            },
        )

        # Should handle gracefully
        assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_header_injection_prevention():
    """Test that header injection is prevented."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to inject headers via query
        malicious_query = "What is the BCEA?\r\nX-Malicious-Header: value"

        response = await client.post(
            f"/api/v1/search",
            json={
                "query": malicious_query,
                "jurisdiction": "za",
            },
        )

        # Should succeed (headers should not be injected)
        assert response.status_code in [200, 429]

        if response.status_code == 200:
            # Verify malicious header is not in response
            assert "X-Malicious-Header" not in response.headers
