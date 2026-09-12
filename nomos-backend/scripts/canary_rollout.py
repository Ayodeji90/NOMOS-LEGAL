#!/usr/bin/env python3
"""
Canary rollout automation script.

Week 15 E1: Automated canary rollout 10% -> 50% -> 100% with SLO monitoring.
This script automates the canary rollout process with automatic rollback if SLOs are breached.
"""
import argparse
import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CanaryRollout:
    """Automated canary rollout with SLO monitoring."""

    def __init__(
        self,
        base_url: str,
        admin_key: str,
        slo_check_interval: int = 300,  # 5 minutes
        slo_breach_threshold: int = 3,  # Number of breaches before rollback
    ):
        self.base_url = base_url
        self.admin_key = admin_key
        self.slo_check_interval = slo_check_interval
        self.slo_breach_threshold = slo_breach_threshold
        self.slo_breach_count = 0
        self.logger = logger.bind(base_url=base_url)

    async def set_canary_percentage(self, percentage: int) -> bool:
        """Set canary percentage via admin API."""
        self.logger.info(f"Setting canary percentage to {percentage}%")

        # In production, this would call the admin API
        # For now, we'll simulate the call
        self.logger.info(f"Canary percentage set to {percentage}%")
        return True

    async def get_slo_metrics(self) -> dict[str, Any]:
        """
        Get current SLO metrics from monitoring system.

        Returns dict with:
        - p95_latency_ms
        - error_rate_5xx
        - refusal_rate
        - baseline_refusal_rate
        """
        # In production, this would query Cloud Monitoring
        # For now, return placeholder data
        return {
            "p95_latency_ms": 5000,
            "error_rate_5xx": 0.002,
            "refusal_rate": 0.15,
            "baseline_refusal_rate": 0.15,
        }

    async def check_slo_compliance(self, metrics: dict[str, Any]) -> bool:
        """
        Check if SLOs are being met.

        SLO thresholds:
        - p95 latency: < 8s
        - 5xx rate: < 0.5%
        - Refusal rate shift: < 10%
        """
        p95_latency = metrics.get("p95_latency_ms", 0) / 1000
        error_rate = metrics.get("error_rate_5xx", 0)
        refusal_rate = metrics.get("refusal_rate", 0)
        baseline_refusal = metrics.get("baseline_refusal_rate", 0)
        refusal_shift = abs(refusal_rate - baseline_refusal)

        compliant = (
            p95_latency < 8.0
            and error_rate < 0.005
            and refusal_shift < 0.10
        )

        if not compliant:
            self.logger.warning(
                "SLO breach detected",
                p95_latency_s=p95_latency,
                error_rate=error_rate,
                refusal_shift=refusal_shift,
            )

        return compliant

    async def monitor_phase(
        self,
        percentage: int,
        duration_hours: int,
    ) -> bool:
        """
        Monitor a canary phase for specified duration.

        Returns True if phase passed, False if rollback triggered.
        """
        self.logger.info(
            f"Starting canary phase at {percentage}%",
            duration_hours=duration_hours,
        )

        end_time = time.time() + (duration_hours * 3600)
        self.slo_breach_count = 0

        while time.time() < end_time:
            # Get SLO metrics
            metrics = await self.get_slo_metrics()

            # Check compliance
            compliant = await self.check_slo_compliance(metrics)

            if not compliant:
                self.slo_breach_count += 1
                self.logger.warning(
                    f"SLO breach {self.slo_breach_count}/{self.slo_breach_threshold}",
                )

                if self.slo_breach_count >= self.slo_breach_threshold:
                    self.logger.error("SLO breach threshold exceeded, triggering rollback")
                    return False
            else:
                self.slo_breach_count = 0

            # Wait for next check
            await asyncio.sleep(self.slo_check_interval)

        self.logger.info(f"Canary phase at {percentage}% completed successfully")
        return True

    async def trigger_rollback(self) -> bool:
        """Trigger immediate rollback to 0% canary."""
        self.logger.error("Triggering rollback to 0% canary")
        return await self.set_canary_percentage(0)

    async def execute_rollout(
        self,
        phases: list[tuple[int, int]],  # List of (percentage, duration_hours)
    ) -> dict[str, Any]:
        """
        Execute full canary rollout through all phases.

        Args:
            phases: List of (percentage, duration_hours) tuples

        Returns:
            Dict with rollout results
        """
        start_time = datetime.now()
        self.logger.info(
            "Starting canary rollout",
            phases=phases,
            start_time=start_time.isoformat(),
        )

        results = []
        for percentage, duration in phases:
            # Set canary percentage
            await self.set_canary_percentage(percentage)

            # Monitor phase
            phase_passed = await self.monitor_phase(percentage, duration)

            results.append({
                "percentage": percentage,
                "duration_hours": duration,
                "passed": phase_passed,
            })

            if not phase_passed:
                # Rollback and stop
                await self.trigger_rollback()
                break

        total_time = (datetime.now() - start_time).total_seconds()
        final_percentage = results[-1]["percentage"] if results else 0

        return {
            "success": all(r["passed"] for r in results),
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_time_hours": round(total_time / 3600, 2),
            "phases": results,
            "final_percentage": final_percentage,
        }


async def main():
    parser = argparse.ArgumentParser(description="Automated canary rollout")
    parser.add_argument("--url", required=True, help="Base URL for admin API")
    parser.add_argument("--admin-key", required=True, help="Admin API key")
    parser.add_argument(
        "--phases",
        nargs="*",
        default=["10,24", "50,24", "100,48"],
        help="Canary phases as 'percentage,duration_hours' (default: 10%%,24h 50%%,24h 100%%,48h)",
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=300,
        help="SLO check interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--breach-threshold",
        type=int,
        default=3,
        help="SLO breach threshold before rollback (default: 3)",
    )

    args = parser.parse_args()

    # Parse phases
    phases = []
    for phase_str in args.phases:
        percentage, duration = map(int, phase_str.split(","))
        phases.append((percentage, duration))

    # Execute rollout
    rollout = CanaryRollout(
        base_url=args.url,
        admin_key=args.admin_key,
        slo_check_interval=args.check_interval,
        slo_breach_threshold=args.breach_threshold,
    )

    result = await rollout.execute_rollout(phases)

    # Print results
    print("\n" + "=" * 60)
    print("CANARY ROLLOUT RESULTS")
    print("=" * 60)
    print(f"Success: {'✅' if result['success'] else '❌'}")
    print(f"Start Time: {result['start_time']}")
    print(f"End Time: {result['end_time']}")
    print(f"Total Time: {result['total_time_hours']} hours")
    print(f"Final Percentage: {result['final_percentage']}%")
    print("\nPhases:")
    for i, phase in enumerate(result["phases"], 1):
        status = "✅ PASSED" if phase["passed"] else "❌ FAILED"
        print(f"  Phase {i}: {phase['percentage']}% for {phase['duration_hours']}h - {status}")
    print("=" * 60)

    # Exit with appropriate code
    exit(0 if result["success"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
