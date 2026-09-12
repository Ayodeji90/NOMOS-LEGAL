"""Vertex AI (Gemini) provider implementation.

This provider uses Google Cloud Vertex AI to access Gemini models.
"""

import asyncio
import logging
import re
from typing import Any

from app.services.ai.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

#: Timeout for the direct REST JSON call (seconds). Chosen to sit inside the
#: reranker's own 4s watchdog so graceful degradation stays in charge.
_REST_TIMEOUT_SECONDS = 8


class VertexAIProvider(BaseLLMProvider):
    """Vertex AI (Gemini) LLM provider."""

    def __init__(self, model_name: str, project_id: str = None, location: str = None, **kwargs):
        """Initialize Vertex AI provider.

        Args:
            model_name: Gemini model name (e.g., 'gemini-1.5-flash', 'gemini-1.5-pro')
            project_id: GCP project ID (uses default if None)
            location: Vertex AI location (default: 'us-central1')
            **kwargs: Additional configuration
        """
        super().__init__(model_name, **kwargs)
        self._project_id = project_id
        self._location = location or "us-central1"
        self._client = None

    @property
    def provider_name(self) -> str:
        return "vertex"

    def _get_client(self):
        """Lazy initialization of Vertex AI client."""
        if self._client is None:
            try:
                from vertexai.generative_models import GenerativeModel

                self._client = GenerativeModel
                logger.info(f"Vertex AI client initialized for model: {self._model_name}")
            except ImportError as e:
                raise RuntimeError(
                    "Vertex AI package not installed. Install with: pip install vertexai"
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
        """Generate JSON output using Gemini."""
        client_class = self._get_client()

        try:
            # The deprecated vertexai SDK's GenerationConfig lacks thinking
            # support. 2.5-* models spend an uncontrolled thinking budget on
            # big prompts, which can consume all of max_output_tokens and
            # leave an empty candidate ("Model returned no JSON"). Call the
            # REST endpoint directly with thinkingBudget=0 for deterministic
            # JSON output; fall back to the SDK path for any error.
            text = await asyncio.to_thread(
                self._generate_json_rest, system_prompt, user_prompt, temperature, max_tokens
            )
            return self._extract_json(text)
        except ValueError:
            raise
        except Exception as rest_exc:
            logger.warning("Vertex REST JSON call failed (%s); trying SDK", rest_exc)

        try:
            from vertexai.generative_models import GenerationConfig

            # vertexai SDK: system_instruction is a constructor arg of
            # GenerativeModel, not a generate_content kwarg (the latter
            # raises TypeError on vertexai>=1.34).
            model = client_class(self._model_name, system_instruction=[system_prompt])

            generation_config = GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            )

            response = model.generate_content(
                contents=user_prompt,
                generation_config=generation_config,
            )

            text = response.text
            return self._extract_json(text)

        except Exception as e:
            logger.error(f"Vertex AI JSON generation failed: {e}")
            raise

    def _generate_json_rest(
        self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int
    ) -> str:
        """Synchronous REST call to generateContent with thinking disabled."""
        import json as _json
        import urllib.error
        import urllib.request

        import google.auth
        import google.auth.transport.requests

        credentials, project = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        location = self._location or "us-central1"
        project_id = self._project_id or project
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/"
            f"publishers/google/models/{self._model_name}:generateContent"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
                # Deterministic mode for structured output; harmless on
                # models without thinking (1.5/2.0 accept and ignore it).
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        req = urllib.request.Request(
            url,
            data=_json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_REST_TIMEOUT_SECONDS) as resp:
            data = _json.loads(resp.read())
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError(f"Vertex REST: no candidates: {str(data.get('error', data))[:300]}")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts or "text" not in parts[0]:
            raise ValueError(
                "Vertex REST: candidate has no text (finishReason={})".format(
                    candidates[0].get("finishReason")
                )
            )
        return parts[0]["text"]

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Generate text output using Gemini."""
        client_class = self._get_client()

        try:
            from vertexai.generative_models import GenerationConfig

            model = client_class(self._model_name, system_instruction=[system_prompt])

            generation_config = GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            response = model.generate_content(
                contents=user_prompt,
                generation_config=generation_config,
            )

            return response.text

        except Exception as e:
            logger.error(f"Vertex AI text generation failed: {e}")
            raise
