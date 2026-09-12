"""Fallback provider for automatic provider switching on failure.

This provider wraps two providers (primary and fallback) and automatically
switches to the fallback if the primary provider fails.
"""

import logging
from typing import Any

from app.services.ai.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class FallbackProvider(BaseLLMProvider):
    """Provider that automatically falls back to secondary on failure."""

    def __init__(self, primary: BaseLLMProvider, fallback: BaseLLMProvider):
        """Initialize fallback provider.

        Args:
            primary: Primary provider to use first
            fallback: Fallback provider to use if primary fails
        """
        super().__init__(f"{primary.provider_name}+{fallback.provider_name}")
        self._primary = primary
        self._fallback = fallback
        self._use_fallback = False
        logger.info(
            f"Initialized FallbackProvider: primary={primary.provider_name}, "
            f"fallback={fallback.provider_name}"
        )

    @property
    def provider_name(self) -> str:
        return "fallback"

    @property
    def primary_provider(self) -> BaseLLMProvider:
        return self._primary

    @property
    def fallback_provider(self) -> BaseLLMProvider:
        return self._fallback

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate JSON with automatic fallback on failure."""
        provider = self._fallback if self._use_fallback else self._primary

        try:
            result = await provider.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            # Reset fallback flag on success
            if self._use_fallback:
                logger.info("Primary provider recovered, switching back")
                self._use_fallback = False
            return result

        except Exception as e:
            if not self._use_fallback:
                logger.warning(
                    f"Primary provider ({self._primary.provider_name}) failed: {e}, "
                    f"trying fallback ({self._fallback.provider_name})"
                )
                self._use_fallback = True
                # Retry with fallback
                return await self._fallback.generate_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            else:
                # Both failed
                logger.error(
                    f"Both primary ({self._primary.provider_name}) and fallback "
                    f"({self._fallback.provider_name}) providers failed"
                )
                raise

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate text with automatic fallback on failure."""
        provider = self._fallback if self._use_fallback else self._primary

        try:
            result = await provider.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            # Reset fallback flag on success
            if self._use_fallback:
                logger.info("Primary provider recovered, switching back")
                self._use_fallback = False
            return result

        except Exception as e:
            if not self._use_fallback:
                logger.warning(
                    f"Primary provider ({self._primary.provider_name}) failed: {e}, "
                    f"trying fallback ({self._fallback.provider_name})"
                )
                self._use_fallback = True
                # Retry with fallback
                return await self._fallback.generate_text(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            else:
                # Both failed
                logger.error(
                    f"Both primary ({self._primary.provider_name}) and fallback "
                    f"({self._fallback.provider_name}) providers failed"
                )
                raise

    async def health_check(self) -> bool:
        """Check health of both providers."""
        primary_healthy = await self._primary.health_check()
        fallback_healthy = await self._fallback.health_check()

        logger.info(f"Health check: primary={primary_healthy}, fallback={fallback_healthy}")

        return primary_healthy or fallback_healthy
