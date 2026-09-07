"""AEGIS-Marine: Core Relational and Spatial SQLAlchemy Models.

Conforms to AEGIS-Marine_Architecture.md Section 6 and rules.md:
- Rule 1: Paired confidence/uncertainty on all estimates/scores.
- Rule 2: Persisted sub-scores in JSONB on VesselCandidate.
- Rule 4: AIS transponder gap flag 'dark_gap' and 'non_ais_unknown'.
- Rule 5: AlternativeExplanation entity required for case completion.
- Rule 7: AHPConfig storing pairwise matrix and consistency ratio.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CaseStatus(str, enum.Enum):
    DETECTING = "detecting"
    CHARACTERIZING = "characterizing"
    HINDCASTING = "hindcasting"
    CORRELATING = "correlating"
    SCORING = "scoring"
    READY = "ready"
    FAILED = "failed"


class DataSource(str, enum.Enum):
    LIVE = "live"
    CACHED = "cached"
    SYNTHETIC = "synthetic"


class AISCoverage(str, enum.Enum):
    FULL = "full"
    PARTIAL = "partial"
    DARK_GAP = "dark_gap"
    NON_AIS_UNKNOWN = "non_ais_unknown"


class Case(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Root aggregate entity for an oil spill investigation."""

    __tablename__ = "cases"

    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status_enum", create_type=False),
        default=CaseStatus.DETECTING,
        nullable=False,
        index=True,
    )
    region = mapped_column(Geometry("POLYGON", srid=4326), nullable=False)
    source_scene_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), default="investigator", nullable=False)

    # Relationships
    detections: Mapped[List[SlickDetection]] = relationship(
        "SlickDetection", back_populates="case", cascade="all, delete-orphan"
    )
    characterizations: Mapped[List[SlickCharacterization]] = relationship(
        "SlickCharacterization", back_populates="case", cascade="all, delete-orphan"
    )
    origin_estimates: Mapped[List[OriginEstimate]] = relationship(
        "OriginEstimate", back_populates="case", cascade="all, delete-orphan"
    )
    forward_forecasts: Mapped[List[ForwardForecast]] = relationship(
        "ForwardForecast", back_populates="case", cascade="all, delete-orphan"
    )
    vessel_candidates: Mapped[List[VesselCandidate]] = relationship(
        "VesselCandidate", back_populates="case", cascade="all, delete-orphan"
    )
    alternative_explanations: Mapped[List[AlternativeExplanation]] = relationship(
        "AlternativeExplanation", back_populates="case", cascade="all, delete-orphan"
    )
    dossiers: Mapped[List[Dossier]] = relationship(
        "Dossier", back_populates="case", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List[AuditLog]] = relationship(
        "AuditLog", back_populates="case", cascade="all, delete-orphan"
    )


class SlickDetection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tier 1: Multi-modal Earth observation segmentation detection."""

    __tablename__ = "slick_detections"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    polygon = mapped_column(Geometry("POLYGON", srid=4326), nullable=False)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Rule 1
    lookalike_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sensor: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., "Sentinel-1 SAR IW"
    detection_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_source: Mapped[DataSource] = mapped_column(
        Enum(DataSource, name="data_source_enum", create_type=False),
        default=DataSource.SYNTHETIC,
        nullable=False,
    )

    case: Mapped[Case] = relationship("Case", back_populates="detections")


class SlickCharacterization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tier 2: Morphometry, thickness, and Fay spreading age inversion."""

    __tablename__ = "slick_characterizations"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    perimeter_m: Mapped[float] = mapped_column(Float, nullable=False)
    principal_axis_deg: Mapped[float] = mapped_column(Float, nullable=False)  # [0, 360)
    baoac_code: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5
    estimated_volume_m3: Mapped[float] = mapped_column(Float, nullable=False)
    t_age_hours: Mapped[float] = mapped_column(Float, nullable=False)
    age_confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Rule 1

    case: Mapped[Case] = relationship("Case", back_populates="characterizations")


class OriginEstimate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tier 3A: Backward Lagrangian hydrodynamic origin density estimate."""

    __tablename__ = "origin_estimates"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    covariance_matrix: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    time_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence_pct: Mapped[float] = mapped_column(Float, nullable=False)  # Rule 1
    region_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    particle_trajectory_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    case: Mapped[Case] = relationship("Case", back_populates="origin_estimates")


class ForwardForecast(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tier 3B: Forward 72h trajectory forecast with Mackay weathering."""

    __tablename__ = "forward_forecasts"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    etb_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Estimated Time of Beaching
    cvi_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Coastal Vulnerability Index
    beached_volume_m3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shoreline_impact_polygon = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)

    case: Mapped[Case] = relationship("Case", back_populates="forward_forecasts")


class VesselCandidate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tier 4: AIS correlated vessel candidate with AHP attribution scores."""

    __tablename__ = "vessel_candidates"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mmsi: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    imo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    flag_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vessel_type: Mapped[str] = mapped_column(String(64), nullable=False)
    s_culprit: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Rule 1

    # Rule 2: Persisted sub-scores, never calculated client-side
    sub_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )  # {spatial, temporal, kinematic, anomaly, type}
    anomaly_flags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    # Rule 4: Surfacing dark ships and non-AIS targets
    ais_coverage: Mapped[AISCoverage] = mapped_column(
        Enum(AISCoverage, name="ais_coverage_enum", create_type=False),
        default=AISCoverage.FULL,
        nullable=False,
    )

    case: Mapped[Case] = relationship("Case", back_populates="vessel_candidates")


class AlternativeExplanation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Forensic explainability: Non-vessel hypotheses (Rule 5)."""

    __tablename__ = "alternative_explanations"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hypothesis: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # "natural_seep", "imaging_artifact", "non_ais_vessel"
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Rule 1
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    case: Mapped[Case] = relationship("Case", back_populates="alternative_explanations")


class AHPConfig(Base):
    """Analytic Hierarchy Process configuration and weights (Rule 7)."""

    __tablename__ = "ahp_configs"

    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    pairwise_matrix: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    weights: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    consistency_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Dossier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Generated legal evidence report with cryptographic chain-of-custody."""

    __tablename__ = "dossiers"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pdf_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    case: Mapped[Case] = relationship("Case", back_populates="dossiers")


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail for all forensic actions and modifications."""

    __tablename__ = "audit_logs"

    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    case: Mapped[Optional[Case]] = relationship("Case", back_populates="audit_logs")
