from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import get_quota_manager
from app.db.session import get_db

router = APIRouter(prefix="/improve", tags=["Improve"])


class ImproveRequest(BaseModel):
    documentText: str = Field(min_length=1, max_length=50000)
    instruction: str = Field(min_length=1, max_length=5000)
    jurisdiction: str = Field(default="za", pattern="^za$")


class ImproveResponse(BaseModel):
    improvedText: str
    changes: list[dict]
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


@router.post("", response_model=ImproveResponse)
async def improve(
    request: Request,
    improve_request: ImproveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImproveResponse:
    user_id = getattr(request.state, "user_id", None) or "anonymous"
    quota_status = await enforce_quotas(user_id)

    quota_manager = get_quota_manager()
    await quota_manager.consume_quota(user_id, "writer")

    return ImproveResponse(
        improvedText=improve_request.documentText,
        changes=[],
        grounded=False,
        writer={"skipped": "not_implemented", "model": None, "usedWriter": False},
    )
