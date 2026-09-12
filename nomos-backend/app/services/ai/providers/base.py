"""Base abstract class for LLM providers.

All provider implementations must inherit from BaseLLMProvider and implement
the required methods. This ensures a consistent interface across all providers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All provider implementations (Vertex AI, Anthropic, OpenAI, etc.) must
    inherit from this class and implement the required methods.
    """

    def __init__(self, model_name: str, **kwargs):
        """Initialize the provider.

        Args:
            model_name: Name of the model to use
            **kwargs: Additional provider-specific configuration
        """
        self._model_name = model_name
        self._config = kwargs
        logger.info(f"Initialized {self.provider_name} with model: {model_name}")

    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate JSON output from the LLM.

        Args:
            system_prompt: System-level instructions for the model
            user_prompt: User query/input for the model
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict containing the parsed JSON response

        Raises:
            Exception: If the API call fails or returns invalid JSON
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate text output from the LLM.

        Args:
            system_prompt: System-level instructions for the model
            user_prompt: User query/input for the model
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            String containing the generated text

        Raises:
            Exception: If the API call fails
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'vertex', 'anthropic', 'openai')."""
        pass

    @property
    def model_name(self) -> str:
        """Current model name."""
        return self._model_name

    @property
    def config(self) -> dict[str, Any]:
        """Provider configuration."""
        return self._config.copy()

    async def health_check(self) -> bool:
        """Check if the provider is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple health check with minimal request
            await self.generate_text(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say 'OK' if you can read this.",
                temperature=0.0,
                max_tokens=10,
            )
            return True
        except Exception as e:
            logger.warning(f"Health check failed for {self.provider_name}: {e}")
            return False
