"""Azure OpenAI chat provider (gpt-4o-mini etc. via an Azure deployment).

Mirrors ``openai_provider.OpenAIProvider`` but targets Azure OpenAI:
authenticates with an endpoint + api-key (``AZURE_OPENAI_ENDPOINT`` /
``AZURE_OPENAI_API_KEY``), and the model name is the Azure **deployment
name** (created in the portal/CLI), not a public model id.

Selected via the standard provider seam:
``QUERY_UNDERSTANDING_PROVIDER=azure_openai`` (etc.) — see
``providers/factory.py`` and ``providers/config_helper.py``.
"""

import logging
import re
from typing import Any

from app.services.ai.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI LLM provider (chat + JSON generation)."""

    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
        **kwargs,
    ):
        """Initialize the Azure OpenAI provider.

        Args:
            model_name: Azure **deployment name** (e.g. 'nomos-gpt-4o-mini')
            api_key: Azure OpenAI key (falls back to AZURE_OPENAI_API_KEY env)
            endpoint: Azure OpenAI endpoint (falls back to
                AZURE_OPENAI_ENDPOINT env)
            api_version: API version (falls back to
                AZURE_OPENAI_API_VERSION env, default 2024-10-21)
        """
        super().__init__(model_name, **kwargs)
        self._api_key = api_key
        self._endpoint = endpoint
        self._api_version = api_version
        self._client = None

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    def _get_client(self):
        """Lazy initialization of the Azure OpenAI async client."""
        if self._client is None:
            try:
                from openai import AsyncAzureOpenAI
            except ImportError as exc:  # pragma: no cover - env-specific
                raise RuntimeError(
                    "openai package not installed. Install project dependencies first."
                ) from exc

            import os

            api_key = self._api_key or os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = self._endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
            api_version = self._api_version or os.getenv("AZURE_OPENAI_API_VERSION")

            if not api_key or not endpoint:
                raise ValueError(
                    "Azure OpenAI credentials missing. Set AZURE_OPENAI_ENDPOINT "
                    "and AZURE_OPENAI_API_KEY (or pass them explicitly)."
                )

            self._client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version or "2024-10-21",
            )
            logger.info(
                "Azure OpenAI client initialized: deployment=%s endpoint=%s",
                self._model_name,
                endpoint,
            )
        return self._client

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response, handling markdown fences."""
        raw = str(text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.IGNORECASE)
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
        """Generate JSON output via the Azure deployment."""
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=self._model_name,  # Azure: the deployment name
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return self._extract_json(response.choices[0].message.content)
        except Exception as exc:
            logger.error("Azure OpenAI JSON generation failed: %s", exc)
            raise

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate plain text via the Azure deployment."""
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
        except Exception as exc:
            logger.error("Azure OpenAI text generation failed: %s", exc)
            raise
