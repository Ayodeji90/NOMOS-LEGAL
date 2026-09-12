"""NLI (Natural Language Inference) service for claim verification.

This service checks if claims in generated answers are entailed by retrieved excerpts.
Week 10: Promote NLI to blocking (atomic claims vs excerpt: entailed, not_entailed, not_found).
"""

import logging
from enum import Enum
from typing import Any

from app.core.config import settings
from app.services.ai.providers import create_provider
from app.services.ai.providers.config_helper import (
    get_model_name_for_service,
    get_provider_config,
)

logger = logging.getLogger(__name__)


class NLIResult(Enum):
    """Result of NLI check."""

    ENTAILED = "entailed"  # Claim is supported by excerpts
    NOT_ENTAILED = "not_entailed"  # Claim contradicts or not supported by excerpts
    NOT_FOUND = "not_found"  # No relevant excerpts found for claim


class NLIService:
    """Service for Natural Language Inference checks on claims."""

    def __init__(self, blocking: bool = True):
        """Initialize NLI service.

        Args:
            blocking: If True, NLI failures are blocking (refuse/repair). If False, log-only.
        """
        self._blocking = blocking
        self._provider = self._get_provider()
        logger.info(f"NLIService initialized with blocking={blocking}")

    def _get_provider(self):
        """Get configured LLM provider for NLI."""
        provider_name = settings.VERIFIER_PROVIDER
        model_name = get_model_name_for_service("verifier", provider_name)
        config = get_provider_config(provider_name)

        return create_provider(provider_name, model_name, **config)

    async def check_claim_entailment(
        self,
        claim: str,
        excerpts: list[dict[str, Any]],
    ) -> tuple[NLIResult, str | None]:
        """
        Check if a claim is entailed by retrieved excerpts.

        Args:
            claim: The claim to verify
            excerpts: Retrieved excerpts with text and metadata

        Returns:
            (nli_result, explanation)
        """
        if not excerpts:
            logger.warning("No excerpts provided for NLI check")
            return NLIResult.NOT_FOUND, "No excerpts available to verify claim"

        # Build NLI prompt
        excerpt_texts = "\n\n".join(
            [
                f"Excerpt {i + 1}: {excerpt.get('sourceText', excerpt.get('text', ''))}"
                for i, excerpt in enumerate(excerpts[:5])  # Limit to 5 excerpts for context
            ]
        )

        prompt = f"""You are a legal fact-checker. Determine if the following claim is entailed by the provided legal excerpts.

Claim: {claim}

Excerpts:
{excerpt_texts}

Classify the claim as one of:
- ENTAILED: The claim is directly supported by the excerpts
- NOT_ENTAILED: The claim contradicts the excerpts or is not supported
- NOT_FOUND: The excerpts do not contain relevant information to verify the claim

Respond with just the classification and a brief explanation in JSON format:
{{"result": "ENTAILED|NOT_ENTAILED|NOT_FOUND", "explanation": "brief explanation"}}"""

        try:
            response = await self._provider.generate_json(
                system_prompt="You are a legal fact-checker. Determine if claims are entailed by legal excerpts.",
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=256,
            )

            result_str = response.get("result", "NOT_FOUND").upper()
            explanation = response.get("explanation", "")

            # Map to enum
            if result_str == "ENTAILED":
                nli_result = NLIResult.ENTAILED
            elif result_str == "NOT_ENTAILED":
                nli_result = NLIResult.NOT_ENTAILED
            else:
                nli_result = NLIResult.NOT_FOUND

            logger.info(f"NLI check: claim='{claim[:50]}...', result={nli_result.value}")
            return nli_result, explanation

        except Exception as e:
            logger.error(f"NLI check failed: {e}")
            return NLIResult.NOT_FOUND, f"NLI check failed: {str(e)}"

    async def check_all_claims(
        self,
        claims: list[str],
        excerpts: list[dict[str, Any]],
    ) -> tuple[list[tuple[str, NLIResult, str | None]], bool]:
        """
        Check entailment for all claims.

        Args:
            claims: List of claims to verify
            excerpts: Retrieved excerpts

        Returns:
            (results, should_block) where results is list of (claim, nli_result, explanation)
        """
        results = []
        has_not_entailed = False

        for claim in claims:
            nli_result, explanation = await self.check_claim_entailment(claim, excerpts)
            results.append((claim, nli_result, explanation))

            if nli_result == NLIResult.NOT_ENTAILED:
                has_not_entailed = True

        should_block = has_not_entailed and self._blocking

        if should_block:
            logger.warning(
                f"NLI blocking: {sum(1 for _, r, _ in results if r == NLIResult.NOT_ENTAILED)} claims not entailed"
            )

        return results, should_block


# Global instance for dependency injection
nli_service = NLIService(blocking=True)
