"""Jurisdiction and named-Act gates for honest jurisdiction enforcement.

These gates ensure the system doesn't silently answer questions with wrong-country
or wrong-Act excerpts. They are blocking gates that refuse answers when:
1. Jurisdiction mismatch: Query jurisdiction doesn't match retrieved excerpts
2. Named-Act gate: Query names an Act but no excerpts from that Act are retrieved

Week 6: Promote from log-only to blocking (Milestone M2).
"""

import logging
from enum import Enum
from typing import Any

from app.services.retrieval.za_focus import detect_act_focus

logger = logging.getLogger(__name__)


class GateResult(Enum):
    """Result of gate check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"  # Gate not applicable


class JurisdictionGate:
    """Gate to detect jurisdiction mismatches."""

    @staticmethod
    def check(
        query: str,
        query_jurisdiction: str,
        excerpts: list[dict[str, Any]],
    ) -> tuple[GateResult, str | None, str | None]:
        """
        Check if query jurisdiction matches retrieved excerpts.

        Args:
            query: User query
            query_jurisdiction: Jurisdiction from query understanding or picker (e.g., 'za', 'gb')
            excerpts: Retrieved excerpts with metadata

        Returns:
            (gate_result, failure_reason, suggested_jurisdiction)
        """
        if not excerpts:
            # No excerpts - let other gates handle this
            return GateResult.SKIP, None, None

        # Extract jurisdictions from excerpts
        excerpt_jurisdictions = set()
        for excerpt in excerpts:
            jur = excerpt.get("jurisdiction") or excerpt.get("country")
            if jur:
                excerpt_jurisdictions.add(str(jur).lower())

        if not excerpt_jurisdictions:
            # Excerpts don't have jurisdiction metadata - skip this gate
            logger.warning("Excerpts lack jurisdiction metadata, skipping jurisdiction gate")
            return GateResult.SKIP, None, None

        query_jur = query_jurisdiction.lower()

        # Check if query jurisdiction matches any excerpt jurisdiction
        if query_jur in excerpt_jurisdictions:
            logger.info(
                f"Jurisdiction gate PASS: query={query_jur}, excerpts={excerpt_jurisdictions}"
            )
            return GateResult.PASS, None, None

        # Jurisdiction mismatch detected
        logger.warning(
            f"Jurisdiction gate FAIL: query={query_jur}, "
            f"excerpt_jurisdictions={excerpt_jurisdictions}"
        )

        # Suggest the most common excerpt jurisdiction
        suggested = max(excerpt_jurisdictions, key=lambda x: list(excerpt_jurisdictions).count(x))

        failure_reason = (
            f"Query jurisdiction ({query_jurisdiction.upper()}) does not match "
            f"retrieved excerpts (jurisdictions: {', '.join(excerpt_jurisdictions)}). "
            f"Please select the correct jurisdiction."
        )

        return GateResult.FAIL, failure_reason, suggested


class NamedActGate:
    """Gate to detect when query names an Act but no excerpts from that Act are retrieved."""

    @staticmethod
    def check(
        query: str,
        jurisdiction: str,
        excerpts: list[dict[str, Any]],
    ) -> tuple[GateResult, str | None]:
        """
        Check if named Act in query has matching excerpts.

        Args:
            query: User query
            jurisdiction: Query jurisdiction
            excerpts: Retrieved excerpts with metadata

        Returns:
            (gate_result, failure_reason)
        """
        # Detect if query has Act focus
        act_focus = detect_act_focus(query)

        if not act_focus:
            # No named Act in query - gate not applicable
            return GateResult.SKIP, None

        # Extract Act identifiers from focus (ActAlias dataclass)
        act_needles = act_focus.title_needles if hasattr(act_focus, "title_needles") else []
        act_keys = act_focus.keys if hasattr(act_focus, "keys") else []

        if not act_needles and not act_keys:
            return GateResult.SKIP, None

        # Check if any excerpt matches the named Act
        act_found = False
        for excerpt in excerpts:
            excerpt_text = str(excerpt.get("sourceText", "") or excerpt.get("text", "")).lower()
            excerpt_citation = str(excerpt.get("citation", "")).lower()
            excerpt_title = str(excerpt.get("title", "")).lower()

            # Check against needles and keys
            for needle in act_needles:
                if needle and needle.lower() in excerpt_text:
                    act_found = True
                    break
                if needle and needle.lower() in excerpt_citation:
                    act_found = True
                    break
                if needle and needle.lower() in excerpt_title:
                    act_found = True
                    break

            if act_found:
                break

            for key in act_keys:
                if key and len(str(key)) > 3 and str(key).lower() in excerpt_text:
                    act_found = True
                    break
                if key and len(str(key)) > 3 and str(key).lower() in excerpt_citation:
                    act_found = True
                    break

        if act_found:
            logger.info("Named-Act gate PASS: Act found in excerpts")
            return GateResult.PASS, None

        # Named Act not found in excerpts - gate failure
        act_name = act_needles[0] if act_needles else (act_keys[0] if act_keys else "the named Act")
        logger.warning(f"Named-Act gate FAIL: Act '{act_name}' not found in excerpts")

        failure_reason = (
            f"Query mentions '{act_name}' but no excerpts from that Act were retrieved. "
            f"Please try a more specific query or check if this Act is in the corpus."
        )

        return GateResult.FAIL, failure_reason


class GateService:
    """Service for running all gates and enforcing blocking behavior."""

    def __init__(self, blocking: bool = True):
        """Initialize gate service.

        Args:
            blocking: If True, gates are blocking (refuse answers). If False, log-only.
        """
        self._blocking = blocking
        logger.info(f"GateService initialized with blocking={blocking}")

    async def check_all_gates(
        self,
        query: str,
        jurisdiction: str,
        excerpts: list[dict[str, Any]],
    ) -> tuple[bool, list[str], str | None]:
        """
        Run all gates and determine if query should be refused.

        Args:
            query: User query
            jurisdiction: Query jurisdiction
            excerpts: Retrieved excerpts

        Returns:
            (should_refuse, failure_reasons, suggested_jurisdiction)
        """
        failure_reasons = []
        suggested_jurisdiction = None

        # Run jurisdiction gate
        jur_result, jur_reason, jur_suggested = JurisdictionGate.check(
            query=query,
            query_jurisdiction=jurisdiction,
            excerpts=excerpts,
        )

        if jur_result == GateResult.FAIL:
            failure_reasons.append(jur_reason or "Jurisdiction mismatch")
            suggested_jurisdiction = jur_suggested
        elif jur_result == GateResult.SKIP:
            logger.info("Jurisdiction gate skipped")

        # Run named-Act gate
        act_result, act_reason = NamedActGate.check(
            query=query,
            jurisdiction=jurisdiction,
            excerpts=excerpts,
        )

        if act_result == GateResult.FAIL:
            failure_reasons.append(act_reason or "Named Act not found")
        elif act_result == GateResult.SKIP:
            logger.info("Named-Act gate skipped")

        # Determine if should refuse
        should_refuse = len(failure_reasons) > 0 and self._blocking

        if should_refuse:
            logger.warning(f"Gates blocking: {len(failure_reasons)} failures")
        else:
            logger.info("Gates passed or non-blocking")

        return should_refuse, failure_reasons, suggested_jurisdiction


# Global instance for dependency injection
gate_service = GateService(blocking=True)
