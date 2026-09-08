"""AEGIS-Marine: FastAPI Core Application Scaffolding, Middleware & RBAC Security (Architecture 10)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.schemas.vessel import AHPConfigResponse
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.errors import assert_no_banned_terms, register_exception_handlers
from backend.core.security import (
    CurrentUser,
    Role,
    get_current_user,
    require_roles,
)
from backend.services.tier4_correlation.ahp_manager import AHPWeightManager

logger = logging.getLogger("aegis.api")


def create_app() -> FastAPI:
    """Factory creating and configuring the primary FastAPI application instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "Automated Spaceborne Oil Spill Detection, Hydrodynamic Hindcasting "
            "& AIS Vessel Attribution Platform (AEGIS-Marine API Gateway)"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Type", "Content-Disposition", "WWW-Authenticate"],
    )

    # 2. Register RFC 7807 Global Problem Details Exception Handlers
    register_exception_handlers(app)

    # 3. Base Operational Endpoints
    @app.get(
        "/",
        tags=["System"],
        summary="API Gateway Root",
    )
    async def root() -> dict[str, Any]:
        return {
            "service": "AEGIS-Marine API Gateway",
            "version": settings.VERSION,
            "status": "online",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get(
        "/health",
        tags=["System"],
        summary="Liveness Health Check",
    )
    async def health_check() -> dict[str, Any]:
        """Liveness check indicating the web service process is active."""
        return {
            "status": "healthy",
            "service": "aegis-marine-api",
            "version": settings.VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get(
        "/ready",
        tags=["System"],
        summary="Readiness Dependency Check",
    )
    async def readiness_check(db: Session = Depends(get_db)) -> dict[str, Any]:
        """Readiness probe checking database and core connectivity."""
        db_status = "connected"
        try:
            db.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning("Database connectivity check failed: %s", e)
            db_status = "unavailable"

        return {
            "status": "ready" if db_status == "connected" else "degraded",
            "database": db_status,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get(
        "/ahp-config",
        response_model=AHPConfigResponse,
        tags=["Attribution & MCDA"],
        summary="Transparent AHP Pairwise Matrix & Weights (Rule 7)",
    )
    async def get_ahp_config(db: Session = Depends(get_db)) -> AHPConfigResponse:
        """Constitutional Rule 7 ('Show your math'): Returns active AHP comparison matrix, weights, and CR < 0.10."""
        manager = AHPWeightManager()
        return manager.get_active_config(db_session=db)

    # 4. API v1 Router with RBAC Protected Endpoints
    api_v1_router = APIRouter(prefix=settings.API_V1_STR)

    # Protected Endpoints for RBAC Verification (Architecture Section 10)
    @api_v1_router.post(
        "/cases/test-create",
        tags=["RBAC Verification"],
        summary="Test Case Creation (Investigator, Admin)",
        status_code=status.HTTP_201_CREATED,
    )
    async def test_case_create(
        user: CurrentUser = Depends(require_roles([Role.INVESTIGATOR, Role.ADMIN])),
    ) -> dict[str, Any]:
        msg = "Case creation authorized."
        assert_no_banned_terms(msg)
        return {"message": msg, "user": user.user_id, "roles": user.roles}

    @api_v1_router.get(
        "/cases/test-view",
        tags=["RBAC Verification"],
        summary="Test Case Viewing (Investigator, Analyst, Legal Reviewer, Admin)",
    )
    async def test_case_view(
        user: CurrentUser = Depends(
            require_roles([Role.INVESTIGATOR, Role.ANALYST, Role.LEGAL_REVIEWER, Role.ADMIN])
        ),
    ) -> dict[str, Any]:
        msg = "Case viewing authorized."
        assert_no_banned_terms(msg)
        return {"message": msg, "user": user.user_id, "roles": user.roles}

    @api_v1_router.post(
        "/cases/test-whatif",
        tags=["RBAC Verification"],
        summary="Test What-If Simulation (Investigator, Analyst, Admin)",
    )
    async def test_case_whatif(
        user: CurrentUser = Depends(require_roles([Role.INVESTIGATOR, Role.ANALYST, Role.ADMIN])),
    ) -> dict[str, Any]:
        msg = "What-if simulation authorized."
        assert_no_banned_terms(msg)
        return {"message": msg, "user": user.user_id, "roles": user.roles}

    @api_v1_router.post(
        "/dossiers/test-export",
        tags=["RBAC Verification"],
        summary="Test Dossier Export (Investigator, Legal Reviewer, Admin)",
    )
    async def test_dossier_export(
        user: CurrentUser = Depends(
            require_roles([Role.INVESTIGATOR, Role.LEGAL_REVIEWER, Role.ADMIN])
        ),
    ) -> dict[str, Any]:
        msg = "Dossier export authorized."
        assert_no_banned_terms(msg)
        return {"message": msg, "user": user.user_id, "roles": user.roles}

    @api_v1_router.get(
        "/admin/test-audit",
        tags=["RBAC Verification"],
        summary="Test System Audit Log Access (Admin only)",
    )
    async def test_admin_audit(
        user: CurrentUser = Depends(require_roles([Role.ADMIN])),
    ) -> dict[str, Any]:
        msg = "Admin audit log access authorized."
        assert_no_banned_terms(msg)
        return {"message": msg, "user": user.user_id, "roles": user.roles}

    # Include comprehensive API router
    from backend.app.api.cases import router as cases_root_router
    from backend.app.api.router import api_router

    app.include_router(api_v1_router)
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # Also mount cases at root level per Architecture Section 7 table
    app.include_router(cases_root_router)
    return app


app = create_app()
