"""Provider factory for creating LLM provider instances.

This module provides a factory pattern for instantiating different LLM providers
based on configuration. It supports provider switching and fallback mechanisms.
"""

import logging

from app.services.ai.providers.anthropic_provider import AnthropicProvider
from app.services.ai.providers.azure_openai_provider import AzureOpenAIProvider
from app.services.ai.providers.base import BaseLLMProvider
from app.services.ai.providers.fallback_provider import FallbackProvider
from app.services.ai.providers.openai_provider import OpenAIProvider
from app.services.ai.providers.vertex_provider import VertexAIProvider

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating LLM provider instances."""

    # Registry of available providers
    _providers: dict[str, type[BaseLLMProvider]] = {
        "vertex": VertexAIProvider,
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "azure_openai": AzureOpenAIProvider,
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: type[BaseLLMProvider]) -> None:
        """Register a new provider class.

        Args:
            name: Provider name (e.g., 'vertex', 'anthropic')
            provider_class: Provider class inheriting from BaseLLMProvider
        """
        cls._providers[name.lower()] = provider_class
        logger.info(f"Registered provider: {name}")

    @classmethod
    def create(cls, provider_name: str, model_name: str, **kwargs) -> BaseLLMProvider:
        """Create a provider instance.

        Args:
            provider_name: Provider name (e.g., 'vertex', 'anthropic', 'openai')
            model_name: Model name to use
            **kwargs: Additional provider-specific configuration

        Returns:
            Instance of the requested provider

        Raises:
            ValueError: If provider name is unknown
        """
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unknown provider: {provider_name}. Available providers: {available}")

        logger.info(f"Creating {provider_name} provider with model: {model_name}")
        return provider_class(model_name=model_name, **kwargs)

    @classmethod
    def create_with_fallback(
        cls, primary_provider: str, fallback_provider: str, model_name: str, **kwargs
    ) -> FallbackProvider:
        """Create a provider with automatic fallback.

        Args:
            primary_provider: Primary provider name
            fallback_provider: Fallback provider name
            model_name: Model name to use
            **kwargs: Additional provider-specific configuration

        Returns:
            FallbackProvider instance wrapping primary and fallback
        """
        primary = cls.create(primary_provider, model_name, **kwargs)
        fallback = cls.create(fallback_provider, model_name, **kwargs)

        logger.info(
            f"Creating fallback provider: primary={primary_provider}, fallback={fallback_provider}"
        )
        return FallbackProvider(primary=primary, fallback=fallback)

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available provider names."""
        return list(cls._providers.keys())


# Convenience function for creating providers
def create_provider(provider_name: str, model_name: str, **kwargs) -> BaseLLMProvider:
    """Convenience function for creating a provider instance.

    Args:
        provider_name: Provider name (e.g., 'vertex', 'anthropic', 'openai')
        model_name: Model name to use
        **kwargs: Additional provider-specific configuration

    Returns:
        Instance of the requested provider
    """
    return ProviderFactory.create(provider_name, model_name, **kwargs)
