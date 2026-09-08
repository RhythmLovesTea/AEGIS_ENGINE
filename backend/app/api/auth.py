"""AEGIS-Marine: Authentication & User Profile API Endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.core.security import CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.get(
    "/me",
    summary="Current Authenticated User Profile",
    description="Returns identity, active roles, and resolved permissions for the current bearer token.",
)
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns identity and permission profile for current user."""
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "name": current_user.name,
        "roles": current_user.roles,
        "permissions": sorted(current_user.permissions),
    }
