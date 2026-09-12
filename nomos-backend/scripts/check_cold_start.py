#!/usr/bin/env python3
"""
Cold start performance check for Cloud Run.

Week 8 E1: Verify cold-start performance after image slimming.
This script measures cold start latency by triggering new instances.
"""
import argparse
import asyncio
import logging
import time
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ColdStartChecker:
    """Measure cold start latency for Cloud Run instances."""

    def __init__(self, url: str, warmup_requests: int = 5):
        self.url = url
        self.warmup_requests = warmup_requests
        self.logger = logger.bind(url=url)

    async def check_cold_start(self) -> dict[str, Any]:
        """
        Measure cold start latency by making requests to new instances.

        Strategy: Make requests with different query parameters to trigger
        new instances, measure time to first response.
        """
        self.logger.info("Starting cold start check")

        # First, warm up any existing instances
        self.logger.info(f"Warming up with {self.warmup_requests} requests")
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(self.warmup_requests):
                try:
                    await client.get(f"{self.url}/health")
                except Exception as e:
                    self.logger.warning(f"Warmup request {i+1} failed: {e}")

        # Wait a bit for instances to scale down
        self.logger.info("Waiting 60s for instances to scale down...")
        await asyncio.sleep(60)

        # Measure cold starts
        cold_start_times = []
        num_measurements = 3

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(num_measurements):
                # Use unique query to potentially trigger new instance
                start_time = time.time()
                try:
                    response = await client.get(f"{self.url}/health?cold_start_check={i}")
                    latency = time.time() - start_time
                    cold_start_times.append(latency)
                    self.logger.info(
                        f"Cold start measurement {i+1}/{num_measurements}",
                        latency_s=round(latency, 2),
                        status_code=response.status_code,
                    )
                except Exception as e:
                    self.logger.error(f"Cold start measurement {i+1} failed: {e}")

        # Calculate statistics
        if cold_start_times:
            avg_cold_start = sum(cold_start_times) / len(cold_start_times)
            max_cold_start = max(cold_start_times)
            min_cold_start = min(cold_start_times)

            return {
                "url": self.url,
                "measurements": num_measurements,
                "cold_start_times": [round(t, 2) for t in cold_start_times],
                "avg_cold_start_s": round(avg_cold_start, 2),
                "max_cold_start_s": round(max_cold_start, 2),
                "min_cold_start_s": round(min_cold_start, 2),
                "target_max_s": 10.0,  # Cloud Run cold start target
                "within_target": max_cold_start <= 10.0,
            }
        else:
            return {
                "url": self.url,
                "error": "No successful measurements",
            }


async def check_warm_latency(url: str) -> dict[str, Any]:
    """Measure warm latency (after instance is warmed up)."""
    logger.info("Measuring warm latency")

    warm_latencies = []
    num_requests = 20

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(num_requests):
            start_time = time.time()
            try:
                response = await client.get(f"{self.url}/health")
                latency = time.time() - start_time
                warm_latencies.append(latency)
            except Exception as e:
                logger.warning(f"Warm request {i+1} failed: {e}")

    if warm_latencies:
        avg_warm = sum(warm_latencies) / len(warm_latencies)
        p50 = sorted(warm_latencies)[len(warm_latencies) // 2]
        p95 = sorted(warm_latencies)[int(len(warm_latencies) * 0.95)]

        return {
            "url": url,
            "requests": num_requests,
            "avg_warm_latency_ms": round(avg_warm * 1000, 2),
            "p50_warm_latency_ms": round(p50 * 1000, 2),
            "p95_warm_latency_ms": round(p95 * 1000, 2),
        }
    else:
        return {"url": url, "error": "No successful measurements"}


async def main():
    parser = argparse.ArgumentParser(description="Check Cloud Run cold start performance")
    parser.add_argument("--url", required=True, help="Cloud Run service URL")
    parser.add_argument("--warmup", type=int, default=5, help="Number of warmup requests")

    args = parser.parse_args()

    checker = ColdStartChecker(args.url, args.warmup)

    # Check cold start
    cold_start_result = await checker.check_cold_start()

    # Check warm latency
    warm_result = await check_warm_latency(args.url)

    # Print results
    print("\n" + "=" * 60)
    print("COLD START PERFORMANCE RESULTS")
    print("=" * 60)
    print(f"URL: {args.url}")
    print(f"\nCold Start:")
    print(f"  Measurements: {cold_start_result.get('measurements', 0)}")
    print(f"  Average: {cold_start_result.get('avg_cold_start_s', 0):.2f}s")
    print(f"  Max: {cold_start_result.get('max_cold_start_s', 0):.2f}s")
    print(f"  Min: {cold_start_result.get('min_cold_start_s', 0):.2f}s")
    print(f"  Target: {cold_start_result.get('target_max_s', 0):.2f}s")
    print(f"  Within Target: {'✅' if cold_start_result.get('within_target') else '❌'}")

    print(f"\nWarm Latency:")
    print(f"  Requests: {warm_result.get('requests', 0)}")
    print(f"  Average: {warm_result.get('avg_warm_latency_ms', 0):.2f}ms")
    print(f"  P50: {warm_result.get('p50_warm_latency_ms', 0):.2f}ms")
    print(f"  P95: {warm_result.get('p95_warm_latency_ms', 0):.2f}ms")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
