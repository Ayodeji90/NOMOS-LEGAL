"""
Shadow traffic middleware for duplicating production queries to staging.

Week 3 E1: Duplicate 10% of prod queries to staging for comparison without
user impact. This allows A/B testing between v1 (lexical) and v2 (hybrid)
retrieval paths before full rollout.

The shadow traffic is:
- Sampled at 10% (configurable via SHADOW_TRAFFIC_SAMPLE_RATE)
- Sent asynchronously to staging endpoint
- Does not affect production response
- Logged for comparison analysis
"""
import asyncio
import hashlib
import logging
import random
from typing import Any

import httpx
from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)


class ShadowTrafficMiddleware:
    """Middleware to duplicate a sample of production requests to staging."""

    def __init__(
        self,
        sample_rate: float = 0.1,
        staging_url: str | None = None,
        timeout: float = 5.0,
    ):
        self.sample_rate = sample_rate
        self.staging_url = staging_url or settings.SHADOW_TRAFFIC_STAGING_URL
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        logger.info(
            "Shadow traffic middleware initialized",
            sample_rate=sample_rate,
            staging_url=self.staging_url,
        )

    def _should_sample(self, request: Request) -> bool:
        """
        Determine if request should be sampled for shadow traffic.

        Uses deterministic sampling based on request hash to ensure
        consistent sampling for the same request.
        """
        if not self.staging_url or settings.ENVIRONMENT != "production":
            return False

        # Create hash from request path + body + headers
        hash_input = f"{request.url.path}{request.url.query}".encode()
        hash_digest = int(hashlib.md5(hash_input).hexdigest(), 16)
        sample_threshold = int(self.sample_rate * (2**32))

        return hash_digest < sample_threshold

    async def _send_shadow_request(
        self, method: str, path: str, query: str, headers: dict[str, str], body: bytes | None
    ) -> None:
        """Send shadow request to staging asynchronously."""
        if not self.staging_url:
            return

        try:
            url = f"{self.staging_url}{path}?{query}" if query else f"{self.staging_url}{path}"
            # Remove host header to avoid conflicts
            shadow_headers = {k: v for k, v in headers.items() if k.lower() != "host"}
            # Add shadow traffic marker
            shadow_headers["X-Shadow-Traffic"] = "true"

            response = await self.client.request(
                method=method,
                url=url,
                headers=shadow_headers,
                content=body,
            )

            logger.debug(
                "Shadow request sent",
                method=method,
                path=path,
                status_code=response.status_code,
            )
        except Exception as e:
            logger.warning(
                "Shadow request failed",
                method=method,
                path=path,
                error=str(e),
            )

    async def __call__(self, request: Request, call_next):
        """Process request and optionally send shadow copy to staging."""
        # Only shadow POST requests to /api/v1/search
        if (
            request.method != "POST"
            or not request.url.path.startswith("/api/v1/search")
            or not self._should_sample(request)
        ):
            return await call_next(request)

        # Read request body for shadow copy
        body = await request.body()

        # Send shadow request asynchronously (fire and forget)
        asyncio.create_task(
            self._send_shadow_request(
                method=request.method,
                path=request.url.path,
                query=request.url.query,
                headers=dict(request.headers),
                body=body,
            )
        )

        # Process original request
        return await call_next(request)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


# Global instance
shadow_traffic_middleware: ShadowTrafficMiddleware | None = None


def get_shadow_traffic_middleware() -> ShadowTrafficMiddleware:
    """Get or create shadow traffic middleware instance."""
    global shadow_traffic_middleware
    if shadow_traffic_middleware is None:
        sample_rate = getattr(settings, "SHADOW_TRAFFIC_SAMPLE_RATE", 0.1)
        staging_url = getattr(settings, "SHADOW_TRAFFIC_STAGING_URL", None)
        shadow_traffic_middleware = ShadowTrafficMiddleware(
            sample_rate=sample_rate,
            staging_url=staging_url,
        )
    return shadow_traffic_middleware
