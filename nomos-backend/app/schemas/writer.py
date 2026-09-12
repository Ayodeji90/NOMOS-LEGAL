from typing import Any

from pydantic import BaseModel, Field

from .query_understanding import QueryUnderstandingOutput


class WriterInput(BaseModel):
    """Input to the writer service."""

    # Original user query
    query: str = Field(description="Original user query", min_length=1, max_length=2500)

    # Jurisdiction for the answer
    jurisdiction: str = Field(
        description="Jurisdiction ID (e.g., 'za', 'gb', 'us')", examples=["za", "gb", "us"]
    )

    # Retrieved excerpts to ground the answer in
    excerpts: list[dict[str, Any]] = Field(
        description="Retrieved excerpts with citation numbers, text, and metadata", min_items=1
    )

    # Query understanding output (optional, for context)
    understanding: QueryUnderstandingOutput | None = Field(
        default=None, description="Pre-computed query understanding for context"
    )

    # Conversation history for follow-up pronouns
    history: list[dict] = Field(
        default_factory=list, description="Conversation history for pronoun resolution", max_items=6
    )

    # Whether this is a repair attempt (from verification failure)
    is_repair: bool = Field(
        default=False, description="Whether this is a repair attempt after verification failure"
    )

    # Failure reasons from previous verification (if repair)
    verification_failures: list[str] | None = Field(
        default=None, description="Specific failures from previous verification attempt"
    )


class WriterOutput(BaseModel):
    """Output from the writer service."""

    # Whether the system has sufficient context to answer
    insufficientContext: bool = Field(
        description="True if no retrieved excerpts address the question at all"
    )

    # Direct answer to the user's question (3-8 short paragraphs with [n] citations)
    directAnswer: str = Field(
        description="Direct answer with [n] citations to retrieved excerpts", max_length=2000
    )

    # Explanation of legal reasoning
    explanation: str = Field(
        description="Explanation of how the answer was derived from the excerpts"
    )

    # Gaps in the retrieved material (what's missing)
    gaps: str = Field(description="What the retrieved excerpts do not cover")

    # Follow-up questions for clarification
    followUps: list[str] = Field(
        description="Suggested follow-up questions for clarification", max_items=3
    )

    # Metadata about the answer generation
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata about generation (token usage, model, etc.)"
    )


# Re-use StructuredAnswer from search.py for consistency in API responses
# This ensures writer output matches what the API expects
