from typing import Literal

from pydantic import BaseModel, Field


class QueryUnderstandingOutput(BaseModel):
    """Schema for query understanding output from Gemini Flash."""

    # Jurisdiction confirmation - normalized jurisdiction ID
    jurisdiction: str = Field(
        description="Normalized jurisdiction ID (e.g., 'za', 'gb', 'us')",
        examples=["za", "gb", "us"],
    )

    # Question type classification
    question_type: Literal[
        "definition", "interpretation", "procedure", "comparison", "compliance", "history", "other"
    ] = Field(description="Type of legal question being asked")

    # Expanded queries for retrieval (paraphrases, synonyms, related concepts)
    expanded_queries: list[str] = Field(
        default_factory=list,
        description="Alternative query formulations for improved retrieval",
        max_items=5,
    )

    # Named Acts/legislation mentioned in the question
    named_acts: list[str] = Field(
        default_factory=list,
        description="Specific Acts or legislation explicitly named in the question",
        examples=["Basic Conditions of Employment Act", "Companies Act 71 of 2008"],
    )

    # Intent category for routing/dispatch
    intent_category: Literal[
        "statutory_interpretation",
        "case_law_precedent",
        "procedural_question",
        "definition_request",
        "compliance_check",
        "historical_inquiry",
        "other",
    ] = Field(description="High-level intent category for question routing")

    # Confidence score for the understanding
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score in the understanding output (0.0 to 1.0)"
    )

    # Whether the question requires multi-jurisdiction analysis
    multi_jurisdiction: bool = Field(
        default=False, description="Whether the question spans multiple jurisdictions"
    )

    # Complexity indicator for agent loop routing
    complexity_score: float = Field(
        ge=0.0, le=1.0, default=0.5, description="Estimated complexity of the question (0.0 to 1.0)"
    )


class QueryUnderstandingInput(BaseModel):
    """Input to query understanding service."""

    query: str = Field(description="Original user query", min_length=1, max_length=2500)

    jurisdiction_hint: str | None = Field(
        default=None,
        description="Optional jurisdiction hint from UI/context",
        examples=["za", "gb", "us"],
    )

    history: list[dict] = Field(
        default_factory=list,
        description="Conversation history for follow-up pronoun resolution",
        max_items=6,
    )
