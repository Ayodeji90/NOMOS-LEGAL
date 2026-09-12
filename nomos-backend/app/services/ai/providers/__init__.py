"""LLM provider implementations for model-agnostic AI services.

This module provides a provider abstraction layer that allows easy switching
between different LLM providers (Vertex AI, Anthropic, OpenAI, etc.) via
configuration.

Providers:
- BaseLLMProvider: Abstract base class defining the provider interface
- VertexAIProvider: Vertex AI (Gemini) implementation
- AnthropicProvider: Anthropic (Claude) implementation
- OpenAIProvider: OpenAI (GPT) implementation
- ProviderFactory: Factory for creating provider instances
- FallbackProvider: Provider with automatic fallback to secondary provider
"""

from app.services.ai.providers.anthropic_provider import AnthropicProvider
from app.services.ai.providers.base import BaseLLMProvider
from app.services.ai.providers.factory import ProviderFactory, create_provider
from app.services.ai.providers.fallback_provider import FallbackProvider
from app.services.ai.providers.openai_provider import OpenAIProvider
from app.services.ai.providers.vertex_provider import VertexAIProvider

__all__ = [
    "BaseLLMProvider",
    "VertexAIProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "ProviderFactory",
    "create_provider",
    "FallbackProvider",
]
