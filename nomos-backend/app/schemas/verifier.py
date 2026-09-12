from typing import Any

from pydantic import BaseModel, Field


class VerifierVerdict(BaseModel):
    """Schema for verifier verdict output."""

    # Whether the answer is grounded in the retrieved excerpts
    grounded: bool = Field(
        description="Whether the answer is sufficiently grounded in retrieved excerpts"
    )

    # Specific citation issues (if any)
    citation_issues: list[str] = Field(
        default_factory=list,
        description="Problems with [n] citations in the answer",
        examples=[
            "Citation [5] does not match any retrieved excerpt",
            "Citation [2] refers to excerpt 3 but excerpt 3 is empty",
        ],
    )

    # Section realism issues (if any)
    section_issues: list[str] = Field(
        default_factory=list,
        description="Problems with statutory references in the answer",
        examples=[
            "Reference to 'section 15(2)' not found in any excerpt",
            "Incorrect section numbering in Act reference",
        ],
    )

    # Entailment/contradiction issues (if any)
    entailment_issues: list[str] = Field(
        default_factory=list,
        description="Claims that are not supported by or contradict the cited excerpts",
        examples=[
            "Claim 'employers must pay overtime on Sundays' contradicts excerpt 7 which states overtime is voluntary",
            "Claim not found in cited excerpts",
        ],
    )

    # Currency issues (if any)
    currency_issues: list[str] = Field(
        default_factory=list,
        description="Problems with currency/time assumptions in the answer",
        examples=[
            "Answer states law as of 2020 but excerpts are from 2023",
            "Answer refers to repealed section without noting repeal",
        ],
    )

    # Overall confidence in the verdict
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this verdict (0.0 to 1.0)")

    # Suggested repairs (if not grounded)
    suggested_repairs: list[str] = Field(
        default_factory=list,
        description="Specific suggestions for improving the answer",
        max_items=3,
    )

    # Whether to attempt repair or refuse
    should_repair: bool = Field(
        description="Whether the system should attempt to repair the answer based on these issues"
    )

    # Summary of verification outcome
    summary: str = Field(description="Human-readable summary of verification results")


class VerifierInput(BaseModel):
    """Input to the verifier service."""

    # Original user query
    query: str = Field(description="Original user query", min_length=1, max_length=2500)

    # The answer to verify (from writer)
    answer: str = Field(description="The generated answer to verify", min_length=1)

    # Retrieved excerpts used to generate the answer
    excerpts: list[dict[str, Any]] = Field(
        description="The excerpts that were available to the writer", min_items=1
    )

    # Jurisdiction for context
    jurisdiction: str = Field(
        description="Jurisdiction ID (e.g., 'za', 'gb', 'us')", examples=["za", "gb", "us"]
    )

    # Whether this is a repair attempt
    is_repair: bool = Field(
        default=False, description="Whether this is verification of a repair attempt"
    )

    # Previous verification failures (if repair)
    previous_failures: list[str] | None = Field(
        default=None, description="Failures from previous verification that motivated this repair"
    )
