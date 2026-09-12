"""
Smoke load test for 20 RPS (requests per second).

This test verifies the application can handle sustained load of 20 RPS.
"""
import asyncio
import time
from statistics import mean, median

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_20_rps_health_endpoint():
    """Test that /health endpoint can handle 20 RPS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Warm up
        await client.get("/health")

        # Test 20 RPS for 10 seconds (200 requests total)
        duration_seconds = 10
        target_rps = 20
        total_requests = duration_seconds * target_rps

        latencies = []
        error_count = 0
        start_time = time.time()

        async def make_request(request_num: int):
            nonlocal error_count
            try:
                req_start = time.time()
                response = await client.get("/health")
                latency = time.time() - req_start
                latencies.append(latency)
                assert response.status_code == 200
                return True
            except Exception:
                error_count += 1
                return False

        # Fire requests at target rate
        tasks = []
        for i in range(total_requests):
            # Calculate when this request should fire
            target_time = start_time + (i / target_rps)
            current_time = time.time()
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)

            task = asyncio.create_task(make_request(i))
            tasks.append(task)

        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        actual_duration = time.time() - start_time
        successful_requests = sum(1 for r in results if r is True)

        # Calculate statistics
        if latencies:
            avg_latency = mean(latencies) * 1000  # Convert to ms
            median_latency = median(latencies) * 1000
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] * 1000 if latencies else 0
        else:
            avg_latency = median_latency = p95_latency = 0

        actual_rps = successful_requests / actual_duration

        # Assertions
        assert error_count == 0, f"Expected no errors, got {error_count}"
        assert successful_requests >= total_requests * 0.95, f"Expected at least 95% success rate, got {successful_requests}/{total_requests}"
        assert actual_rps >= target_rps * 0.9, f"Expected at least 90% of target RPS, got {actual_rps:.2f}"
        assert avg_latency < 100, f"Average latency too high: {avg_latency:.2f}ms"
        assert p95_latency < 500, f"P95 latency too high: {p95_latency:.2f}ms"

        print("\nLoad Test Results:")
        print(f"  Target RPS: {target_rps}")
        print(f"  Actual RPS: {actual_rps:.2f}")
        print(f"  Duration: {actual_duration:.2f}s")
        print(f"  Success Rate: {successful_requests}/{total_requests} ({successful_requests/total_requests*100:.1f}%)")
        print(f"  Avg Latency: {avg_latency:.2f}ms")
        print(f"  Median Latency: {median_latency:.2f}ms")
        print(f"  P95 Latency: {p95_latency:.2f}ms")
        print(f"  Errors: {error_count}")


@pytest.mark.asyncio
async def test_20_rps_readiness_endpoint():
    """Test that /ready endpoint can handle 20 RPS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Warm up
        await client.get("/ready")

        # Test 20 RPS for 5 seconds (100 requests total)
        duration_seconds = 5
        target_rps = 20
        total_requests = duration_seconds * target_rps

        latencies = []
        error_count = 0
        start_time = time.time()

        async def make_request(request_num: int):
            nonlocal error_count
            try:
                req_start = time.time()
                response = await client.get("/ready")
                latency = time.time() - req_start
                latencies.append(latency)
                assert response.status_code == 200
                return True
            except Exception:
                error_count += 1
                return False

        # Fire requests at target rate
        tasks = []
        for i in range(total_requests):
            target_time = start_time + (i / target_rps)
            current_time = time.time()
            if current_time < target_time:
                await asyncio.sleep(target_time - current_time)

            task = asyncio.create_task(make_request(i))
            tasks.append(task)

        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        actual_duration = time.time() - start_time
        successful_requests = sum(1 for r in results if r is True)

        # Assertions
        assert error_count == 0, f"Expected no errors, got {error_count}"
        assert successful_requests >= total_requests * 0.95, "Expected at least 95% success rate"
        assert successful_requests / actual_duration >= target_rps * 0.9, "Expected at least 90% of target RPS"


@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test handling of concurrent requests (burst load)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Fire 100 concurrent requests
        concurrent_requests = 100

        async def make_request():
            try:
                response = await client.get("/health")
                return response.status_code == 200
            except Exception:
                return False

        start_time = time.time()
        tasks = [make_request() for _ in range(concurrent_requests)]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        successful = sum(results)

        # Assertions
        assert successful >= concurrent_requests * 0.95, "Expected at least 95% success rate in burst"
        assert duration < 10, f"Burst of {concurrent_requests} requests took too long: {duration:.2f}s"

        print("\nBurst Test Results:")
        print(f"  Concurrent Requests: {concurrent_requests}")
        print(f"  Successful: {successful}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Throughput: {successful/duration:.2f} RPS")
