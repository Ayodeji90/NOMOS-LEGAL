"""
Repair loop service for bounded retry on verification failure.

Implements the repair loop: verify → if failed, retry once with failure reasons → refuse if still fails.
Reference: REDESIGN.md section 4 (Grounding & Verification)
"""

import logging

from app.schemas.verifier import VerifierInput, VerifierVerdict
from app.schemas.writer import WriterInput, WriterOutput
from app.services.ai.verifier_service import verifier_service
from app.services.ai.writer_service import writer_service

logger = logging.getLogger(__name__)


class RepairService:
    """Service for managing the repair loop with bounded retries."""

    def __init__(self):
        self._max_repair_attempts = 1  # One repair retry max
        logger.info("RepairService initialized with max_repair_attempts=1")

    async def write_with_verification(
        self,
        query: str,
        jurisdiction: str,
        excerpts: list[dict],
        history: list[dict] | None = None,
        understanding: dict | None = None,
    ) -> tuple[WriterOutput, VerifierVerdict, int]:
        """
        Generate answer with verification and optional repair loop.

        Returns:
            (writer_output, verifier_verdict, attempt_count)

        Process:
        1. Generate initial answer
        2. Verify answer
        3. If verification fails and not a repair attempt:
           - Retry with failure reasons injected
           - Verify again
        4. Return final answer and verdict
        """
        attempt = 0
        current_writer_output: WriterOutput | None = None
        current_verdict: VerifierVerdict | None = None
        verification_failures: list[str] = []

        while attempt <= self._max_repair_attempts:
            attempt += 1

            logger.info(f"Write/verify attempt {attempt}/{self._max_repair_attempts + 1}")

            # Build writer input
            writer_input = WriterInput(
                query=query,
                jurisdiction=jurisdiction,
                excerpts=excerpts,
                understanding=understanding,
                history=history or [],
                is_repair=(attempt > 1),
                verification_failures=verification_failures if attempt > 1 else None,
            )

            # Generate answer
            writer_output = await writer_service.write_answer(writer_input)
            current_writer_output = writer_output

            # Build verifier input
            verifier_input = VerifierInput(
                query=query,
                answer=writer_output.directAnswer + "\n" + writer_output.explanation,
                excerpts=excerpts,
                jurisdiction=jurisdiction,
                is_repair=(attempt > 1),
                previous_failures=verification_failures if attempt > 1 else None,
            )

            # Verify answer
            verdict = await verifier_service.verify(verifier_input)
            current_verdict = verdict

            logger.info(
                f"Attempt {attempt} verification: grounded={verdict.grounded}, "
                f"issues={len(verdict.citation_issues) + len(verdict.section_issues) + len(verdict.entailment_issues)}"
            )

            # If grounded, we're done
            if verdict.grounded:
                logger.info(f"Answer grounded on attempt {attempt}")
                return writer_output, verdict, attempt

            # If not grounded and we have attempts left, collect failures and retry
            if attempt <= self._max_repair_attempts:
                verification_failures = []
                verification_failures.extend(verdict.citation_issues)
                verification_failures.extend(verdict.section_issues)
                verification_failures.extend(verdict.entailment_issues)
                verification_failures.extend(verdict.currency_issues)

                logger.info(
                    f"Verification failed on attempt {attempt}, "
                    f"retrying with {len(verification_failures)} failure reasons"
                )
            else:
                logger.warning(
                    f"Verification failed after {attempt} attempts, returning ungrounded answer"
                )
                break

        # Return the last attempt's results
        return current_writer_output, current_verdict, attempt

    async def should_refuse(
        self,
        verdict: VerifierVerdict,
        attempt_count: int,
    ) -> bool:
        """
        Determine if we should refuse based on verification results.

        Refuse if:
        - Verification failed after max repair attempts
        - Critical issues remain (invented Acts, bad citations)
        """
        if verdict.grounded:
            return False

        if attempt_count > self._max_repair_attempts:
            # Failed after repair attempts
            return True

        # Check for critical issues that should trigger refusal
        if verdict.citation_issues:
            # Bad citations are critical
            return True

        if verdict.section_issues:
            # Invented sections are critical
            return True

        # If only entailment issues (log-only in Week 4), don't refuse yet
        if verdict.entailment_issues and not verdict.citation_issues and not verdict.section_issues:
            return False

        return False


# Global instance for dependency injection
repair_service = RepairService()
