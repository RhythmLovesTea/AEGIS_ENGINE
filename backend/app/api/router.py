"""AEGIS-Marine: Central API Router Assembler."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.ahp import router as ahp_router
from backend.app.api.auth import router as auth_router
from backend.app.api.cases import router as cases_router

api_router = APIRouter()

# Mount feature sub-routers
api_router.include_router(cases_router)
api_router.include_router(auth_router)
api_router.include_router(ahp_router)
