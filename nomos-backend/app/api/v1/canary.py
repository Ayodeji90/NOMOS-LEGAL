"""
Canary deployment management endpoints.

Week 4 E1: Admin endpoints for canary management and SLO monitoring.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.canary import canary_manager
from app.core.config import settings

router = APIRouter()


class CanaryStatusResponse(BaseModel):
    canary_percentage: int
    rollback_mode: bool
    jurisdiction: str


class SLOMetrics(BaseModel):
    p95_latency_ms: float
    error_rate_5xx: float
    refusal_rate: float
    baseline_refusal_rate: float


class RollbackRequest(BaseModel):
    enable: bool
    reason: str | None = None


@router.get("/status", response_model=CanaryStatusResponse)
async def get_canary_status() -> CanaryStatusResponse:
    """Get current canary deployment status."""
    status = canary_manager.get_canary_status()
    return CanaryStatusResponse(**status)


@router.post("/rollback")
async def set_rollback_mode(request: RollbackRequest) -> dict:
    """
    Enable or disable rollback mode.

    When rollback mode is enabled, all users receive v1 (stable) version.
    This provides instant rollback capability if SLOs are breached.
    """
    # Note: In production, this should be protected by admin authentication
    # For now, we'll log the action
    import structlog

    logger = structlog.get_logger(__name__)
    logger.info(
        "Rollback mode changed",
        enable=request.enable,
        reason=request.reason,
    )

    # In a real implementation, this would update Secret Manager or
    # a configuration service. For now, we'll return success.
    return {
        "success": True,
        "rollback_mode": request.enable,
        "message": "Rollback mode updated (requires config service integration)",
    }


@router.post("/check-slo")
async def check_slo_breach(metrics: SLOMetrics) -> dict:
    """
    Check if SLO metrics indicate a breach that should trigger rollback.

    SLO thresholds:
    - p95 latency: < 8s
    - 5xx rate: < 0.5%
    - Refusal rate shift: < 10% absolute change
    """
    should_rollback = canary_manager.should_trigger_rollback(metrics.dict())

    return {
        "should_rollback": should_rollback,
        "message": "SLO check completed",
    }


@router.get("/user/{user_id}")
async def check_user_canary(user_id: str, jurisdiction: str = "za") -> dict:
    """Check if a specific user is in the canary group."""
    is_canary = canary_manager.is_canary_user(user_id, jurisdiction)
    return {
        "user_id": user_id,
        "jurisdiction": jurisdiction,
        "is_canary": is_canary,
        "version": "v2" if is_canary else "v1",
    }
