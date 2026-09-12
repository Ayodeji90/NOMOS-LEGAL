import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_readiness_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "ready" in data


@pytest.mark.asyncio
async def test_liveness_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/live")
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_api_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]


@pytest.mark.asyncio
async def test_search_endpoint_exists() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/search",
            json={"query": "test query", "jurisdiction": "za"},
        )
    # Should return 422 (validation error for missing auth) or 401 (unauthorized)
    # or 200 with not_implemented response
    assert response.status_code in [200, 401, 422]


@pytest.mark.asyncio
async def test_draft_endpoint_exists() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/draft",
            json={"instruction": "test", "documentType": "clause", "jurisdiction": "za"},
        )
    assert response.status_code in [200, 401, 422]


@pytest.mark.asyncio
async def test_review_endpoint_exists() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/review",
            json={"documentText": "test document", "jurisdiction": "za"},
        )
    assert response.status_code in [200, 401, 422]


@pytest.mark.asyncio
async def test_improve_endpoint_exists() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/improve",
            json={"documentText": "test", "instruction": "improve", "jurisdiction": "za"},
        )
    assert response.status_code in [200, 401, 422]


@pytest.mark.asyncio
async def test_auth_register_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "password123", "full_name": "Test User"},
        )
    # May fail due to no database in test, but endpoint should exist
    assert response.status_code in [201, 400, 500, 503]


@pytest.mark.asyncio
async def test_auth_login_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/login",
            data={"username": "test@example.com", "password": "password123"},
        )
    assert response.status_code in [200, 400, 401, 500, 503]


# Auth tests (require database)
# @pytest.mark.asyncio
# async def test_full_auth_flow():
#     pass
