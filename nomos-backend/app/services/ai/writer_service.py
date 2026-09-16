"""
Writer service for generating grounded legal answers.

Uses Gemini Pro (with Claude fallback) to generate structured answers
from retrieved excerpts. Grounds only on provided excerpts with [n] citations.

Reference implementation: juris-backend-src/ai-write.js
"""

import json
import logging
import re

from app.core.config import settings
from app.schemas.writer import WriterInput, WriterOutput

logger = logging.getLogger(__name__)


# Prompts preserved verbatim from original implementation
ASK_SYSTEM = (
    "You are NOMOS, a legal research assistant. Ground only on the numbered excerpts retrieved for this request from the live Nomos corpus (Laws.Africa knowledge bases for South Africa; the Cloud Run legislation corpora for UK, US, Canada, Australia, Ireland, Germany, and New Zealand). Never use Discovery Engine. Never cite gs://juris-legal-documents/ paths. "
    "Write like a careful lawyer talking to a colleague: clear prose, not a template. "
    "Use ONLY the numbered excerpts. Do not invent Acts, sections, cases, tests, dates, or duties. "
    "Every legal proposition must be followed by an [n] cite that matches an excerpt number. "
    "Do not write 'the retrieved sources point primarily to'. Name the rule, then cite. "
    "Before writing: identify the single most on-point retrieved section (the controlling provision) and lead with it in directAnswer, then explanation, then leave remaining limits in gaps. "
    "If retrieved excerpts span more than one Act and the question names one Act or topic, ignore excerpts from other Acts. Do not blend jurisdictions. "
    "Answer the current question only. Conversation is for follow-up pronouns, not for importing statutes from earlier turns unless those statutes appear in the excerpts. "
    "If at least one excerpt is on-point, you MUST answer from it. Do not set insufficientContext=true because other excerpts are off-topic, truncated, or because court judgments are absent. Put those limits in gaps. "
    "Set insufficientContext=true only when every excerpt is empty or none of them address the question at all. "
    "gaps is required: name what the excerpts do not cover (other instruments, missing sections, case law). "
    'Return JSON: {"insufficientContext": boolean, "directAnswer": string (3-8 short paragraphs, blank line between them, [n] cites; empty if insufficientContext), "explanation": string, "gaps": string, "followUps": string[3]}.'
)

ZA_ASK_ADDENDUM = " For South African questions: if numbered statute excerpts address the question, answer from those excerpts and do not set insufficientContext merely because court judgments or common-law cases are absent. State in gaps that judgments and common-law case principles are not in this legislation corpus (judgments off pending licence). Do not imply there is no legal basis when statute was retrieved."


def basis_payload(excerpts: list[dict]) -> list[dict]:
    """Format excerpts for the writer prompt, matching original basisPayload."""
    return [
        {
            "n": i + 1,
            "citation": b.get("citation", ""),
            "excerpt": str(b.get("sourceText", "") or b.get("text", ""))[:2200],
        }
        for i, b in enumerate(excerpts[:8])
    ]


def extract_json(text: str) -> dict:
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


class WriterService:
    """Service for generating grounded legal answers using LLMs."""

    def __init__(self):
        self._model = settings.MODEL_WRITER or "gemini-2.5-flash"
        self._project = settings.GCP_PROJECT_ID
        self._location = settings.VERTEX_AI_LOCATION
        logger.info(f"WriterService initialized with model: {self._model}")

    async def _call_gemini(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
    ) -> dict:
        """Call Gemini Pro API with JSON response."""
        try:
            from vertexai.generative_models import GenerationConfig, GenerativeModel
        except ImportError as e:
            raise RuntimeError(
                "Vertex AI package not installed. Install with: pip install vertexai"
            ) from e

        try:
            model = GenerativeModel(
                self._model,
                system_instruction=system,
            )

            generation_config = GenerationConfig(
                temperature=0,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            )

            response = model.generate_content(
                contents=user,
                generation_config=generation_config,
            )

            text = response.text
            return extract_json(text)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    async def write_answer(
        self,
        input_data: WriterInput,
    ) -> WriterOutput:
        """Generate a grounded legal answer from retrieved excerpts."""

        # Determine if ZA addendum should be used
        is_za = input_data.jurisdiction.lower() == "za"
        system_prompt = ASK_SYSTEM + (ZA_ASK_ADDENDUM if is_za else "")

        # Format excerpts for the prompt
        basis = basis_payload(input_data.excerpts)

        # Build user prompt
        user_payload = {
            "jurisdiction": input_data.jurisdiction,
            "question": input_data.query,
            "conversation": input_data.history[-6:] if input_data.history else [],
            "excerpts": basis,
        }

        user_prompt = json.dumps(user_payload, indent=2)

        # Add repair context if this is a repair attempt
        if input_data.is_repair and input_data.verification_failures:
            system_prompt += (
                "\n\nREPAIR CONTEXT: The previous answer failed verification for these reasons:\n"
                "\n".join(f"- {f}" for f in input_data.verification_failures)
                + "\nFix these specific issues in your response."
            )

        logger.info(f"Calling writer for query: {input_data.query[:100]}...")

        try:
            response = await self._call_gemini(
                system=system_prompt,
                user=user_prompt,
                max_tokens=2048,
            )

            # Map response to WriterOutput schema
            output = WriterOutput(
                insufficientContext=response.get("insufficientContext", False),
                directAnswer=response.get("directAnswer", ""),
                explanation=response.get("explanation", ""),
                gaps=response.get("gaps", ""),
                followUps=response.get("followUps", [])[:3],
                metadata={
                    "model": self._model,
                    "jurisdiction": input_data.jurisdiction,
                    "excerpt_count": len(input_data.excerpts),
                },
            )

            logger.info(
                f"Writer generated answer (insufficientContext={output.insufficientContext})"
            )
            return output

        except Exception as e:
            logger.error(f"Writer failed: {e}")
            # Return a safe fallback
            return WriterOutput(
                insufficientContext=True,
                directAnswer="",
                explanation=f"Writer service failed: {str(e)}",
                gaps="Unable to generate answer due to service error.",
                followUps=[],
                metadata={"error": str(e), "model": self._model},
            )


# Global instance for dependency injection
writer_service = WriterService()
