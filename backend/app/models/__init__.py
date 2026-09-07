"""AEGIS-Marine: Database Models Module."""

from backend.app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.app.models.entities import (
    AHPConfig,
    AISCoverage,
    AISTrack,
    AlternativeExplanation,
    AuditLog,
    Case,
    CaseStatus,
    DataSource,
    Dossier,
    ForwardForecast,
    OriginEstimate,
    ParticleTrajectory,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "Case",
    "CaseStatus",
    "DataSource",
    "AISCoverage",
    "SlickDetection",
    "SlickCharacterization",
    "OriginEstimate",
    "ForwardForecast",
    "VesselCandidate",
    "AlternativeExplanation",
    "AHPConfig",
    "Dossier",
    "AuditLog",
    "AISTrack",
    "ParticleTrajectory",
]
