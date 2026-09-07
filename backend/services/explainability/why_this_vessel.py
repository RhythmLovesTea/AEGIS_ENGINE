"""AEGIS-Marine: 'Why This Vessel?' Structured Evidence Composer (TASK-029).

Implements Feature 1 (D1) and PRD FR-16:
- Decomposes candidate vessel composite score S_culprit into 5 structured sub-scores:
  - Spatial: Mahalanobis distance D_M, physical distance in km, 1σ/2σ/3σ error ellipse bands.
  - Temporal: |t_CPA - t_release| in minutes/hours, exponential decay factor.
  - Kinematic: heading difference |θ_vessel - θ_slick| in degrees, speed modulation at CPA.
  - Anomaly: explicit breakdown of speed loitering/dumping and dark transponder gaps.
  - Type: vessel category justification and IMO registry reference.
- Generates 5-axis polar radar chart data and weighted contribution bar chart data.
- Assembles structured forensic evidence checklist with paired confidence (Rule 1).
- Enforces Rule 6: Strictly zero occurrences of banned terms.
"""

from __future__ import annotations

import contextlib
import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import (
    AnomalyBreakdown,
    BarChartItem,
    EvidenceChecklistItem,
    KinematicBreakdown,
    RadarChartDataPoint,
    SpatialBreakdown,
    TemporalBreakdown,
    TypeBreakdown,
    WhyThisVesselPayload,
)
from backend.app.schemas.vessel import SubScores

logger = logging.getLogger(__name__)

# Canonical AHP weights (PRD Section 11, TASK-026)
CANONICAL_WEIGHTS: dict[str, float] = {
    "spatial": 0.30,
    "temporal": 0.25,
    "kinematic": 0.15,
    "anomaly": 0.20,
    "type": 0.10,
}

# Regional benchmark / innocent baseline scores for comparison
FLEET_BENCHMARKS: dict[str, float] = {
    "spatial": 25.0,
    "temporal": 20.0,
    "kinematic": 30.0,
    "anomaly": 10.0,
    "type": 40.0,
}


