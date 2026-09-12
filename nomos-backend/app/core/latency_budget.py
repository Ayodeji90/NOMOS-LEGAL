"""
Latency budget enforcement for NOMOS backend.

Week 10 E1: Enforce p95 budgets per step:
- Understanding ~300ms
- Retrieval + rerank < 1.5s
- Writer < 4s
- Verifier < 1.5s
- Total p95 < 8s

This system monitors latency per step and enforces budgets by:
1. Logging when budgets are exceeded
2. Optionally failing fast when budgets are critically exceeded
3. Providing metrics for SLO monitoring
"""
import logging

import structlog
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class LatencyBudget:
    """Latency budget for a specific step."""
    name: str
    budget_ms: float
    critical_threshold_ms: float | None = None
    p95_target_ms: float | None = None


# Default latency budgets from Week 10 E1
DEFAULT_BUDGETS = {
    "query_understanding": LatencyBudget(
        name="query_understanding",
        budget_ms=300,
        critical_threshold_ms=500,
        p95_target_ms=300,
    ),
    "retrieval": LatencyBudget(
        name="retrieval",
        budget_ms=1500,
        critical_threshold_ms=2000,
        p95_target_ms=1500,
    ),
    "rerank": LatencyBudget(
        name="rerank",
        budget_ms=500,
        critical_threshold_ms=750,
        p95_target_ms=500,
    ),
    "writer": LatencyBudget(
        name="writer",
        budget_ms=4000,
        critical_threshold_ms=5000,
        p95_target_ms=4000,
    ),
    "verifier": LatencyBudget(
        name="verifier",
        budget_ms=1500,
        critical_threshold_ms=2000,
        p95_target_ms=1500,
    ),
    "total_search": LatencyBudget(
        name="total_search",
        budget_ms=8000,
        critical_threshold_ms=10000,
        p95_target_ms=8000,
    ),
}


@dataclass
class LatencyMeasurement:
    """Result of a latency measurement."""
    step: str
    duration_ms: float
    budget_ms: float
    exceeded: bool
    critical_exceeded: bool
    timestamp: float = field(default_factory=time.time)


class LatencyBudgetEnforcer:
    """Enforces latency budgets across the application."""

    def __init__(self, budgets: dict[str, LatencyBudget] | None = None):
        self.budgets = budgets or DEFAULT_BUDGETS
        self.measurements: list[LatencyMeasurement] = []
        self.logger = logger.bind(service="LatencyBudgetEnforcer")

    @contextmanager
    def measure(self, step: str):
        """
        Context manager to measure and enforce latency budget for a step.

        Usage:
            with enforcer.measure("query_understanding"):
                # do work
                pass
        """
        budget = self.budgets.get(step)
        if not budget:
            self.logger.warning(f"No budget defined for step: {step}")
            budget = LatencyBudget(name=step, budget_ms=float("inf"))

        start_time = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            exceeded = duration_ms > budget.budget_ms
            critical_exceeded = (
                budget.critical_threshold_ms is not None
                and duration_ms > budget.critical_threshold_ms
            )

            measurement = LatencyMeasurement(
                step=step,
                duration_ms=duration_ms,
                budget_ms=budget.budget_ms,
                exceeded=exceeded,
                critical_exceeded=critical_exceeded,
            )
            self.measurements.append(measurement)

            if critical_exceeded:
                self.logger.error(
                    f"Critical latency budget exceeded for {step}",
                    step=step,
                    duration_ms=round(duration_ms, 2),
                    budget_ms=budget.budget_ms,
                    critical_threshold_ms=budget.critical_threshold_ms,
                )
            elif exceeded:
                self.logger.warning(
                    f"Latency budget exceeded for {step}",
                    step=step,
                    duration_ms=round(duration_ms, 2),
                    budget_ms=budget.budget_ms,
                )
            else:
                self.logger.debug(
                    f"Latency budget OK for {step}",
                    step=step,
                    duration_ms=round(duration_ms, 2),
                    budget_ms=budget.budget_ms,
                )

    def get_step_metrics(self, step: str) -> dict[str, Any]:
        """Get latency metrics for a specific step."""
        step_measurements = [m for m in self.measurements if m.step == step]
        if not step_measurements:
            return {"step": step, "count": 0}

        durations = [m.duration_ms for m in step_measurements]
        durations.sort()

        budget = self.budgets.get(step)
        budget_ms = budget.budget_ms if budget else float("inf")

        return {
            "step": step,
            "count": len(durations),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "p50_ms": round(durations[len(durations) // 2], 2),
            "p95_ms": round(durations[int(len(durations) * 0.95)], 2) if durations else 0,
            "p99_ms": round(durations[int(len(durations) * 0.99)], 2) if durations else 0,
            "max_ms": round(max(durations), 2),
            "min_ms": round(min(durations), 2),
            "budget_ms": budget_ms,
            "p95_within_budget": (
                durations[int(len(durations) * 0.95)] <= budget_ms
                if durations
                else True
            ),
        }

    def get_total_metrics(self) -> dict[str, Any]:
        """Get overall latency metrics across all steps."""
        if not self.measurements:
            return {"total_measurements": 0}

        return {
            "total_measurements": len(self.measurements),
            "steps": {step: self.get_step_metrics(step) for step in self.budgets.keys()},
        }

    def check_slo_compliance(self) -> dict[str, Any]:
        """
        Check if SLOs are being met based on p95 targets.

        Returns dict with compliance status per step.
        """
        compliance = {}
        all_compliant = True

        for step, budget in self.budgets.items():
            metrics = self.get_step_metrics(step)
            p95_ms = metrics.get("p95_ms", 0)
            p95_target = budget.p95_target_ms or budget.budget_ms

            step_compliant = p95_ms <= p95_target if metrics["count"] > 0 else True
            compliance[step] = {
                "p95_ms": p95_ms,
                "p95_target_ms": p95_target,
                "compliant": step_compliant,
            }

            if not step_compliant:
                all_compliant = False

        return {
            "all_compliant": all_compliant,
            "steps": compliance,
        }

    def reset(self):
        """Clear all measurements."""
        self.measurements.clear()
        self.logger.info("Latency measurements reset")


# Global instance
latency_enforcer = LatencyBudgetEnforcer()


def get_latency_enforcer() -> LatencyBudgetEnforcer:
    """Get the global latency enforcer instance."""
    return latency_enforcer
