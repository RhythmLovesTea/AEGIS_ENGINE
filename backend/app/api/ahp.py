"""AEGIS-Marine: AHP Configuration & Mathematical Transparency Endpoints (Rule 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.schemas.vessel import AHPConfigResponse
from backend.core.database import get_db
from backend.services.tier4_correlation.ahp_manager import AHPWeightManager

router = APIRouter(tags=["Attribution & MCDA"])


@router.get(
    "/ahp-config",
    response_model=AHPConfigResponse,
    summary="Active AHP Pairwise Comparison Matrix & Weights (Rule 7)",
    description=(
        "Constitutional Rule 7 ('Show your math'): Returns active AHP comparison matrix, "
        "normalized weights, and Saaty consistency ratio (CR < 0.10)."
    ),
)
async def get_ahp_configuration(
    db: Session = Depends(get_db),
) -> AHPConfigResponse:
    """Returns active AHP weights, pairwise matrix, and consistency ratio."""
    manager = AHPWeightManager()
    return manager.get_active_config(db_session=db)
