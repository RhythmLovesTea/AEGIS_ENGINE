"""AEGIS-Marine: Pydantic Schemas for Audit Logging System (Architecture 10 & rules.md Section 5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from backend.app.schemas.common import BaseSchema


class AuditLogResponse(BaseSchema):
    """Audit log record representing an immutable forensic or system event."""

    id: uuid.UUID = Field(..., description="Unique audit entry identifier")
    case_id: uuid.UUID | None = Field(
        default=None, description="Associated investigation case UUID, if applicable"
    )
    user_id: str = Field(..., description="Authenticated user identity or subject claim")
    action: str = Field(
        ...,
        description="Forensic or system action descriptor (e.g., case.create, dossier.generate)",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Cryptographic hash digest, client IP, and contextual metadata",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the action execution",
    )


class AuditLogListResponse(BaseSchema):
    """Paginated collection of audit log entries for administrative oversight."""

    items: list[AuditLogResponse] = Field(
        default_factory=list, description="List of audit log records"
    )
    total: int = Field(..., ge=0, description="Total count of audit log records matching the query")
    limit: int = Field(default=50, ge=1, le=200, description="Pagination size limit")
    offset: int = Field(default=0, ge=0, description="Pagination offset index")
