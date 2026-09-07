"""AEGIS-Marine: Vessel Kinematic Anomaly Detector & Transponder Dark Gap Flagger.

Implements Tier 4 behavioral anomaly detection per PRD Section 11 (FR-13, FR-19, C10),
Architecture Section 4.4, and Constitutional Rules (rules.md):
- A_speed: Speed drop into characteristic bilge/ballast dumping speed band (4-8 kts)
  Formula:
    A_speed = 1.0 if 4.0 <= v <= 8.0 kts else max(0.0, 1.0 - abs(v - 6.0) / 6.0)
- A_course: Course deviation / abnormal turns (> 45 deg deviation or zig-zag loitering)
- A_dark: AIS transponder gap detection (delta_t > 30 minutes) and dead-reckoning path extrapolation
- Non-AIS Target Integration (P4, FR-19): Flag radar/optical contacts with no AIS transponder
- Rule 1: Mandatory calibrated confidence_pct in [0.0, 100.0]
- Rule 4: Explicit ais_coverage ('full' | 'partial' | 'dark_gap' | 'non_ais_unknown') & data_source
- Rule 6: Strictly zero occurrences of banned terms
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from backend.services.data_adapters.ais_adapter import AISTrackRecord
from backend.services.tier4_correlation.trajectory_reconstruction import (
    InterpolatedTrackPoint,
    ReconstructedTrajectory,
)

logger = logging.getLogger("aegis.anomaly_detector")

# Characteristic bilge / ballast discharge speed thresholds (knots)
DISCHARGE_SPEED_MIN_KTS = 4.0
DISCHARGE_SPEED_MAX_KTS = 8.0
DISCHARGE_SPEED_CENTER_KTS = 6.0
DISCHARGE_SPEED_HALF_WIDTH_KTS = 6.0

# Transponder gap threshold (seconds) per FR-19 / Rule 4
DEFAULT_DARK_GAP_THRESHOLD_SECONDS = 1800.0  # 30 minutes

# Course deviation threshold (degrees)
DEFAULT_COURSE_TURN_THRESHOLD_DEG = 45.0


def compute_speed_drop_anomaly(speed_kts: float) -> float:
    """Computes the bilge/ballast dumping speed anomaly score A_speed in [0.0, 1.0].

    Formula (PRD Section 11, TODO.md TASK-025):
      A_speed = 1.0 if 4.0 <= v <= 8.0 kts
                else max(0.0, 1.0 - abs(v - 6.0) / 6.0)

    Args:
        speed_kts: Vessel speed over ground in knots.

    Returns:
        A_speed value bounded in [0.0, 1.0].
    """
    v = max(0.0, float(speed_kts))
    if DISCHARGE_SPEED_MIN_KTS <= v <= DISCHARGE_SPEED_MAX_KTS:
        return 1.0
    return max(0.0, 1.0 - abs(v - DISCHARGE_SPEED_CENTER_KTS) / DISCHARGE_SPEED_HALF_WIDTH_KTS)


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Computes great-circle distance between two points in meters using Haversine formula."""
    r_earth = 6371000.0  # Mean Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


def angular_difference_deg(deg1: float, deg2: float) -> float:
    """Computes the minimal unsigned angular difference between two compass bearings in [0, 180]."""
    diff = (deg1 - deg2 + 180.0) % 360.0 - 180.0
    return abs(diff)


@dataclass
class DarkGapInfo:
    """Details of a detected AIS transponder coverage gap (delta_t > 30 min)."""

    gap_index: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    duration_hours: float
    start_point: tuple[float, float]  # (lon, lat)
    end_point: tuple[float, float]  # (lon, lat)
    extrapolated_cpa_distance_m: float | None = None  # Min distance from DR path to origin
    extrapolated_cpa_time: datetime | None = None  # Estimated time of DR CPA
    crosses_origin_region: bool = False  # True if DR path passes near origin mu_p


