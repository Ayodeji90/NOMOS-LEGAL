"""Anthropic (Claude) provider implementation.

This provider uses Anthropic's API to access Claude models.
"""

import logging
import re
from typing import Any

from app.services.ai.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic (Claude) LLM provider."""

    def __init__(self, model_name: str, api_key: str = None, **kwargs):
        """Initialize Anthropic provider.

        Args:
            model_name: Claude model name (e.g., 'claude-3-haiku-20240307', 'claude-3-5-sonnet-20241022')
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if None)
            **kwargs: Additional configuration
        """
        super().__init__(model_name, **kwargs)
        self._api_key = api_key
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                api_key = self._api_key
                if not api_key:
                    import os

                    api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError(
                        "Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable "
                        "or pass api_key parameter."
                    )
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
                logger.info(f"Anthropic client initialized for model: {self._model_name}")
            except ImportError as e:
                raise RuntimeError(
                    "Anthropic package not installed. Install with: pip install anthropic"
                ) from e
        return self._client

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        raw = str(text or "").strip()
        # Remove markdown code blocks if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.IGNORECASE)
        # Find JSON object
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("Model returned no JSON")
        import json

        return json.loads(match[0])

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate JSON output using Claude."""
        client = self._get_client()

        try:
            # Claude expects messages in a specific format
            message = await client.messages.create(
                model=self._model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                # Request JSON response
                response_format={"type": "json_object"}
                if "json" in kwargs.get("response_format", "json")
                else None,
            )

            text = message.content[0].text
            return self._extract_json(text)

        except Exception as e:
            logger.error(f"Anthropic JSON generation failed: {e}")
            raise

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate text output using Claude."""
        client = self._get_client()

        try:
            message = await client.messages.create(
                model=self._model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return message.content[0].text

        except Exception as e:
            logger.error(f"Anthropic text generation failed: {e}")
            raise
