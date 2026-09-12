"""OpenAI (GPT) provider implementation.

This provider uses OpenAI's API to access GPT models.
"""

import logging
import re
from typing import Any

from app.services.ai.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI (GPT) LLM provider."""

    def __init__(self, model_name: str, api_key: str = None, **kwargs):
        """Initialize OpenAI provider.

        Args:
            model_name: GPT model name (e.g., 'gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo')
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if None)
            **kwargs: Additional configuration
        """
        super().__init__(model_name, **kwargs)
        self._api_key = api_key
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                api_key = self._api_key
                if not api_key:
                    import os

                    api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                        "or pass api_key parameter."
                    )
                self._client = AsyncOpenAI(api_key=api_key)
                logger.info(f"OpenAI client initialized for model: {self._model_name}")
            except ImportError as e:
                raise RuntimeError(
                    "OpenAI package not installed. Install with: pip install openai"
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
        """Generate JSON output using GPT."""
        client = self._get_client()

        try:
            response = await client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

            text = response.choices[0].message.content
            return self._extract_json(text)

        except Exception as e:
            logger.error(f"OpenAI JSON generation failed: {e}")
            raise

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate text output using GPT."""
        client = self._get_client()

        try:
            response = await client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI text generation failed: {e}")
            raise
