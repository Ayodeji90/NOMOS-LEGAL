"""
Query understanding service using Gemini Flash.

Analyzes user queries to extract:
- Jurisdiction confirmation
- Question type classification
- Expanded queries for retrieval (3-5 variants)
- Named Acts mentioned
- Intent category
- Complexity score

Week 5: Live integration with Gemini Flash, cached 24h by query hash + jurisdiction.
"""

import hashlib
import json
import logging
import re

from app.core.config import settings
from app.core.redis import redis_manager
from app.schemas.query_understanding import QueryUnderstandingInput, QueryUnderstandingOutput

logger = logging.getLogger(__name__)


def _get_cache_key(query: str, jurisdiction: str | None) -> str:
    """Generate cache key for query understanding results."""
    key_data = f"{query.lower().strip()}::{jurisdiction or 'default'}"
    return f"qu:{hashlib.md5(key_data.encode()).hexdigest()}"


async def _get_cached_understanding(cache_key: str) -> QueryUnderstandingOutput | None:
    """Retrieve cached query understanding if available."""
    try:
        cached = await redis_manager.client.get(cache_key)
        if cached:
            logger.info(f"Cache hit for query understanding: {cache_key[:16]}...")
            return QueryUnderstandingOutput.model_validate_json(cached)
    except Exception as e:
        logger.warning(f"Failed to get cached understanding: {e}")
    return None


async def _cache_understanding(cache_key: str, output: QueryUnderstandingOutput) -> None:
    """Cache query understanding result for 24 hours."""
    try:
        await redis_manager.client.set(cache_key, output.model_dump_json(), ex=86400)  # 24h TTL
        logger.info(f"Cached query understanding: {cache_key[:16]}...")
    except Exception as e:
        logger.warning(f"Failed to cache understanding: {e}")


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    raw = str(text or "").strip()
    # Remove markdown code blocks if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.IGNORECASE)
    # Find JSON object
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("Model returned no JSON")
    return json.loads(match[0])


class QueryUnderstandingService:
    """Service for query understanding using Gemini Flash."""

    def __init__(self):
        self._model = settings.MODEL_QUERY_UNDERSTANDING or "gemini-1.5-flash"
        self._project = settings.GCP_PROJECT_ID
        self._location = settings.VERTEX_AI_LOCATION
        logger.info(f"QueryUnderstandingService initialized with model: {self._model}")

    async def _call_gemini_flash(
        self,
        system: str,
        user: str,
        max_tokens: int = 1024,
    ) -> dict:
        """Call Gemini Flash API with JSON response."""
        try:
            from vertexai.generative_models import GenerationConfig, GenerativeModel
        except ImportError as e:
            raise RuntimeError(
                "Vertex AI package not installed. Install with: pip install vertexai"
            ) from e

        try:
            model = GenerativeModel(self._model)

            generation_config = GenerationConfig(
                temperature=settings.QUERY_UNDERSTANDING_TEMPERATURE,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            )

            response = model.generate_content(
                contents=user,
                generation_config=generation_config,
                system_instruction=system,
            )

            text = response.text
            return _extract_json(text)

        except Exception as e:
            logger.error(f"Gemini Flash API call failed: {e}")
            raise

    async def understand(
        self,
        query_input: QueryUnderstandingInput,
    ) -> QueryUnderstandingOutput:
        """
        Analyze query using Gemini Flash with 24h caching.

        Returns structured output with jurisdiction, question type,
        expanded queries, named acts, intent, and complexity.
        """
        # Check cache first
        cache_key = _get_cache_key(query_input.query, query_input.jurisdiction_hint)
        cached = await _get_cached_understanding(cache_key)
        if cached:
            return cached

        logger.info(f"Processing query understanding for: {query_input.query[:100]}...")

        # Build system prompt
        system_prompt = (
            "You are a legal query analyzer for NOMOS, a legal research system. "
            "Analyze the user's query and return structured JSON output. "
            "Identify the jurisdiction, question type, generate 3-5 expanded queries "
            "for better retrieval, extract named Acts, classify intent, and estimate complexity. "
            "Return JSON with these fields: "
            "jurisdiction (normalized: 'za', 'gb', 'us', etc.), "
            "question_type (one of: definition, interpretation, procedure, comparison, compliance, history, other), "
            "expanded_queries (array of 3-5 alternative query formulations), "
            "named_acts (array of Act names explicitly mentioned), "
            "intent_category (one of: statutory_interpretation, case_law_precedent, procedural_question, definition_request, compliance_check, historical_inquiry, other), "
            "confidence (0.0 to 1.0), "
            "multi_jurisdiction (boolean), "
            "complexity_score (0.0 to 1.0)."
        )

        # Build user prompt
        user_payload = {
            "query": query_input.query,
            "jurisdiction_hint": query_input.jurisdiction_hint,
            "conversation_history": query_input.history[-6:] if query_input.history else [],
        }

        user_prompt = json.dumps(user_payload, indent=2)

        try:
            response = await self._call_gemini_flash(
                system=system_prompt,
                user=user_prompt,
                max_tokens=settings.QUERY_UNDERSTANDING_MAX_TOKENS,
            )

            # Map response to QueryUnderstandingOutput schema
            output = QueryUnderstandingOutput(
                jurisdiction=response.get("jurisdiction", query_input.jurisdiction_hint or "za"),
                question_type=response.get("question_type", "other"),
                expanded_queries=response.get("expanded_queries", [query_input.query])[:5],
                named_acts=response.get("named_acts", [])[:10],
                intent_category=response.get("intent_category", "other"),
                confidence=float(response.get("confidence", 0.8)),
                multi_jurisdiction=bool(response.get("multi_jurisdiction", False)),
                complexity_score=float(response.get("complexity_score", 0.5)),
            )

            logger.info(
                f"Query understanding complete: jurisdiction={output.jurisdiction}, "
                f"type={output.question_type}, expanded={len(output.expanded_queries)} queries"
            )

            # Cache the result
            await _cache_understanding(cache_key, output)

            return output

        except Exception as e:
            logger.error(f"Query understanding failed: {e}")
            # Return safe fallback
            fallback = QueryUnderstandingOutput(
                jurisdiction=query_input.jurisdiction_hint or "za",
                question_type="other",
                expanded_queries=[query_input.query],
                named_acts=[],
                intent_category="other",
                confidence=0.5,
                multi_jurisdiction=False,
                complexity_score=0.5,
            )
            logger.warning("Using fallback query understanding")
            return fallback


# Global instance for dependency injection
query_understanding_service = QueryUnderstandingService()


async def understand_query(query_input: QueryUnderstandingInput) -> QueryUnderstandingOutput:
    """
    Convenience function for query understanding.

    This is the main entry point for the service.
    """
    return await query_understanding_service.understand(query_input)


async def understand_query_log_only(
    query_input: QueryUnderstandingInput,
) -> QueryUnderstandingOutput | None:
    """
    Log-only version that doesn't actually process.
    Used for testing the pipeline without API calls.
    """
    logger.info(f"[LOG-ONLY] Would process query understanding for: {query_input.query}")
    logger.info(f"[LOG-ONLY] Jurisdiction hint: {query_input.jurisdiction_hint}")
    logger.info(f"[LOG-ONLY] History length: {len(query_input.history)}")
    return None
