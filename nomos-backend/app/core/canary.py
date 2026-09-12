"""
Canary deployment and rollback infrastructure.

Week 4 E1: 10% ZA canary to v2 with instant rollback capability.
This provides safe, gradual rollout with immediate rollback if SLOs are breached.

Canary flow:
1. Feature flag controls canary percentage (0-100%)
2. User hash determines if they receive v2 or v1
3. SLO breaches trigger automatic rollback
4. Manual rollback available via feature flag
"""
import hashlib
import logging

import structlog
from typing import Any

from app.core.config import settings

logger = structlog.get_logger(__name__)


class CanaryManager:
    """Manages canary rollout and rollback logic."""

    def __init__(self):
        self.logger = logger.bind(service="CanaryManager")
        self.logger.info(
            "Canary manager initialized",
            canary_percentage=getattr(settings, "CANARY_PERCENTAGE", 0),
            rollback_mode=getattr(settings, "ROLLBACK_MODE", False),
        )

    def is_canary_user(self, user_id: str | None, jurisdiction: str = "za") -> bool:
        """
        Determine if user should receive canary (v2) or stable (v1) version.

        Uses deterministic hashing to ensure consistent assignment.
        Only applies to ZA jurisdiction initially.
        """
        if jurisdiction != "za":
            return False

        if getattr(settings, "ROLLBACK_MODE", False):
            self.logger.info("Rollback mode active, serving v1 to all users")
            return False

        canary_percentage = getattr(settings, "CANARY_PERCENTAGE", 0)
        if canary_percentage == 0:
            return False
        if canary_percentage >= 100:
            return True

        if not user_id:
            # No user ID, use random sampling
            import random
            return random.random() < (canary_percentage / 100)

        # Deterministic sampling based on user ID
        hash_digest = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        threshold = int(canary_percentage / 100 * (2**32))
        return hash_digest < threshold

    def get_canary_status(self) -> dict[str, Any]:
        """Get current canary deployment status."""
        return {
            "canary_percentage": getattr(settings, "CANARY_PERCENTAGE", 0),
            "rollback_mode": getattr(settings, "ROLLBACK_MODE", False),
            "jurisdiction": "za",
        }

    def should_trigger_rollback(self, slo_metrics: dict[str, Any]) -> bool:
        """
        Determine if SLO breach should trigger automatic rollback.

        SLO thresholds (Week 4 E1):
        - p95 latency: < 8s
        - 5xx rate: < 0.5%
        - Refusal rate shift: < 10% absolute change
        """
        rollback = False
        reasons = []

        # Check p95 latency
        p95_latency = slo_metrics.get("p95_latency_ms", 0) / 1000
        if p95_latency > 8.0:
            rollback = True
            reasons.append(f"p95 latency {p95_latency:.2f}s exceeds 8s threshold")

        # Check 5xx rate
        error_rate = slo_metrics.get("error_rate_5xx", 0)
        if error_rate > 0.005:  # 0.5%
            rollback = True
            reasons.append(f"5xx rate {error_rate:.2%} exceeds 0.5% threshold")

        # Check refusal rate shift
        refusal_rate = slo_metrics.get("refusal_rate", 0)
        baseline_refusal_rate = slo_metrics.get("baseline_refusal_rate", 0)
        refusal_shift = abs(refusal_rate - baseline_refusal_rate)
        if refusal_shift > 0.10:  # 10% absolute change
            rollback = True
            reasons.append(
                f"Refusal rate shift {refusal_shift:.2%} exceeds 10% threshold "
                f"(current: {refusal_rate:.2%}, baseline: {baseline_refusal_rate:.2%})"
            )

        if rollback:
            self.logger.warning(
                "SLO breach detected, rollback recommended",
                reasons=reasons,
                metrics=slo_metrics,
            )

        return rollback


# Global instance
canary_manager = CanaryManager()


def get_canary_manager() -> CanaryManager:
    """Get canary manager instance."""
    return canary_manager
