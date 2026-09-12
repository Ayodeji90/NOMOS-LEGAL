"""
Verifier service for grounding verification.

Implements citation realism, section-reference realism, and NLI entailment checks.
Reference implementation: juris-backend-src/grounding.js

Week 4: citation realism + section realism blocking, NLI log-only
Week 10: NLI promoted to blocking
"""

import logging
import re
from typing import Any

from app.schemas.verifier import VerifierInput, VerifierVerdict

logger = logging.getLogger(__name__)


# Constants from original grounding.js
RESEARCH_CAVEAT = "Research assistance only. Not a substitute for professional legal advice."
COVERAGE_CAVEAT = "Corpus coverage and retrieval can miss the best section; always open the source link and confirm against the full Act."
CASE_LAW_NOT_IN_CORPUS = "Statutory sections were retrieved. Court judgments and common-law case principles are not in this corpus (judgments off pending licence). That is a case-law gap, not an absence of legal basis."
NO_STATUTE_RETRIEVED = "No on-point statute was retrieved for this question. Nomos will not invent Acts, sections, or holdings."


def extract_citation_numbers(text: str) -> list[int]:
    """Extract [n] citation numbers from text."""
    nums = []
    for match in re.finditer(r"\[(\d+)\]", str(text or "")):
        nums.append(int(match.group(1)))
    return nums


def extract_section_references(text: str) -> list[str]:
    """Extract statutory section references like 's 145', 'section 37(1)', 's. 10A'."""
    patterns = [
        r"(?:s(?:ection)?\.?\s*)(\d+[A-Za-z]?)(?:\s*\([^)]+\))?",  # s 145, section 37(1)
        r"(?:§\s*)(\d+[A-Za-z]?)(?:\s*\([^)]+\))?",  # § 145
    ]
    refs = []
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or ""), re.IGNORECASE):
            refs.append(match.group(0))
    return refs


def check_citation_realism(
    answer: str,
    excerpts: list[dict[str, Any]],
) -> list[str]:
    """
    Verify every [n] citation maps to a valid excerpt.

    Returns list of citation issues (empty if all valid).
    """
    issues = []
    cite_nums = extract_citation_numbers(answer)

    for num in cite_nums:
        if num < 1 or num > len(excerpts):
            issues.append(
                f"Citation [{num}] does not match any retrieved excerpt (1-{len(excerpts)} available)"
            )
        else:
            excerpt = excerpts[num - 1]
            text = str(excerpt.get("sourceText", "") or excerpt.get("text", "")).strip()
            if not text or len(text) < 20:
                issues.append(
                    f"Citation [{num}] refers to excerpt {num} which is empty or too short"
                )

    return issues


def check_section_realism(
    answer: str,
    excerpts: list[dict[str, Any]],
) -> list[str]:
    """
    Verify every statutory section reference exists in the cited excerpt's metadata or text.

    Returns list of section issues (empty if all valid).
    """
    issues = []
    cite_nums = extract_citation_numbers(answer)
    section_refs = extract_section_references(answer)

    # Build mapping of citation numbers to their excerpts
    for ref in section_refs:
        # Find which citation this section reference is near
        # This is a simplified check - in production, we'd need more sophisticated parsing
        found_in_excerpt = False

        for num in cite_nums:
            if num < 1 or num > len(excerpts):
                continue

            excerpt = excerpts[num - 1]
            excerpt_text = str(excerpt.get("sourceText", "") or excerpt.get("text", "")).lower()
            excerpt_citation = str(excerpt.get("citation", "")).lower()
            excerpt_section = str(
                excerpt.get("section", "") or excerpt.get("sectionNo", "")
            ).lower()

            ref_lower = ref.lower()

            # Check if the section reference appears in the excerpt
            if (
                ref_lower in excerpt_text
                or ref_lower in excerpt_citation
                or ref_lower in excerpt_section
            ):
                found_in_excerpt = True
                break

        if not found_in_excerpt:
            issues.append(f"Section reference '{ref}' not found in any cited excerpt")

    return issues


def check_invented_acts(
    answer: str,
    excerpts: list[dict[str, Any]],
    query: str,
) -> list[str]:
    """
    Detect invented Act names not present in excerpts or query.

    Returns list of invented Act issues (empty if none found).
    """
    issues = []

    # Extract Act names from answer (simplified pattern)
    act_pattern = r"\b(?:the\s+)?([A-Z][A-Za-z&'’-]{3,}(?:\s+[A-Z][A-Za-z&'’-]{2,}){1,8}\s+Act(?:\s+(?:No\.?\s*)?\d{1,5}(?:\s+of\s+\d{4})?|\s+\d{4})?)"
    answer_acts = re.findall(act_pattern, str(answer or ""))

    # Build blob of all excerpt text for checking
    excerpt_blob = " ".join(
        str(e.get("sourceText", "") or e.get("text", "") or e.get("citation", "")).lower()
        for e in excerpts
    )

    query_lower = str(query or "").lower()

    for act in answer_acts:
        act_lower = act.replace("the ", "").lower()
        if len(act_lower) < 12:
            continue

        # Skip if mentioned in query
        if act_lower in query_lower or act_lower.replace(" act", "") in query_lower:
            continue

        # Skip if found in excerpts
        if act_lower in excerpt_blob or act_lower.replace(" act", "") in excerpt_blob:
            continue

        issues.append(f"Invented Act name detected: '{act}' not found in excerpts or query")

    return issues