@dataclass
class AnomalyAssessment:
    """Complete behavioral anomaly assessment for a candidate vessel or contact."""

    mmsi: int
    vessel_name: str
    vessel_type: str
    a_speed: float  # [0.0, 1.0]
    a_course: float  # [0.0, 1.0]
    a_dark: float  # [0.0, 1.0]
    s_anomaly: float  # [0.0, 100.0] Composite AHP sub-score
    anomaly_flags: list[str]  # e.g., ["speed_drop_dumping", "dark_transponder_gap"]
    ais_coverage: Literal["full", "partial", "dark_gap", "non_ais_unknown"]
    dark_gaps: list[DarkGapInfo] = field(default_factory=list)
    speed_at_cpa_kts: float | None = None
    min_encounter_speed_kts: float | None = None
    max_course_deviation_deg: float = 0.0
    confidence_pct: float = 85.0  # Rule 1: [0.0, 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4


class VesselAnomalyDetector:
    """Detects kinematic anomalies, transponder dark gaps, and non-AIS targets.

    Conforms to PRD Section 11 (FR-13, FR-19, C10) and rules.md (Rules 1, 4, 6).
    """

    def __init__(
        self,
        dark_gap_threshold_seconds: float = DEFAULT_DARK_GAP_THRESHOLD_SECONDS,
        course_turn_threshold_deg: float = DEFAULT_COURSE_TURN_THRESHOLD_DEG,
        origin_proximity_radius_m: float = 15000.0,  # 15 km search radius for gap DR crossing
    ) -> None:
        self.dark_gap_threshold_seconds = dark_gap_threshold_seconds
        self.course_turn_threshold_deg = course_turn_threshold_deg
        self.origin_proximity_radius_m = origin_proximity_radius_m

    def detect_transponder_gaps(
        self,
        records: list[AISTrackRecord],
        origin_centroid: tuple[float, float] | None = None,
    ) -> tuple[float, list[DarkGapInfo], Literal["full", "partial", "dark_gap"]]:
        """Inspects time deltas between consecutive AIS reports to flag dark gaps.

        Per FR-19 and Rule 4, if delta_t > 30 minutes:
          - Set ais_coverage = 'dark_gap'
          - Flag 'dark_transponder_gap'
          - Extrapolate dead-reckoning trajectory across the gap and check origin proximity.

        Args:
            records: Chronologically sorted discrete AIS reports.
            origin_centroid: Optional (lon, lat) of estimated spill origin mu_p.

        Returns:
            Tuple of (a_dark in [0.0, 1.0], list of DarkGapInfo, ais_coverage tag).
        """
        if len(records) < 2:
            return 0.0, [], "partial"

        # Ensure sorted by timestamp
        sorted_records = sorted(records, key=lambda r: r.timestamp)
        dark_gaps: list[DarkGapInfo] = []
        max_gap_sec = 0.0

        for i in range(len(sorted_records) - 1):
            r1 = sorted_records[i]
            r2 = sorted_records[i + 1]
            gap_sec = (r2.timestamp - r1.timestamp).total_seconds()

            if gap_sec > self.dark_gap_threshold_seconds:
                if gap_sec > max_gap_sec:
                    max_gap_sec = gap_sec

                gap_hours = gap_sec / 3600.0
                start_pt = (r1.lon, r1.lat)
                end_pt = (r2.lon, r2.lat)

                # Dead-reckoning path extrapolation across the gap
                min_dist_m: float | None = None
                dr_cpa_time: datetime | None = None
                crosses_origin = False

                if origin_centroid is not None:
                    o_lon, o_lat = origin_centroid
                    # Sample unobserved line at uniform 1-minute steps
                    n_steps = max(2, int(gap_sec / 60.0))
                    min_dist_m = float("inf")
                    best_step = 0

                    for s in range(n_steps + 1):
                        frac = s / float(n_steps)
                        interp_lon = start_pt[0] + frac * (end_pt[0] - start_pt[0])
                        interp_lat = start_pt[1] + frac * (end_pt[1] - start_pt[1])
                        dist = haversine_distance_m(interp_lon, interp_lat, o_lon, o_lat)
                        if dist < min_dist_m:
                            min_dist_m = dist
                            best_step = s

                    dr_cpa_time = r1.timestamp + timedelta(
                        seconds=(best_step / float(n_steps)) * gap_sec
                    )
                    crosses_origin = min_dist_m <= self.origin_proximity_radius_m

                dark_gaps.append(
                    DarkGapInfo(
                        gap_index=len(dark_gaps) + 1,
                        start_time=r1.timestamp,
                        end_time=r2.timestamp,
                        duration_seconds=gap_sec,
                        duration_hours=round(gap_hours, 2),
                        start_point=start_pt,
                        end_point=end_pt,
                        extrapolated_cpa_distance_m=round(min_dist_m, 1)
                        if min_dist_m is not None
                        else None,
                        extrapolated_cpa_time=dr_cpa_time,
                        crosses_origin_region=crosses_origin,
                    )
                )

        if dark_gaps:
            # Score A_dark based on max gap duration:
            # 30 min (1800s) -> 0.50, >= 2.0 hours (7200s) -> 1.00
            gap_ratio = (max_gap_sec - self.dark_gap_threshold_seconds) / (7200.0 - 1800.0)
            a_dark = min(1.0, max(0.5, 0.5 + 0.5 * gap_ratio))
            if any(g.crosses_origin_region for g in dark_gaps):
                a_dark = max(a_dark, 0.95)
            return a_dark, dark_gaps, "dark_gap"

        # No gaps exceeding threshold
        return 0.0, [], "full"

    def detect_course_deviation_anomaly(
        self,
        points: list[InterpolatedTrackPoint] | list[AISTrackRecord],
    ) -> tuple[float, float]:
        """Detects abnormal course turns or zig-zag loitering (> 45 deg deviation).

        Args:
            points: Chronological track points (interpolated or discrete).

        Returns:
            Tuple of (a_course in [0.0, 1.0], max_deviation_deg in [0.0, 180.0]).
        """
        if len(points) < 2:
            return 0.0, 0.0

        cogs = [p.cog for p in points if getattr(p, "cog", None) is not None]
        if not cogs:
            # Fallback to cog_deg if InterpolatedTrackPoint
            cogs = [p.cog_deg for p in points if hasattr(p, "cog_deg")]

        if len(cogs) < 2:
            return 0.0, 0.0

        # Overall entry-to-exit bearing
        start_pt = points[0]
        end_pt = points[-1]
        start_lon, start_lat = (
            (start_pt.lon, start_pt.lat)
            if hasattr(start_pt, "lon")
            else (start_pt.point.coordinates[0], start_pt.point.coordinates[1])
        )
        end_lon, end_lat = (
            (end_pt.lon, end_pt.lat)
            if hasattr(end_pt, "lon")
            else (end_pt.point.coordinates[0], end_pt.point.coordinates[1])
        )

        d_lon = math.radians(end_lon - start_lon)
        lat1 = math.radians(start_lat)
        lat2 = math.radians(end_lat)
        y = math.sin(d_lon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        overall_bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

        # 1. Measure maximum turn between consecutive points
        max_consecutive_turn = 0.0
        for i in range(len(cogs) - 1):
            turn = angular_difference_deg(cogs[i], cogs[i + 1])
            if turn > max_consecutive_turn:
                max_consecutive_turn = turn

        # 2. Measure maximum deviation from overall transit course
        max_transit_deviation = 0.0
        for cog in cogs:
            dev = angular_difference_deg(cog, overall_bearing)
            if dev > max_transit_deviation:
                max_transit_deviation = dev

        max_deviation = max(max_consecutive_turn, max_transit_deviation)

        # Scale A_course: 0 at <= 15 deg, reaches 1.0 at >= 90 deg
        if max_deviation <= 15.0:
            a_course = 0.0
        elif max_deviation >= 90.0:
            a_course = 1.0
        else:
            a_course = (max_deviation - 15.0) / (90.0 - 15.0)

        return round(a_course, 4), round(max_deviation, 1)

    def assess_trajectory(
        self,
        trajectory: ReconstructedTrajectory,
        origin_centroid: tuple[float, float] | None = None,
        encounter_distance_threshold_m: float = 20000.0,  # 20 km around origin
    ) -> AnomalyAssessment:
        """Performs comprehensive behavioral anomaly assessment on a reconstructed trajectory.

        Args:
            trajectory: Continuous reconstructed trajectory from TASK-024.
            origin_centroid: Estimated spill origin (lon, lat) centroid mu_p.
            encounter_distance_threshold_m: Distance threshold defining origin encounter.

        Returns:
            AnomalyAssessment with A_speed, A_course, A_dark, S_anomaly, and anomaly_flags.
        """
        anomaly_flags: list[str] = []

        # 1. Detect transponder dark gaps (FR-19, Rule 4)
        a_dark, dark_gaps, gap_coverage = self.detect_transponder_gaps(
            records=trajectory.discrete_points,
            origin_centroid=origin_centroid,
        )
        if dark_gaps:
            anomaly_flags.append("dark_transponder_gap")

        # 2. Speed drop anomaly evaluation (A_speed)
        # Evaluate speed at CPA
        speed_at_cpa = trajectory.cpa.sog_kts
        a_speed_cpa = compute_speed_drop_anomaly(speed_at_cpa)

        # Also inspect interpolated speeds during origin encounter
        encounter_points = [
            pt
            for pt in trajectory.interpolated_points
            if pt.distance_to_origin_m <= encounter_distance_threshold_m
        ]
        min_encounter_speed: float | None = None
        max_a_speed_encounter = 0.0

        if encounter_points:
            speeds = [pt.sog_kts for pt in encounter_points]
            min_encounter_speed = min(speeds)
            for s in speeds:
                a_s = compute_speed_drop_anomaly(s)
                if a_s > max_a_speed_encounter:
                    max_a_speed_encounter = a_s
        else:
            # Fallback to all interpolated points
            speeds = [pt.sog_kts for pt in trajectory.interpolated_points]
            min_encounter_speed = min(speeds) if speeds else speed_at_cpa
            max_a_speed_encounter = max(compute_speed_drop_anomaly(s) for s in speeds)

        a_speed = max(a_speed_cpa, max_a_speed_encounter)

        # If speed falls inside dumping band (4-8 kts) while transiting, flag dumping
        if a_speed >= 0.8:
            anomaly_flags.append("speed_drop_dumping")

        # 3. Course deviation anomaly evaluation (A_course)
        a_course, max_turn_deg = self.detect_course_deviation_anomaly(
            trajectory.interpolated_points
        )
        if max_turn_deg >= self.course_turn_threshold_deg:
            anomaly_flags.append("abnormal_course_turn")
            if min_encounter_speed is not None and min_encounter_speed < 5.0:
                anomaly_flags.append("loitering_turn")

        # 4. Determine final AIS coverage tag (Rule 4)
        if dark_gaps:
            ais_coverage = "dark_gap"
        elif trajectory.duration_hours < 2.0:
            ais_coverage = "partial"
        else:
            ais_coverage = "full"

        # 5. Composite Anomaly Score S_anomaly in [0.0, 100.0]
        # Multi-factor probabilistic fusion: 1.0 - (1 - A_speed)(1 - A_course)(1 - A_dark)
        prob_composite = 1.0 - (1.0 - a_speed) * (1.0 - a_course) * (1.0 - a_dark)
        # Ensure composite score is at least the highest individual indicator
        max_single = max(a_speed, a_course, a_dark)
        composite_factor = min(1.0, max(max_single, prob_composite))
        s_anomaly = round(composite_factor * 100.0, 2)

        # 6. Calibrated confidence percentage (Rule 1)
        # Based on trajectory confidence and report sample density
        confidence_pct = min(
            99.0, max(50.0, round(trajectory.confidence_pct * 0.95 + len(anomaly_flags) * 1.5, 1))
        )

        return AnomalyAssessment(
            mmsi=trajectory.mmsi,
            vessel_name=trajectory.vessel_name,
            vessel_type=trajectory.vessel_type,
            a_speed=round(a_speed, 4),
            a_course=round(a_course, 4),
            a_dark=round(a_dark, 4),
            s_anomaly=s_anomaly,
            anomaly_flags=anomaly_flags,
            ais_coverage=ais_coverage,
            dark_gaps=dark_gaps,
            speed_at_cpa_kts=round(speed_at_cpa, 1),
            min_encounter_speed_kts=round(min_encounter_speed, 1)
            if min_encounter_speed is not None
            else None,
            max_course_deviation_deg=max_turn_deg,
            confidence_pct=confidence_pct,
            data_source=trajectory.data_source,
        )

    def assess_non_ais_contact(
        self,
        contact_id: str,
        coordinates: tuple[float, float],
        detection_time: datetime,
        origin_centroid: tuple[float, float],
        estimated_length_m: float | None = None,
        radar_confidence_pct: float = 85.0,
        data_source: Literal["live", "cached", "synthetic"] = "synthetic",
    ) -> AnomalyAssessment:
        """Assesses an uncooperative / non-AIS vessel contact surfaced by radar or optical detection.

        Per FR-19, P4, and Rule 4:
          Vessels with no AIS transponder are never silently excluded. They are surfaced
          with ais_coverage = 'non_ais_unknown' and flagged as 'non_ais_radar_contact'.

        Args:
            contact_id: Synthetic or radar target identifier.
            coordinates: (lon, lat) of the non-AIS contact detection.
            detection_time: Timestamp of radar/optical contact.
            origin_centroid: (lon, lat) of estimated spill origin mu_p.
            estimated_length_m: Estimated target length from radar cross-section / bounding box.
            radar_confidence_pct: Detection confidence in [0.0, 100.0].
            data_source: 'live', 'cached', or 'synthetic'.

        Returns:
            AnomalyAssessment marked as 'non_ais_unknown' with A_dark = 1.0.
        """
        # Non-AIS targets receive maximum dark score (total AIS absence)
        a_dark = 1.0
        # Speed and course unknown without multi-frame track, assign neutral prior
        a_speed = 0.50
        a_course = 0.0

        # Distance to origin centroid
        dist_m = haversine_distance_m(
            coordinates[0], coordinates[1], origin_centroid[0], origin_centroid[1]
        )
        logger.info(
            "Assessing non-AIS radar contact %s at %s (est length: %s, distance to origin: %.1f m)",
            contact_id,
            detection_time.isoformat(),
            f"{estimated_length_m:.1f}m" if estimated_length_m is not None else "unknown",
            dist_m,
        )

        anomaly_flags = ["non_ais_radar_contact", "dark_transponder_gap"]

        # Composite anomaly score
        s_anomaly = 95.0

        # Generate deterministic synthetic pseudo-MMSI if contact_id is not integer
        try:
            mmsi_val = int(contact_id)
        except ValueError:
            # Hash contact_id into 9-digit pseudo MMSI starting with 999 (standard SAR search code)
            mmsi_val = 999000000 + abs(hash(contact_id)) % 1000000

        return AnomalyAssessment(
            mmsi=mmsi_val,
            vessel_name=f"UNIDENTIFIED CONTACT ({contact_id})",
            vessel_type="Unknown",
            a_speed=a_speed,
            a_course=a_course,
            a_dark=a_dark,
            s_anomaly=s_anomaly,
            anomaly_flags=anomaly_flags,
            ais_coverage="non_ais_unknown",
            dark_gaps=[],
            speed_at_cpa_kts=None,
            min_encounter_speed_kts=None,
            max_course_deviation_deg=0.0,
            confidence_pct=round(max(0.0, min(100.0, radar_confidence_pct)), 1),
            data_source=data_source,
        )
