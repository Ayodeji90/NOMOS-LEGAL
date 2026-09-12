"""
Admin endpoints for access management.

Week 2 E6: Admin/access endpoints parity with Node backend.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.access_gate import access_gate
from app.api.v1.auth import get_current_user_flexible
from app.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])


class AllowlistAddRequest(BaseModel):
    email: str


class AllowlistRemoveRequest(BaseModel):
    email: str


class AllowlistResponse(BaseModel):
    allowlist: list[str]
    count: int


@router.get("/access/allowlist", response_model=AllowlistResponse)
async def get_allowlist(
    current_user: Annotated[User, Depends(get_current_user_flexible)]
) -> AllowlistResponse:
    """
    Get current allowlist.

    Requires admin privileges (in production, check user role).
    """
    # In production, verify user is admin
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin privileges required")

    allowlist = access_gate.get_allowlist()
    return AllowlistResponse(allowlist=allowlist, count=len(allowlist))


@router.post("/access/allowlist/add")
async def add_to_allowlist(
    request: AllowlistAddRequest,
    current_user: Annotated[User, Depends(get_current_user_flexible)]
) -> dict:
    """
    Add email to allowlist.

    Requires admin privileges (in production, check user role).
    """
    # In production, verify user is admin
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin privileges required")

    access_gate.add_to_allowlist(request.email)
    return {"message": f"Email {request.email} added to allowlist"}


@router.post("/access/allowlist/remove")
async def remove_from_allowlist(
    request: AllowlistRemoveRequest,
    current_user: Annotated[User, Depends(get_current_user_flexible)]
) -> dict:
    """
    Remove email from allowlist.

    Requires admin privileges (in production, check user role).
    """
    # In production, verify user is admin
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin privileges required")

    access_gate.remove_from_allowlist(request.email)
    return {"message": f"Email {request.email} removed from allowlist"}


@router.get("/access/status")
async def get_access_status(
    email: str,
    current_user: Annotated[User, Depends(get_current_user_flexible)]
) -> dict:
    """
    Check if email is allowed access.

    Requires admin privileges (in production, check user role).
    """
    # In production, verify user is admin
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin privileges required")

    allowed, reason = access_gate.check_access(email=email)
    return {
        "email": email,
        "allowed": allowed,
        "reason": reason,
    }
