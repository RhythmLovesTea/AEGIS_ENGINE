"""AEGIS-Marine: Multi-Criteria Attribution Scoring Engine (S_culprit).

Implements Tier 4 Multi-Criteria Attribution Scoring per PRD Section 11
(FR-14, FR-16, C11, D1) and Architecture Section 4.4, strictly enforcing:
- Rule 1: Mandatory confidence score in [0.0, 100.0]
- Rule 2: Persisted 5-component sub-scores (spatial, temporal, kinematic, anomaly, type)
- Rule 3: Never rank by distance alone (multi-criteria synthesis)
- Rule 4: Explicit ais_coverage flags ('full' | 'partial' | 'dark_gap' | 'non_ais_unknown')
- Rule 6: Strictly zero occurrences of banned terms
- Rule 7: AHP-derived weights [0.30, 0.25, 0.15, 0.20, 0.10]
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.app.schemas.common import AISCoverageEnum
from backend.app.schemas.vessel import SubScores
from backend.services.tier4_correlation.ahp_manager import CANONICAL_WEIGHTS
from backend.services.tier4_correlation.anomaly_detector import AnomalyAssessment
from backend.services.tier4_correlation.trajectory_reconstruction import (
    ReconstructedTrajectory,
)

logger = logging.getLogger("aegis.scoring_engine")

# Temporal coincidence exponential decay time constant (hours)
DEFAULT_TEMPORAL_TAU_HOURS: float = 1.5

# Categorical vessel type risk priors [0.0 - 100.0]
VESSEL_TYPE_PRIORS: dict[str, float] = {
    "tanker": 100.0,
    "oil tanker": 100.0,
    "crude oil tanker": 100.0,
    "chemical tanker": 95.0,
    "cargo": 75.0,
    "general cargo": 75.0,
    "container ship": 75.0,
    "bulk carrier": 75.0,
    "offshore": 50.0,
    "offshore supply": 50.0,
    "tug": 40.0,
    "towing": 40.0,
    "fishing": 30.0,
    "passenger": 15.0,
    "pleasure craft": 5.0,
    "sailing vessel": 5.0,
    "unknown": 20.0,
    "non_ais_contact": 80.0,
}


def get_vessel_type_prior(vessel_type: str | None) -> float:
    """Maps vessel type category to prior spill likelihood score in [0.0, 100.0]."""
    if not vessel_type:
        return VESSEL_TYPE_PRIORS["unknown"]

    v_lower = vessel_type.lower().strip()
    for key, score in VESSEL_TYPE_PRIORS.items():
        if key in v_lower or v_lower in key:
            return score

    return VESSEL_TYPE_PRIORS["unknown"]


def compute_mahalanobis_spatial_score(
    vessel_cpa_coords: tuple[float, float],
    origin_centroid: tuple[float, float],
    covariance_matrix: dict[str, float] | None = None,
) -> tuple[float, float]:
    """Computes Mahalanobis distance D_M and spatial proximity sub-score S_spatial.

    Formula (PRD Section 11, TODO.md TASK-027):
      D_M = sqrt((x_CPA - mu_p)^T * Sigma_p^-1 * (x_CPA - mu_p))
      S_spatial = 100.0 * exp(-0.5 * D_M^2)

    Args:
        vessel_cpa_coords: (lon, lat) of vessel closest point of approach.
        origin_centroid: (lon, lat) centroid mu_p of estimated spill origin.
        covariance_matrix: Dict with 'var_lon', 'var_lat', 'cov_lon_lat'.

    Returns:
        Tuple of (S_spatial in [0.0, 100.0], Mahalanobis distance D_M).
    """
    d_lon = vessel_cpa_coords[0] - origin_centroid[0]
    d_lat = vessel_cpa_coords[1] - origin_centroid[1]

    if covariance_matrix:
        var_lon = float(covariance_matrix.get("var_lon", 0.000185))
        var_lat = float(covariance_matrix.get("var_lat", 0.000142))
        cov_lon_lat = float(covariance_matrix.get("cov_lon_lat", 9.5e-05))
    else:
        var_lon = 0.000185
        var_lat = 0.000142
        cov_lon_lat = 9.5e-05

    det = var_lon * var_lat - (cov_lon_lat**2)

    if det > 1e-12:
        # Inverse of 2x2 covariance matrix
        inv_00 = var_lat / det
        inv_01 = -cov_lon_lat / det
        inv_10 = -cov_lon_lat / det
        inv_11 = var_lon / det

        dm_sq = (
            (d_lon**2) * inv_00
            + d_lon * d_lat * inv_01
            + d_lat * d_lon * inv_10
            + (d_lat**2) * inv_11
        )
        dm_sq = max(0.0, float(dm_sq))
        d_m = math.sqrt(dm_sq)
    else:
        # Fallback to Euclidean metric distance scaled by 5 km standard deviation
        deg_dist = math.hypot(d_lon, d_lat)
        d_m = deg_dist / 0.05  # ~5.5 km

    s_spatial = 100.0 * math.exp(-0.5 * (d_m**2))
    return round(s_spatial, 2), round(d_m, 3)


def compute_temporal_coincidence_score(
    t_cpa: datetime,
    t_release: datetime,
    tau_hours: float = DEFAULT_TEMPORAL_TAU_HOURS,
) -> tuple[float, float]:
    """Computes temporal coincidence score S_temporal via exponential decay.

    Formula (PRD Section 11, TODO.md TASK-027):
      delta_t = |t_CPA - t_release| (hours)
      S_temporal = 100.0 * exp(-delta_t / tau)

    Args:
        t_cpa: Timestamp of vessel closest approach to origin.
        t_release: Estimated spill release timestamp.
        tau_hours: Exponential decay time constant in hours (default 1.5h).

    Returns:
        Tuple of (S_temporal in [0.0, 100.0], delta_t_hours).
    """
    delta_sec = abs((t_cpa - t_release).total_seconds())
    delta_hours = delta_sec / 3600.0
    tau = max(0.1, tau_hours)

    s_temporal = 100.0 * math.exp(-delta_hours / tau)
    return round(s_spatial_temporal_bounded(s_temporal), 2), round(delta_hours, 3)


def compute_kinematic_alignment_score(
    vessel_heading_deg: float,
    slick_orientation_deg: float,
    sog_kts: float,
) -> tuple[float, float]:
    """Computes kinematic heading alignment with slick principal orientation.

    Formula (PRD Section 11, TODO.md TASK-027):
      S_kinematic = 100.0 * |cos(theta_vessel - theta_slick)| * f(v)
      where f(v) = min(1.0, max(0.2, v / 3.0)) modulates wake formation.

    Args:
        vessel_heading_deg: Vessel heading or course over ground at CPA (degrees).
        slick_orientation_deg: Slick major principal axis orientation (degrees).
        sog_kts: Vessel speed over ground (knots).

    Returns:
        Tuple of (S_kinematic in [0.0, 100.0], delta_heading_deg).
    """
    diff_deg = abs((vessel_heading_deg - slick_orientation_deg + 180.0) % 360.0 - 180.0)
    rad = math.radians(diff_deg)
    cos_val = abs(math.cos(rad))

    # Speed modulation factor: slow/stationary vessels do not create directional wakes
    v = max(0.0, float(sog_kts))
    f_v = min(1.0, max(0.2, v / 3.0))

    s_kinematic = 100.0 * cos_val * f_v
    return round(s_spatial_temporal_bounded(s_kinematic), 2), round(diff_deg, 1)


def compute_anomaly_subscore(
    a_speed: float,
    a_course: float,
    a_dark: float,
) -> float:
    """Computes the behavioral anomaly sub-score S_anomaly in [0.0, 100.0].

    Formula (TODO.md TASK-027):
      S_anomaly = 100.0 * (0.4 * A_speed + 0.3 * A_course + 0.3 * A_dark)

    Args:
        a_speed: Speed drop anomaly in [0.0, 1.0].
        a_course: Course deviation anomaly in [0.0, 1.0].
        a_dark: Transponder dark gap indicator in [0.0, 1.0].

    Returns:
        S_anomaly bounded in [0.0, 100.0].
    """
    score = 100.0 * (0.40 * a_speed + 0.30 * a_course + 0.30 * a_dark)
    return round(s_spatial_temporal_bounded(score), 2)


def s_spatial_temporal_bounded(val: float) -> float:
    """Clips score to valid range [0.0, 100.0]."""
    return max(0.0, min(100.0, float(val)))


@dataclass
class ScoredCandidateVessel:
    """Fully scored, ranked vessel candidate adhering to Product Rules 1, 2, 4, 6."""

    mmsi: int
    imo: int | None
    name: str
    flag_state: str | None
    vessel_type: str
    s_culprit: float  # [0.0, 100.0] Composite AHP-weighted attribution score
    confidence: float  # Rule 1: [0.0, 100.0]
    sub_scores: SubScores  # Rule 2: Persisted discrete 5-component scores
    evidence_refs: list[str]  # Human-readable forensic evidence references
    anomaly_flags: list[str]  # e.g., ['speed_drop_dumping', 'dark_transponder_gap']
    ais_coverage: AISCoverageEnum  # Rule 4: 'full' | 'partial' | 'dark_gap' | 'non_ais_unknown'
    cpa_distance_m: float
    cpa_time: datetime
    rank: int = 1
    ahp_version: str = "v1.0"

    def to_dict(self) -> dict[str, Any]:
        """Serializes candidate into API / database dict representation."""
        return {
            "mmsi": self.mmsi,
            "imo": self.imo,
            "name": self.name,
            "flag_state": self.flag_state,
            "vessel_type": self.vessel_type,
            "s_culprit": self.s_culprit,
            "confidence": self.confidence,
            "sub_scores": self.sub_scores.model_dump(),
            "evidence_refs": self.evidence_refs,
            "anomaly_flags": self.anomaly_flags,
            "ais_coverage": self.ais_coverage.value,
            "cpa_distance_m": round(self.cpa_distance_m, 1),
            "cpa_time": self.cpa_time.isoformat(),
            "rank": self.rank,
            "ahp_version": self.ahp_version,
        }


class ScoringEngine:
    """Multi-criteria vessel attribution scoring engine (Tier 4).

    Synthesizes spatial, temporal, kinematic, anomaly, and type signals using
    AHP-derived weights into a ranked list of candidate suspects.
    """

    def __init__(
        self,
        tau_hours: float = DEFAULT_TEMPORAL_TAU_HOURS,
        weights: dict[str, float] | None = None,
        ahp_version: str = "v1.0",
    ) -> None:
        self.tau_hours = tau_hours
        self.weights = weights or dict(CANONICAL_WEIGHTS)
        self.ahp_version = ahp_version

    def score_candidate(
        self,
        trajectory: ReconstructedTrajectory,
        anomaly: AnomalyAssessment,
        origin_centroid: tuple[float, float],
        t_release: datetime,
        slick_orientation_deg: float,
        origin_covariance: dict[str, float] | None = None,
    ) -> ScoredCandidateVessel:
        """Computes all 5 sub-scores, compiles evidence, and evaluates S_culprit for one vessel.

        Args:
            trajectory: Continuous reconstructed vessel trajectory.
            anomaly: Behavioral anomaly assessment.
            origin_centroid: (lon, lat) of estimated spill origin.
            t_release: Estimated release timestamp from spill age inversion.
            slick_orientation_deg: Principal axis angle of observed slick.
            origin_covariance: Covariance matrix dict of origin estimate.

        Returns:
            ScoredCandidateVessel with sub-scores, S_culprit, and evidence references.
        """
        # 1. Spatial Sub-Score (S_spatial)
        # For dark gap ships whose gap spans origin, consider extrapolated DR CPA if closer
        cpa_coords = (trajectory.cpa.lon, trajectory.cpa.lat)
        cpa_dist_m = trajectory.cpa.distance_m
        cpa_time = trajectory.cpa.timestamp

        if anomaly.dark_gaps and anomaly.dark_gaps[0].crosses_origin_region:
            gap_info = anomaly.dark_gaps[0]
            if (
                gap_info.extrapolated_cpa_distance_m is not None
                and gap_info.extrapolated_cpa_distance_m < cpa_dist_m
            ):
                cpa_dist_m = gap_info.extrapolated_cpa_distance_m
                if gap_info.extrapolated_cpa_time:
                    cpa_time = gap_info.extrapolated_cpa_time

        s_spatial, d_m = compute_mahalanobis_spatial_score(
            vessel_cpa_coords=cpa_coords,
            origin_centroid=origin_centroid,
            covariance_matrix=origin_covariance,
        )

        # 2. Temporal Sub-Score (S_temporal)
        s_temporal, delta_hours = compute_temporal_coincidence_score(
            t_cpa=cpa_time,
            t_release=t_release,
            tau_hours=self.tau_hours,
        )

        # 3. Kinematic Alignment Sub-Score (S_kinematic)
        s_kinematic, delta_heading = compute_kinematic_alignment_score(
            vessel_heading_deg=trajectory.cpa.cog_deg,
            slick_orientation_deg=slick_orientation_deg,
            sog_kts=trajectory.cpa.sog_kts,
        )

        # 4. Behavioral Anomaly Sub-Score (S_anomaly)
        s_anomaly = compute_anomaly_subscore(
            a_speed=anomaly.a_speed,
            a_course=anomaly.a_course,
            a_dark=anomaly.a_dark,
        )

        # 5. Vessel Type Prior Sub-Score (S_type)
        s_type = get_vessel_type_prior(trajectory.vessel_type)

        # Rule 2: SubScores discrete container
        sub_scores = SubScores(
            spatial=s_spatial,
            temporal=s_temporal,
            kinematic=s_kinematic,
            anomaly=s_anomaly,
            type=s_type,
        )

        # Composite AHP Score: S_culprit = sum(w_i * S_i)
        w_sp = self.weights.get("spatial", 0.30)
        w_te = self.weights.get("temporal", 0.25)
        w_ki = self.weights.get("kinematic", 0.15)
        w_an = self.weights.get("anomaly", 0.20)
        w_ty = self.weights.get("type", 0.10)

        raw_culprit = (
            w_sp * s_spatial
            + w_te * s_temporal
            + w_ki * s_kinematic
            + w_an * s_anomaly
            + w_ty * s_type
        )
        s_culprit = round(s_spatial_temporal_bounded(raw_culprit), 2)

        # Compile structured forensic evidence references (Feature D1 / Rule 2)
        evidence_refs: list[str] = [
            f"Spatial CPA: d_CPA = {cpa_dist_m / 1000.0:.2f} km (Mahalanobis D_M = {d_m:.2f}, score: {s_spatial:.1f}/100)",
            f"Temporal Offset: |t_CPA - t_release| = {delta_hours:.2f}h (decay score: {s_temporal:.1f}/100, tau = {self.tau_hours:.1f}h)",
            f"Kinematic Heading: COG {trajectory.cpa.cog_deg:.1f} deg vs Slick Axis {slick_orientation_deg:.1f} deg (delta = {delta_heading:.1f} deg, speed = {trajectory.cpa.sog_kts:.1f} kts, score: {s_kinematic:.1f}/100)",
            f"Behavioral Anomaly: speed drop {anomaly.a_speed:.2f}, turn {anomaly.a_course:.2f}, dark gap {anomaly.a_dark:.2f} (score: {s_anomaly:.1f}/100)",
            f"Registry Prior: vessel type '{trajectory.vessel_type}' (prior risk score: {s_type:.1f}/100)",
        ]

        if "speed_drop_dumping" in anomaly.anomaly_flags:
            evidence_refs.append(
                f"Discharge Band: Vessel slowed to {anomaly.speed_at_cpa_kts or trajectory.cpa.sog_kts:.1f} kts in [4, 8] kt dumping window"
            )

        if "dark_transponder_gap" in anomaly.anomaly_flags and anomaly.dark_gaps:
            gap = anomaly.dark_gaps[0]
            evidence_refs.append(
                f"Transponder Gap: {gap.duration_hours:.1f}h silence window across estimated spill origin"
            )

        # Map AISCoverage string to AISCoverageEnum (Rule 4)
        cov_mapping = {
            "full": AISCoverageEnum.FULL,
            "partial": AISCoverageEnum.PARTIAL,
            "dark_gap": AISCoverageEnum.DARK_GAP,
            "non_ais_unknown": AISCoverageEnum.NON_AIS_UNKNOWN,
        }
        coverage_enum = cov_mapping.get(anomaly.ais_coverage, AISCoverageEnum.FULL)

        # Calibrated attribution confidence (Rule 1)
        confidence = min(
            98.0,
            max(
                50.0,
                round(
                    trajectory.confidence_pct * 0.50
                    + anomaly.confidence_pct * 0.40
                    + (10.0 if s_culprit > 70.0 else 0.0),
                    1,
                ),
            ),
        )

        return ScoredCandidateVessel(
            mmsi=trajectory.mmsi,
            imo=trajectory.imo,
            name=trajectory.vessel_name,
            flag_state=None,
            vessel_type=trajectory.vessel_type,
            s_culprit=s_culprit,
            confidence=confidence,
            sub_scores=sub_scores,
            evidence_refs=evidence_refs,
            anomaly_flags=anomaly.anomaly_flags,
            ais_coverage=coverage_enum,
            cpa_distance_m=cpa_dist_m,
            cpa_time=cpa_time,
            ahp_version=self.ahp_version,
        )

    def rank_candidates(
        self,
        trajectories: dict[int, ReconstructedTrajectory],
        anomalies: dict[int, AnomalyAssessment],
        origin_centroid: tuple[float, float],
        t_release: datetime,
        slick_orientation_deg: float,
        origin_covariance: dict[str, float] | None = None,
    ) -> list[ScoredCandidateVessel]:
        """Scores all candidate vessels and returns a sorted ranked list in descending order of S_culprit.

        Rule 3 enforcement: Nearest vessel is not automatically top-ranked;
        multi-criteria synthesis determines ranking.
        """
        scored_vessels: list[ScoredCandidateVessel] = []

        for mmsi, traj in trajectories.items():
            anom = anomalies.get(mmsi)
            if not anom:
                logger.warning("Missing anomaly assessment for MMSI %d; skipping scoring.", mmsi)
                continue

            candidate = self.score_candidate(
                trajectory=traj,
                anomaly=anom,
                origin_centroid=origin_centroid,
                t_release=t_release,
                slick_orientation_deg=slick_orientation_deg,
                origin_covariance=origin_covariance,
            )
            scored_vessels.append(candidate)

        # Sort descending by composite score S_culprit
        scored_vessels.sort(key=lambda v: v.s_culprit, reverse=True)

        # Assign 1-based ranks
        for idx, vessel in enumerate(scored_vessels, start=1):
            vessel.rank = idx

        return scored_vessels


# Global singleton instance using canonical AHP weights
default_scoring_engine = ScoringEngine()
