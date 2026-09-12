from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import get_quota_manager
from app.db.session import get_db

router = APIRouter(prefix="/draft", tags=["Drafting"])


class DraftRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=5000)
    documentText: str | None = Field(default=None, max_length=50000)
    priorQa: list[dict] | None = None
    documentType: Literal["clause", "contract", "letter", "memo", "advice"] = "clause"
    draftGuidance: str | None = None
    jurisdiction: str = Field(default="za", pattern="^za$")


class DraftResponse(BaseModel):
    draft: str
    note: str
    documentType: str
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


@router.post("", response_model=DraftResponse)
async def draft(
    request: Request,
    draft_request: DraftRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DraftResponse:
    user_id = getattr(request.state, "user_id", None) or "anonymous"
    quota_status = await enforce_quotas(user_id)

    quota_manager = get_quota_manager()
    await quota_manager.consume_quota(user_id, "writer")

    return DraftResponse(
        draft="",
        note="Drafting functionality is not yet available. Requires: 1) corpus ingestion for ZA, 2) hybrid retrieval pipeline, 3) writer LLM integration, 4) grounding verification.",
        documentType=draft_request.documentType,
        grounded=False,
        writer={"skipped": "not_implemented", "model": None, "usedWriter": False},
    )
