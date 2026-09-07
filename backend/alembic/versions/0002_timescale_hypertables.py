"""0002_timescale_hypertables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07 14:26:00.000000

Sets up TimescaleDB hypertables for time-series particle advection
and vessel AIS kinematic reports per Architecture Section 6.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ais_tracks table
    op.create_table(
        "ais_tracks",
        sa.Column("mmsi", sa.BigInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point", Geometry("POINT", srid=4326), nullable=False),
        sa.Column("sog", sa.Float(), nullable=True),
        sa.Column("cog", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("nav_status", sa.Integer(), nullable=True),
        sa.Column(
            "data_source",
            postgresql.ENUM(name="data_source_enum", create_type=False),
            nullable=False,
            server_default="synthetic",
        ),
        sa.PrimaryKeyConstraint("mmsi", "timestamp", name="pk_ais_tracks"),
    )
    op.create_index("idx_ais_tracks_point", "ais_tracks", ["point"], postgresql_using="gist")
    op.create_index("idx_ais_tracks_mmsi_timestamp", "ais_tracks", ["mmsi", sa.text("timestamp DESC")])

    # Convert ais_tracks to TimescaleDB hypertable partitioned by timestamp (1-day chunk)
    op.execute(
        "SELECT create_hypertable('ais_tracks', 'timestamp', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )

    # 2. Create particle_trajectories table
    op.create_table(
        "particle_trajectories",
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("particle_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point", Geometry("POINT", srid=4326), nullable=False),
        sa.Column("depth_m", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mass_fraction", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("case_id", "particle_id", "timestamp", name="pk_particle_trajectories"),
    )
    op.create_index(
        "idx_particle_trajectories_point",
        "particle_trajectories",
        ["point"],
        postgresql_using="gist",
    )
    op.create_index(
        "idx_particle_trajectories_case_timestamp",
        "particle_trajectories",
        ["case_id", "timestamp"],
    )

    # Convert particle_trajectories to TimescaleDB hypertable partitioned by timestamp (12-hour chunk)
    op.execute(
        "SELECT create_hypertable('particle_trajectories', 'timestamp', chunk_time_interval => INTERVAL '12 hours', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("particle_trajectories")
    op.drop_table("ais_tracks")