def assert_no_banned_terms(text: str, context_label: str = "text") -> None:
    """Ensures text contains zero Rule 6 banned determination terms."""
    import re

    from scripts.lint_banned_terms import BANNED_RULES

    for rule in BANNED_RULES:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            raise ValueError(
                f"Rule 6 Violation: Detected banned term '{rule['name']}' in {context_label}: {text}"
            )


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculates great-circle distance between two coordinates in kilometers."""
    r = 6371.0  # Earth mean radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class WhyThisVesselComposer:
    """Forensic Explainability Service for Candidate Vessels (Feature 1 / D1).

    Produces structured, human-readable forensic rationales and chart payloads
    derived directly from persisted candidate records and case physical estimates.
    """

    def __init__(
        self,
        tau_hours: float = 1.5,
        default_weights: dict[str, float] | None = None,
    ) -> None:
        self.tau_hours = tau_hours
        self.weights = default_weights or dict(CANONICAL_WEIGHTS)

    def compose_from_db(
        self,
        db: Session,
        case_id: str | uuid.UUID,
        mmsi: int,
        custom_weights: dict[str, float] | None = None,
    ) -> WhyThisVesselPayload:
        """Loads case entities from database and composes forensic explanation payload.

        Args:
            db: Active SQLAlchemy database session.
            case_id: UUID of investigation case.
            mmsi: MMSI of candidate vessel to explain.
            custom_weights: Optional overriding AHP weights for what-if scenarios.

        Returns:
            WhyThisVesselPayload populated with granular breakdowns and visualization data.
        """
        case_uuid = uuid.UUID(str(case_id))
        candidate = (
            db.query(VesselCandidate)
            .filter(VesselCandidate.case_id == case_uuid, VesselCandidate.mmsi == mmsi)
            .first()
        )
        if not candidate:
            raise ValueError(f"Candidate vessel with MMSI {mmsi} not found for case {case_id}")

        origin = (
            db.query(OriginEstimate)
            .filter(OriginEstimate.case_id == case_uuid)
            .order_by(OriginEstimate.confidence_pct.desc())
            .first()
        )
        characterization = (
            db.query(SlickCharacterization)
            .filter(SlickCharacterization.case_id == case_uuid)
            .order_by(SlickCharacterization.created_at.desc())
            .first()
        )
        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.confidence.desc())
            .first()
        )

        return self.compose_from_candidate(
            candidate=candidate,
            origin=origin,
            characterization=characterization,
            detection=detection,
            custom_weights=custom_weights,
        )

    def compose_from_candidate(
        self,
        candidate: VesselCandidate | dict[str, Any],
        origin: OriginEstimate | None = None,
        characterization: SlickCharacterization | None = None,
        detection: SlickDetection | None = None,
        custom_weights: dict[str, float] | None = None,
    ) -> WhyThisVesselPayload:
        """Composes forensic explanation for a candidate vessel.

        Args:
            candidate: VesselCandidate ORM model or candidate dictionary.
            origin: Optional Tier 3 OriginEstimate entity.
            characterization: Optional Tier 2 SlickCharacterization entity.
            detection: Optional Tier 1 SlickDetection entity.
            custom_weights: Optional overriding AHP weight dictionary.

        Returns:
            Structured WhyThisVesselPayload conforming to PRD FR-16.
        """
        weights = custom_weights or self.weights

        # 1. Normalize candidate fields
        if isinstance(candidate, dict):
            mmsi = int(candidate.get("mmsi", 0))
            imo = candidate.get("imo")
            vessel_name = str(candidate.get("name", candidate.get("vessel_name", "Unknown Vessel")))
            flag_state = candidate.get("flag_state")
            vessel_type = str(candidate.get("vessel_type", "Unknown"))
            s_culprit = float(candidate.get("s_culprit", 0.0))
            confidence = float(candidate.get("confidence", 80.0))
            sub_scores_raw = candidate.get("sub_scores", {})
            anomaly_flags = list(candidate.get("anomaly_flags", []))
            ais_cov = str(candidate.get("ais_coverage", "full"))
            rank = candidate.get("rank")
            evidence_refs = list(candidate.get("evidence_refs", []))
            extra_details = candidate.get("details") or (
                sub_scores_raw.get("details", {}) if isinstance(sub_scores_raw, dict) else {}
            )
        else:
            mmsi = int(candidate.mmsi)
            imo = candidate.imo
            vessel_name = str(candidate.name)
            flag_state = candidate.flag_state
            vessel_type = str(candidate.vessel_type)
            s_culprit = float(candidate.s_culprit)
            confidence = float(candidate.confidence)
            sub_scores_raw = candidate.sub_scores or {}
            anomaly_flags = list(candidate.anomaly_flags or [])
            ais_cov = (
                candidate.ais_coverage.value
                if hasattr(candidate.ais_coverage, "value")
                else str(candidate.ais_coverage)
            )
            rank = getattr(candidate, "rank", None)
            evidence_refs = getattr(candidate, "evidence_refs", [])
            extra_details = (
                sub_scores_raw.get("details", {}) if isinstance(sub_scores_raw, dict) else {}
            )

        # 2. Extract persisted sub-scores
        s_spatial = float(sub_scores_raw.get("spatial", 0.0))
        s_temporal = float(sub_scores_raw.get("temporal", 0.0))
        s_kinematic = float(sub_scores_raw.get("kinematic", 0.0))
        s_anomaly = float(sub_scores_raw.get("anomaly", 0.0))
        s_type = float(sub_scores_raw.get("type", 0.0))

        sub_scores_schema = SubScores(
            spatial=s_spatial,
            temporal=s_temporal,
            kinematic=s_kinematic,
            anomaly=s_anomaly,
            type=s_type,
        )

        # 3. Generate 5 Component Breakdowns
        spatial_breakdown = self._build_spatial_breakdown(
            s_spatial=s_spatial,
            origin=origin,
            details=extra_details,
        )

        temporal_breakdown = self._build_temporal_breakdown(
            s_temporal=s_temporal,
            origin=origin,
            characterization=characterization,
            detection=detection,
            details=extra_details,
        )

        kinematic_breakdown = self._build_kinematic_breakdown(
            s_kinematic=s_kinematic,
            characterization=characterization,
            details=extra_details,
        )

        anomaly_breakdown = self._build_anomaly_breakdown(
            s_anomaly=s_anomaly,
            anomaly_flags=anomaly_flags,
            ais_coverage=ais_cov,
            details=extra_details,
        )

        type_breakdown = self._build_type_breakdown(
            s_type=s_type,
            vessel_type=vessel_type,
            imo=imo,
            flag_state=flag_state,
        )

        # 4. Generate Visualization Payloads (Radar and Bar charts)
        radar_data = self._build_radar_chart(
            sub_scores=sub_scores_schema,
            weights=weights,
        )

        bar_data = self._build_bar_chart(
            sub_scores=sub_scores_schema,
            weights=weights,
        )

        # 5. Generate Evidence Checklist
        evidence_checklist = self._build_evidence_checklist(
            spatial=spatial_breakdown,
            temporal=temporal_breakdown,
            kinematic=kinematic_breakdown,
            anomaly=anomaly_breakdown,
            v_type=type_breakdown,
            overall_confidence=confidence,
        )

        # 6. Generate Forensic Summary (Strictly Rule 6 Compliant)
        forensic_summary = self._generate_forensic_summary(
            vessel_name=vessel_name,
            mmsi=mmsi,
            vessel_type=vessel_type,
            s_culprit=s_culprit,
            confidence=confidence,
            spatial=spatial_breakdown,
            temporal=temporal_breakdown,
            kinematic=kinematic_breakdown,
            anomaly=anomaly_breakdown,
            v_type=type_breakdown,
            ais_coverage=ais_cov,
        )

        # Runtime verification of zero banned terms across all rationales and summaries
        assert_no_banned_terms(spatial_breakdown.rationale, "spatial_breakdown")
        assert_no_banned_terms(temporal_breakdown.rationale, "temporal_breakdown")
        assert_no_banned_terms(kinematic_breakdown.rationale, "kinematic_breakdown")
        assert_no_banned_terms(anomaly_breakdown.rationale, "anomaly_breakdown")
        assert_no_banned_terms(type_breakdown.rationale, "type_breakdown")
        assert_no_banned_terms(forensic_summary, "forensic_summary")
        for item in evidence_checklist:
            assert_no_banned_terms(item.finding, f"checklist_{item.check}")

        return WhyThisVesselPayload(
            mmsi=mmsi,
            vessel_name=vessel_name,
            s_culprit=s_culprit,
            confidence=confidence,
            sub_scores=sub_scores_schema,
            radar_data=[p.model_dump() for p in radar_data],
            forensic_summary=forensic_summary,
            rank=rank,
            imo=imo,
            vessel_type=vessel_type,
            flag_state=flag_state,
            ais_coverage=ais_cov,
            spatial_breakdown=spatial_breakdown,
            temporal_breakdown=temporal_breakdown,
            kinematic_breakdown=kinematic_breakdown,
            anomaly_breakdown=anomaly_breakdown,
            type_breakdown=type_breakdown,
            bar_data=bar_data,
            evidence_checklist=evidence_checklist,
            evidence_refs=evidence_refs,
        )

    def _build_spatial_breakdown(
        self,
        s_spatial: float,
        origin: OriginEstimate | None,
        details: dict[str, Any],
    ) -> SpatialBreakdown:
        """Decomposes spatial proximity into Mahalanobis distance, km, and sigma bands."""
        # Recover Mahalanobis distance D_M from S_spatial = 100 * exp(-0.5 * D_M^2)
        if "d_m" in details:
            d_m = float(details["d_m"])
        elif s_spatial > 0.0:
            ratio = max(1e-7, min(1.0, s_spatial / 100.0))
            d_m = math.sqrt(-2.0 * math.log(ratio))
        else:
            d_m = 5.0

        # Determine sigma band
        if d_m <= 1.0:
            sigma_band = "1sigma"
            inside_1sigma = True
            inside_2sigma = True
            inside_3sigma = True
        elif d_m <= 2.0:
            sigma_band = "2sigma"
            inside_1sigma = False
            inside_2sigma = True
            inside_3sigma = True
        elif d_m <= 3.0:
            sigma_band = "3sigma"
            inside_1sigma = False
            inside_2sigma = False
            inside_3sigma = True
        else:
            sigma_band = "outside_3sigma"
            inside_1sigma = False
            inside_2sigma = False
            inside_3sigma = False

        # Physical distance estimation
        origin_coords: tuple[float, float] | None = None
        cpa_coords: tuple[float, float] | None = None
        if origin and origin.centroid:
            pt = to_shape(origin.centroid)
            origin_coords = (float(pt.x), float(pt.y))

        if "cpa_coords" in details and details["cpa_coords"]:
            cpa_coords = tuple(details["cpa_coords"])

        if "cpa_dist_km" in details:
            dist_km = float(details["cpa_dist_km"])
        elif origin_coords and cpa_coords:
            dist_km = haversine_km(origin_coords[0], origin_coords[1], cpa_coords[0], cpa_coords[1])
        else:
            # Approximate physical distance from Mahalanobis D_M (1 sigma ~ 1.35 km in standard model)
            dist_km = d_m * 1.35

        # Format rationale without banned terms
        if inside_1sigma:
            rationale = (
                f"Closest point of approach occurred within the tight 1-sigma uncertainty core "
                f"({dist_km:.2f} km from origin centroid, Mahalanobis distance {d_m:.2f})."
            )
        elif inside_2sigma:
            rationale = (
                f"Closest point of approach fell within the 2-sigma uncertainty ellipse "
                f"({dist_km:.2f} km from origin centroid, Mahalanobis distance {d_m:.2f})."
            )
        elif inside_3sigma:
            rationale = (
                f"Closest point of approach intersected the 3-sigma outer uncertainty boundary "
                f"({dist_km:.2f} km from origin centroid, Mahalanobis distance {d_m:.2f})."
            )
        else:
            rationale = (
                f"Closest approach was outside the 3-sigma uncertainty boundary "
                f"({dist_km:.2f} km from origin centroid, Mahalanobis distance {d_m:.2f})."
            )

        return SpatialBreakdown(
            sub_score=round(s_spatial, 2),
            mahalanobis_distance=round(d_m, 3),
            physical_distance_km=round(dist_km, 3),
            sigma_band=sigma_band,
            inside_1sigma=inside_1sigma,
            inside_2sigma=inside_2sigma,
            inside_3sigma=inside_3sigma,
            cpa_coordinates=cpa_coords,
            origin_centroid=origin_coords,
            rationale=rationale,
        )

    def _build_temporal_breakdown(
        self,
        s_temporal: float,
        origin: OriginEstimate | None,
        characterization: SlickCharacterization | None,
        detection: SlickDetection | None,
        details: dict[str, Any],
    ) -> TemporalBreakdown:
        """Decomposes temporal coincidence into time delta, decay factor, and timestamps."""
        # Recover dt from S_temporal = 100 * exp(-dt / tau)
        if "delta_hours" in details:
            delta_hours = float(details["delta_hours"])
        elif s_temporal > 0.0:
            ratio = max(1e-7, min(1.0, s_temporal / 100.0))
            delta_hours = -self.tau_hours * math.log(ratio)
        else:
            delta_hours = 6.0

        delta_minutes = delta_hours * 60.0
        decay_factor = math.exp(-delta_hours / self.tau_hours)

        # Extract timestamps if available
        t_cpa = None
        t_release = None
        if "cpa_time" in details and details["cpa_time"]:
            with contextlib.suppress(Exception):
                t_cpa = datetime.fromisoformat(details["cpa_time"])

        if characterization and detection:
            t_obs = detection.detection_time
            if t_obs and t_obs.tzinfo is None:
                t_obs = t_obs.replace(tzinfo=UTC)
            t_age_hours = float(characterization.t_age_hours or 6.0)
            if t_obs:
                t_release = t_obs - timedelta(hours=t_age_hours)
        elif origin and origin.time_window_start and origin.time_window_end:
            mid = origin.time_window_start + (origin.time_window_end - origin.time_window_start) / 2
            t_release = mid

        if delta_minutes <= 15.0:
            rationale = (
                f"Near-exact temporal coincidence: CPA occurred within {delta_minutes:.1f} minutes "
                f"of estimated release time (temporal decay factor {decay_factor:.2f})."
            )
        elif delta_minutes <= 60.0:
            rationale = (
                f"Close temporal alignment: CPA was {delta_minutes:.1f} minutes ({delta_hours:.2f}h) "
                f"from estimated release window (decay factor {decay_factor:.2f})."
            )
        else:
            rationale = (
                f"Moderate-to-low temporal coincidence: CPA offset by {delta_hours:.2f} hours "
                f"({delta_minutes:.0f} minutes) from estimated release (decay factor {decay_factor:.2f})."
            )

        return TemporalBreakdown(
            sub_score=round(s_temporal, 2),
            delta_minutes=round(delta_minutes, 1),
            delta_hours=round(delta_hours, 2),
            decay_factor=round(decay_factor, 3),
            tau_hours=self.tau_hours,
            t_cpa=t_cpa,
            t_release=t_release,
            rationale=rationale,
        )

    def _build_kinematic_breakdown(
        self,
        s_kinematic: float,
        characterization: SlickCharacterization | None,
        details: dict[str, Any],
    ) -> KinematicBreakdown:
        """Decomposes kinematic alignment into heading differences and speed modulation."""
        slick_orientation = (
            float(characterization.principal_axis_deg)
            if characterization and characterization.principal_axis_deg is not None
            else float(details.get("slick_orientation_deg", 65.0))
        )
        vessel_cog = float(details.get("cog_deg", 68.0)) if "cog_deg" in details else None
        vessel_speed = float(details.get("speed_kts", 6.0)) if "speed_kts" in details else None

        if "heading_difference_deg" in details:
            delta_heading = float(details["heading_difference_deg"])
        elif vessel_cog is not None:
            raw_diff = abs(vessel_cog - slick_orientation) % 180.0
            delta_heading = min(raw_diff, 180.0 - raw_diff)
        else:
            # Estimate from s_kinematic: s = 100 * cos(dh) * f(v)
            cos_approx = max(0.0, min(1.0, s_kinematic / 100.0))
            delta_heading = math.degrees(math.acos(cos_approx))

        speed_val = vessel_speed if vessel_speed is not None else 6.0
        speed_mod = min(1.0, max(0.2, speed_val / 3.0))

        if delta_heading <= 10.0:
            rationale = (
                f"Course heading strongly aligned with observed slick principal axis "
                f"(angular offset {delta_heading:.1f}°, wake formation modulation {speed_mod:.2f})."
            )
        elif delta_heading <= 30.0:
            rationale = (
                f"Course heading moderately aligned with observed slick principal axis "
                f"(angular offset {delta_heading:.1f}°, wake modulation factor {speed_mod:.2f})."
            )
        else:
            rationale = (
                f"Vessel course diverged significantly from slick principal axis "
                f"(angular offset {delta_heading:.1f}°)."
            )

        return KinematicBreakdown(
            sub_score=round(s_kinematic, 2),
            vessel_cog_deg=vessel_cog,
            slick_orientation_deg=round(slick_orientation, 1),
            heading_difference_deg=round(delta_heading, 1),
            vessel_speed_kts=vessel_speed,
            speed_modulation_factor=round(speed_mod, 2),
            rationale=rationale,
        )

    def _build_anomaly_breakdown(
        self,
        s_anomaly: float,
        anomaly_flags: list[str],
        ais_coverage: str,
        details: dict[str, Any],
    ) -> AnomalyBreakdown:
        """Decomposes behavioral anomalies into speed drops, turns, and transponder dark gaps."""
        speed_loitering = (
            "speed_drop_dumping" in anomaly_flags or "speed_loitering" in anomaly_flags
        )
        dark_gap = (
            "dark_transponder_gap" in anomaly_flags
            or ais_coverage == "dark_gap"
            or "dark_gap" in anomaly_flags
        )
        course_turn = "course_turn" in anomaly_flags

        a_speed = float(details.get("a_speed", 1.0 if speed_loitering else 0.0))
        a_dark = float(details.get("a_dark", 1.0 if dark_gap else 0.0))
        a_course = float(details.get("a_course", 1.0 if course_turn else 0.0))
        speed_at_cpa = (
            float(details.get("speed_at_cpa", details.get("speed_kts", 6.2)))
            if speed_loitering
            else None
        )

        dark_intervals = list(details.get("dark_gap_intervals", []))
        if dark_gap and not dark_intervals:
            dark_intervals = [
                {
                    "duration_hours": details.get("gap_duration_hours", 2.0),
                    "coverage_status": ais_coverage,
                    "description": "AIS transponder silence across estimated origin zone",
                }
            ]

        # Construct informative rationale without banned words
        active_anomalies = []
        if speed_loitering:
            speed_str = f" at {speed_at_cpa:.1f} kts" if speed_at_cpa else ""
            active_anomalies.append(f"speed reduction into [4, 8] kt discharge band{speed_str}")
        if dark_gap:
            active_anomalies.append("transponder silence window exceeding 30 minutes")
        if course_turn:
            active_anomalies.append("abrupt course alteration across release coordinates")

        if active_anomalies:
            rationale = (
                f"Identified operational anomalies during passage: {'; '.join(active_anomalies)}."
            )
        else:
            rationale = (
                "No behavioral maneuvers, loitering speeds, or transponder dark gaps detected."
            )

        return AnomalyBreakdown(
            sub_score=round(s_anomaly, 2),
            anomaly_flags=anomaly_flags,
            speed_anomaly_score=round(a_speed, 2),
            course_anomaly_score=round(a_course, 2),
            dark_gap_score=round(a_dark, 2),
            speed_loitering_detected=speed_loitering,
            speed_at_cpa_kts=speed_at_cpa,
            dark_gap_detected=dark_gap,
            dark_gap_intervals=dark_intervals,
            rationale=rationale,
        )

    def _build_type_breakdown(
        self,
        s_type: float,
        vessel_type: str,
        imo: int | None,
        flag_state: str | None,
    ) -> TypeBreakdown:
        """Decomposes vessel type prior risk and registry information."""
        imo_str = str(imo) if imo else "Unregistered / Non-AIS"
        flag_str = str(flag_state) if flag_state else "Unknown Flag State"
        registry_ref = f"IMO {imo_str} ({flag_str})"

        v_lower = vessel_type.lower()
        if "tanker" in v_lower:
            type_desc = "Crude/product tanker with high cargo discharge risk profile"
        elif "cargo" in v_lower or "container" in v_lower or "bulk" in v_lower:
            type_desc = "Commercial cargo carrier with bunker and oily bilge discharge capacity"
        elif "offshore" in v_lower:
            type_desc = (
                "Offshore support/supply vessel operating in vicinity of production infrastructure"
            )
        elif "fishing" in v_lower:
            type_desc = "Commercial fishing vessel with moderate fuel capacity"
        elif "non_ais" in v_lower:
            type_desc = "Unidentified radar contact lacking active AIS broadcast"
        else:
            type_desc = f"Vessel category: {vessel_type}"

        rationale = (
            f"Vessel type '{vessel_type}' carries a prior discharge index of {s_type:.1f}/100 "
            f"({type_desc}; Registry: {registry_ref})."
        )

        return TypeBreakdown(
            sub_score=round(s_type, 2),
            vessel_type=vessel_type,
            prior_risk_score=round(s_type, 2),
            imo=imo,
            flag_state=flag_state,
            registry_reference=registry_ref,
            rationale=rationale,
        )

    def _build_radar_chart(
        self,
        sub_scores: SubScores,
        weights: dict[str, float],
    ) -> list[RadarChartDataPoint]:
        """Assembles 5-axis polar coordinates for frontend radar chart."""
        axes = [
            ("spatial", "Spatial Proximity", sub_scores.spatial),
            ("temporal", "Temporal Coincidence", sub_scores.temporal),
            ("kinematic", "Kinematic Alignment", sub_scores.kinematic),
            ("anomaly", "Behavioral Anomaly", sub_scores.anomaly),
            ("type", "Vessel Type Prior", sub_scores.type),
        ]

        radar_points: list[RadarChartDataPoint] = []
        for key, axis_label, val in axes:
            w = weights.get(key, CANONICAL_WEIGHTS.get(key, 0.20))
            radar_points.append(
                RadarChartDataPoint(
                    axis=axis_label,
                    key=key,
                    value=round(val, 1),
                    weight=round(w, 2),
                    weighted_score=round(val * w, 2),
                    fleet_benchmark=FLEET_BENCHMARKS.get(key, 20.0),
                )
            )

        return radar_points

    def _build_bar_chart(
        self,
        sub_scores: SubScores,
        weights: dict[str, float],
    ) -> list[BarChartItem]:
        """Assembles weighted contribution bar chart items for each criterion."""
        items = [
            ("spatial", "Spatial Proximity", sub_scores.spatial),
            ("temporal", "Temporal Coincidence", sub_scores.temporal),
            ("kinematic", "Kinematic Alignment", sub_scores.kinematic),
            ("anomaly", "Behavioral Anomaly", sub_scores.anomaly),
            ("type", "Vessel Type Prior", sub_scores.type),
        ]

        bar_items: list[BarChartItem] = []
        for key, category, raw_score in items:
            w = weights.get(key, CANONICAL_WEIGHTS.get(key, 0.20))
            weighted_contrib = raw_score * w
            max_contrib = 100.0 * w
            bar_items.append(
                BarChartItem(
                    category=category,
                    key=key,
                    raw_score=round(raw_score, 1),
                    weight=round(w, 2),
                    weighted_contribution=round(weighted_contrib, 2),
                    max_contribution=round(max_contrib, 2),
                )
            )

        return bar_items

    def _build_evidence_checklist(
        self,
        spatial: SpatialBreakdown,
        temporal: TemporalBreakdown,
        kinematic: KinematicBreakdown,
        anomaly: AnomalyBreakdown,
        v_type: TypeBreakdown,
        overall_confidence: float,
    ) -> list[EvidenceChecklistItem]:
        """Compiles objective evidence checklist with status and paired confidence."""
        checklist: list[EvidenceChecklistItem] = []

        # 1. Spatial check
        spatial_status = (
            "positive_indicator"
            if spatial.inside_1sigma
            else ("neutral" if spatial.inside_2sigma else "unlikely")
        )
        checklist.append(
            EvidenceChecklistItem(
                check="Spatial Origin Intersection",
                status=spatial_status,
                finding=(
                    f"CPA {spatial.physical_distance_km:.2f} km from centroid, "
                    f"within {spatial.sigma_band} ellipse (D_M = {spatial.mahalanobis_distance:.2f})"
                ),
                confidence_pct=min(100.0, max(0.0, overall_confidence)),
            )
        )

        # 2. Temporal check
        temporal_pass = temporal.delta_minutes <= 90.0
        temporal_status = (
            "positive_indicator"
            if temporal.delta_minutes <= 30.0
            else ("neutral" if temporal_pass else "unlikely")
        )
        checklist.append(
            EvidenceChecklistItem(
                check="Release Temporal Coincidence",
                status=temporal_status,
                finding=(
                    f"Delta |t_CPA - t_release| = {temporal.delta_minutes:.1f} min "
                    f"(decay factor {temporal.decay_factor:.2f})"
                ),
                confidence_pct=min(100.0, max(0.0, overall_confidence)),
            )
        )

        # 3. Kinematic check
        kinematic_pass = kinematic.heading_difference_deg <= 30.0
        kinematic_status = (
            "positive_indicator"
            if kinematic.heading_difference_deg <= 15.0
            else ("neutral" if kinematic_pass else "unlikely")
        )
        checklist.append(
            EvidenceChecklistItem(
                check="Trajectory & Slick Orientation Alignment",
                status=kinematic_status,
                finding=f"Angular offset {kinematic.heading_difference_deg:.1f}° relative to slick principal axis",
                confidence_pct=min(100.0, max(0.0, overall_confidence)),
            )
        )

        # 4. Behavioral Anomaly check
        anomaly_detected = (
            anomaly.speed_loitering_detected
            or anomaly.dark_gap_detected
            or len(anomaly.anomaly_flags) > 0
        )
        anomaly_status = "positive_indicator" if anomaly_detected else "neutral"
        flag_summary = ", ".join(anomaly.anomaly_flags) if anomaly.anomaly_flags else "none"
        checklist.append(
            EvidenceChecklistItem(
                check="Operational Behavioral Anomalies",
                status=anomaly_status,
                finding=f"Detected flags: {flag_summary} (anomaly score {anomaly.sub_score:.1f}/100)",
                confidence_pct=min(100.0, max(0.0, overall_confidence)),
            )
        )

        # 5. Vessel Typology check
        type_status = "positive_indicator" if v_type.prior_risk_score >= 70.0 else "neutral"
        checklist.append(
            EvidenceChecklistItem(
                check="Vessel Category Discharge Prior",
                status=type_status,
                finding=f"{v_type.vessel_type} ({v_type.registry_reference}, prior index {v_type.prior_risk_score:.1f}/100)",
                confidence_pct=min(100.0, max(0.0, overall_confidence)),
            )
        )

        return checklist

    def _generate_forensic_summary(
        self,
        vessel_name: str,
        mmsi: int,
        vessel_type: str,
        s_culprit: float,
        confidence: float,
        spatial: SpatialBreakdown,
        temporal: TemporalBreakdown,
        kinematic: KinematicBreakdown,
        anomaly: AnomalyBreakdown,
        v_type: TypeBreakdown,
        ais_coverage: str,
    ) -> str:
        """Synthesizes objective forensic overview strictly adhering to Rule 6."""
        # Classify correlation level using approved objective language
        if s_culprit >= 75.0:
            correlation_desc = "highly correlated as a candidate suspect"
        elif s_culprit >= 50.0:
            correlation_desc = "moderately correlated as a candidate suspect"
        elif s_culprit >= 30.0:
            correlation_desc = "weakly correlated as a potential source"
        else:
            correlation_desc = "shows low correlation with the observed spill event"

        summary_lines = [
            f"Vessel {vessel_name} (MMSI: {mmsi}, Type: {vessel_type}) is {correlation_desc} "
            f"with an overall attribution score of {s_culprit:.1f}/100 (paired confidence: {confidence:.1f}%).",
            f"Spatially, the vessel reached closest approach {spatial.physical_distance_km:.2f} km from the estimated origin centroid, "
            f"falling within the {spatial.sigma_band} uncertainty envelope (Mahalanobis distance: {spatial.mahalanobis_distance:.2f}).",
            f"Temporally, CPA was reached {temporal.delta_minutes:.1f} minutes from the estimated discharge timestamp "
            f"(temporal decay factor: {temporal.decay_factor:.2f}).",
            f"Kinematically, the transit heading was aligned within {kinematic.heading_difference_deg:.1f}° of the slick's principal elongation axis.",
            f"Typology assessment reflects a {v_type.vessel_type} classification with an operational discharge risk index of {v_type.prior_risk_score:.1f}/100 ({v_type.registry_reference}).",
        ]

        # Detail anomaly and coverage conditions
        if anomaly.speed_loitering_detected or anomaly.dark_gap_detected:
            indicators = []
            if anomaly.speed_loitering_detected:
                indicators.append("a speed drop into the operational discharge velocity window")
            if anomaly.dark_gap_detected:
                indicators.append("an AIS transponder gap across the origin envelope")
            summary_lines.append(f"Behavioral evaluation detected {' and '.join(indicators)}.")
        elif ais_coverage == "dark_gap":
            summary_lines.append(
                "AIS coverage indicates transponder silence during transit across the surveillance zone."
            )
        else:
            summary_lines.append(
                "No abnormal loitering speeds or transponder silence gaps were observed along the transit path."
            )

        return " ".join(summary_lines)