async def check_nli_entailment(
    answer: str,
    excerpts: list[dict[str, Any]],
    query: str,
) -> list[str]:
    """
    Check entailment of claims against cited excerpts using NLI.

    Week 4: Log-only implementation (returns empty issues)
    Week 10: Promote to blocking with actual Gemini Flash NLI calls
    """
    # Log-only for Week 4
    logger.info("[NLI LOG-ONLY] Would check entailment for answer against excerpts")
    logger.info(f"[NLI LOG-ONLY] Query: {query[:100]}...")
    logger.info(f"[NLI LOG-ONLY] Answer length: {len(answer)} chars")
    logger.info(f"[NLI LOG-ONLY] Excerpts: {len(excerpts)}")

    # Return empty issues for now (log-only mode)
    return []


def check_currency_disclosure(
    answer: str,
    excerpts: list[dict[str, Any]],
) -> list[str]:
    """
    Check if currency/asAt information is properly disclosed.

    Week 11: Full implementation
    Week 4: Basic check for currency mentions
    """
    issues = []

    # Check if answer mentions dates or currency
    has_date_mention = bool(re.search(r"\d{4}", answer))
    has_currency_mention = "as at" in answer.lower() or "as of" in answer.lower()

    # Extract max asAt from excerpts if available
    max_asat = None
    for excerpt in excerpts:
        asat = excerpt.get("asAt") or excerpt.get("effectiveFrom")
        if asat:
            if max_asat is None or asat > max_asat:
                max_asat = asat

    if max_asat and not has_currency_mention:
        issues.append(f"Answer does not disclose currency (excerpt asAt: {max_asat})")

    return issues


class VerifierService:
    """Service for verifying grounded legal answers."""

    def __init__(self):
        logger.info("VerifierService initialized")

    async def verify(
        self,
        input_data: VerifierInput,
    ) -> VerifierVerdict:
        """
        Verify a generated answer against retrieved excerpts.

        Week 4: citation realism + section realism (blocking), NLI (log-only)
        """
        logger.info(f"Verifying answer for query: {input_data.query[:100]}...")

        citation_issues = check_citation_realism(
            input_data.answer,
            input_data.excerpts,
        )

        section_issues = check_section_realism(
            input_data.answer,
            input_data.excerpts,
        )

        invented_acts = check_invented_acts(
            input_data.answer,
            input_data.excerpts,
            input_data.query,
        )

        # NLI is log-only in Week 4
        entailment_issues = await check_nli_entailment(
            input_data.answer,
            input_data.excerpts,
            input_data.query,
        )

        # Currency disclosure is informational in Week 4
        currency_issues = check_currency_disclosure(
            input_data.answer,
            input_data.excerpts,
        )

        # Determine if answer is grounded
        all_issues = citation_issues + section_issues + invented_acts + entailment_issues

        grounded = len(all_issues) == 0

        # Determine if repair should be attempted
        should_repair = grounded or (
            len(citation_issues) <= 2 and len(section_issues) <= 2 and len(invented_acts) == 0
        )

        # Build suggested repairs
        suggested_repairs = []
        if citation_issues:
            suggested_repairs.append("Fix citation numbers to match retrieved excerpts")
        if section_issues:
            suggested_repairs.append("Verify section references against excerpt text")
        if invented_acts:
            suggested_repairs.append("Remove invented Act names not in excerpts")

        # Build summary
        if grounded:
            summary = "Answer is grounded in retrieved excerpts"
        else:
            summary = f"Verification failed: {len(all_issues)} issue(s) found"

        verdict = VerifierVerdict(
            grounded=grounded,
            citation_issues=citation_issues,
            section_issues=section_issues,
            entailment_issues=entailment_issues,
            currency_issues=currency_issues,
            confidence=0.9 if grounded else 0.3,
            suggested_repairs=suggested_repairs[:3],
            should_repair=should_repair and not input_data.is_repair,  # Only repair once
            summary=summary,
        )

        logger.info(f"Verification complete: grounded={grounded}, issues={len(all_issues)}")
        return verdict


# Global instance for dependency injection
verifier_service = VerifierService()
