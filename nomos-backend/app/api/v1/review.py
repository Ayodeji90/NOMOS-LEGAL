from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import get_quota_manager
from app.db.session import get_db

router = APIRouter(prefix="/review", tags=["Review"])


class ReviewRequest(BaseModel):
    documentText: str = Field(min_length=1, max_length=50000)
    focus: str | None = Field(default=None, max_length=5000)
    jurisdiction: str = Field(default="za", pattern="^za$")


class ReviewIssue(BaseModel):
    type: Literal["risk", "missing", "unclear", "non_compliant", "best_practice"]
    severity: Literal["high", "medium", "low"]
    location: str
    description: str
    suggestion: str | None = None
    citation: str | None = None


class ReviewResponse(BaseModel):
    issues: list[ReviewIssue]
    summary: str
    grounded: bool
    writer: dict


async def enforce_quotas(user_id: str) -> dict:
    quota_manager = get_quota_manager()
    quota_status = await quota_manager.get_quota_status(user_id)

    if quota_status["writer"]["used"] >= quota_status["writer"]["limit"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily writer quota exceeded",
        )

    return quota_status


@router.post("", response_model=ReviewResponse)
async def review(
    request: Request,
    review_request: ReviewRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewResponse:
    user_id = getattr(request.state, "user_id", None) or "anonymous"
    quota_status = await enforce_quotas(user_id)

    quota_manager = get_quota_manager()
    await quota_manager.consume_quota(user_id, "writer")

    return ReviewResponse(
        issues=[],
        summary="Review functionality is not yet available. Requires: 1) corpus ingestion for ZA, 2) hybrid retrieval pipeline, 3) writer LLM integration, 4) grounding verification.",
        grounded=False,
        writer={"skipped": "not_implemented", "model": None, "usedWriter": False},
    )
