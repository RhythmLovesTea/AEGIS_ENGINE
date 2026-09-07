"""0001_initial_schema

Revision ID: 0001
Revises: None
Create Date: 2026-09-07 14:20:00.000000

Initial relational and spatial schema for AEGIS-Marine platform.
Enforces rules.md:
- Rule 1: Paired confidence/uncertainty on all estimates/scores.
- Rule 2: Stored sub-scores on VesselCandidate.
- Rule 4: AIS coverage flags including dark_gap and non_ais_unknown.
- Rule 5: Alternative explanations evaluated for every case.
- Rule 7: AHP configuration and consistency ratio.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure PostGIS and TimescaleDB extensions exist
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    # 2. Create PostgreSQL Enum Types
    case_status_enum = postgresql.ENUM(
        "detecting",
        "characterizing",
        "hindcasting",
        "correlating",
        "scoring",
        "ready",
        "failed",
        name="case_status_enum",
        create_type=False,
    )
    case_status_enum.create(op.get_bind(), checkfirst=True)

    data_source_enum = postgresql.ENUM(
        "live",
        "cached",
        "synthetic",
        name="data_source_enum",
        create_type=False,
    )
    data_source_enum.create(op.get_bind(), checkfirst=True)

    ais_coverage_enum = postgresql.ENUM(
        "full",
        "partial",
        "dark_gap",
        "non_ais_unknown",
        name="ais_coverage_enum",
        create_type=False,
    )
    ais_coverage_enum.create(op.get_bind(), checkfirst=True)

    # 3. Create cases table
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", case_status_enum, nullable=False, server_default="detecting"),
        sa.Column("region", Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("source_scene_ref", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="investigator"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_cases_status", "cases", ["status"])
    op.create_index("idx_cases_region", "cases", ["region"], postgresql_using="gist")

    # 4. Create slick_detections table (Tier 1)
    op.create_table(
        "slick_detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("polygon", Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("centroid", Geometry("POINT", srid=4326), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("lookalike_risk", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sensor", sa.String(64), nullable=False),
        sa.Column("detection_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", data_source_enum, nullable=False, server_default="synthetic"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_slick_detections_case_id", "slick_detections", ["case_id"])
    op.create_index("idx_slick_detections_polygon", "slick_detections", ["polygon"], postgresql_using="gist")
    op.create_index("idx_slick_detections_centroid", "slick_detections", ["centroid"], postgresql_using="gist")

    # 5. Create slick_characterizations table (Tier 2)
    op.create_table(
        "slick_characterizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("perimeter_m", sa.Float(), nullable=False),
        sa.Column("principal_axis_deg", sa.Float(), nullable=False),
        sa.Column("baoac_code", sa.Integer(), nullable=False),
        sa.Column("estimated_volume_m3", sa.Float(), nullable=False),
        sa.Column("t_age_hours", sa.Float(), nullable=False),
        sa.Column("age_confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_slick_characterizations_case_id", "slick_characterizations", ["case_id"])

    # 6. Create origin_estimates table (Tier 3A)
    op.create_table(
        "origin_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("centroid", Geometry("POINT", srid=4326), nullable=False),
        sa.Column("covariance_matrix", postgresql.JSONB(), nullable=False),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence_pct", sa.Float(), nullable=False),
        sa.Column("region_area_km2", sa.Float(), nullable=False),
        sa.Column("particle_trajectory_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_origin_estimates_case_id", "origin_estimates", ["case_id"])
    op.create_index("idx_origin_estimates_centroid", "origin_estimates", ["centroid"], postgresql_using="gist")

    # 7. Create forward_forecasts table (Tier 3B)
    op.create_table(
        "forward_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("etb_hours", sa.Float(), nullable=True),
        sa.Column("cvi_index", sa.Float(), nullable=True),
        sa.Column("beached_volume_m3", sa.Float(), nullable=True),
        sa.Column("shoreline_impact_polygon", Geometry("POLYGON", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_forward_forecasts_case_id", "forward_forecasts", ["case_id"])
    op.create_index("idx_forward_forecasts_polygon", "forward_forecasts", ["shoreline_impact_polygon"], postgresql_using="gist")

    # 8. Create vessel_candidates table (Tier 4)
    op.create_table(
        "vessel_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mmsi", sa.BigInteger(), nullable=False),
        sa.Column("imo", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("flag_state", sa.String(64), nullable=True),
        sa.Column("vessel_type", sa.String(64), nullable=False),
        sa.Column("s_culprit", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sub_scores", postgresql.JSONB(), nullable=False),
        sa.Column("anomaly_flags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ais_coverage", ais_coverage_enum, nullable=False, server_default="full"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_vessel_candidates_case_id", "vessel_candidates", ["case_id"])
    op.create_index("idx_vessel_candidates_mmsi", "vessel_candidates", ["mmsi"])
    op.create_index("idx_vessel_candidates_s_culprit", "vessel_candidates", ["s_culprit"])

    # 9. Create alternative_explanations table (Explainability, Rule 5)
    op.create_table(
        "alternative_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hypothesis", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_alternative_explanations_case_id", "alternative_explanations", ["case_id"])

    # 10. Create ahp_configs table (Rule 7)
    op.create_table(
        "ahp_configs",
        sa.Column("version", sa.String(32), primary_key=True),
        sa.Column("pairwise_matrix", postgresql.JSONB(), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column("consistency_ratio", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 11. Create dossiers table
    op.create_table(
        "dossiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pdf_ref", sa.String(512), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("generated_by", sa.String(255), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model_versions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_dossiers_case_id", "dossiers", ["case_id"])

    # 12. Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_logs_case_id", "audit_logs", ["case_id"])
    op.create_index("idx_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("dossiers")
    op.drop_table("ahp_configs")
    op.drop_table("alternative_explanations")
    op.drop_table("vessel_candidates")
    op.drop_table("forward_forecasts")
    op.drop_table("origin_estimates")
    op.drop_table("slick_characterizations")
    op.drop_table("slick_detections")
    op.drop_table("cases")

    op.execute("DROP TYPE IF EXISTS ais_coverage_enum;")
    op.execute("DROP TYPE IF EXISTS data_source_enum;")
    op.execute("DROP TYPE IF EXISTS case_status_enum;")
