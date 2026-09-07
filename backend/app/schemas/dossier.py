"""AEGIS-Marine: Legal Dossier Generation Schemas (FR-20, C13)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from backend.app.schemas.common import BaseSchema


class DossierGenerateRequest(BaseSchema):
    """Payload to trigger legal dossier generation."""

    case_id: uuid.UUID
    include_sar_chip: bool = Field(
        default=True, description="Whether to include SAR chip in report"
    )
    model_versions: dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit model or pipeline version strings for forensic audit",
    )
    generated_by: str = Field(
        default="AEGIS Automated Forensic Pipeline",
        description="Entity or investigator generating the dossier",
    )


class DossierResult(BaseSchema):
    """Result of PDF legal dossier compilation and cryptographic hashing."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    case_id: uuid.UUID
    pdf_ref: str = Field(..., description="URI or path reference to generated PDF asset")
    sha256_hash: str = Field(
        ..., min_length=64, max_length=64, description="Deterministic 64-character SHA-256 digest"
    )
    generated_by: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_versions: dict[str, Any] = Field(default_factory=dict)
    file_size_bytes: int = Field(..., ge=0)
    verification_qr_b64: str | None = Field(
        default=None, description="Base64 data URI PNG containing chain-of-custody QR code"
    )
    pdf_bytes: bytes | None = Field(default=None, description="Raw binary PDF bytes")


class DossierResponse(BaseSchema):
    """API response contract for persisted Dossier database entity."""

    id: uuid.UUID
    case_id: uuid.UUID
    pdf_ref: str
    sha256_hash: str
    generated_by: str
    generated_at: datetime
    model_versions: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
