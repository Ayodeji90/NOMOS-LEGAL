from typing import Any

from pydantic import BaseModel, Field, field_validator


def _coerce_to_str_list(v: Any) -> list[str]:
    """Coerce a Gemini response field to list[str].

    Gemini sometimes returns a single string where a list[str] is expected,
    or a dict/list-of-dicts where a flat list is expected.
    """
    if isinstance(v, list):
        return [str(item) for item in v]
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, dict):
        # Gemini sometimes nests under a key like "issues" or "items"
        for key in ("issues", "items", "problems", "details"):
            if key in v and isinstance(v[key], list):
                return [str(item) for item in v[key]]
        return [str(v)]
    return []


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

    @field_validator("citation_issues", "section_issues", "entailment_issues", "currency_issues", "suggested_repairs", mode="before")
    @classmethod
    def coerce_issue_list(cls, v: Any) -> list[str]:
        return _coerce_to_str_list(v)

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_summary_to_string(cls, v: Any) -> str:
        if isinstance(v, list):
            return "; ".join(str(item) for item in v)
        return str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.5
        if isinstance(v, dict):
            # Gemini might return {"score": 0.8} instead of 0.8
            for key in ("score", "value", "confidence"):
                if key in v:
                    try:
                        return float(v[key])
                    except (ValueError, TypeError):
                        pass
            return 0.5
        return float(v) if v is not None else 0.5

    @field_validator("should_repair", mode="before")
    @classmethod
    def coerce_repair_bool(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "1", "repair")
        if isinstance(v, dict):
            return bool(v)
        return bool(v)


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
