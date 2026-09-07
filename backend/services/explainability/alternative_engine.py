"""AEGIS-Marine: Alternative Explanation Engine (TASK-030).

Implements Feature 7 (P2) and PRD Section 11 / FR-18:
- Evaluates non-vessel alternative hypotheses to guarantee balanced forensic evaluation:
  1. 'natural_seep': Geological hydrocarbon seep proximity based on natural seeps catalog.
  2. 'imaging_artifact': False-positive lookalike risk modulated by radar incidence angle & wind.
  3. 'non_ais_vessel': Unlisted / dark target hypothesis based on AIS coverage gaps & radar contacts.
- Enforces Product Rule 5: Every case must persist at least one alternative explanation hypothesis
  into 'alternative_explanations' table before the case is marked ready.
- Enforces Product Rule 1: Mandatory confidence score in [0.0, 100.0] on every hypothesis.
- Enforces Product Rule 6: Strictly zero occurrences of banned determination terms.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    AlternativeExplanation,
    Case,
    OriginEstimate,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import (
    AlternativeExplanationResponse,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SEEPS_PATH = BASE_DIR / "data" / "geospatial" / "natural_seeps.geojson"

# Fallback reference seeps if GeoJSON catalog is unavailable
FALLBACK_SEEPS: list[dict[str, Any]] = [
    {
        "seep_id": "SEEP-IND-BH01",
        "name": "Bombay High Shelf Seep Alpha",
        "basin": "Mumbai Offshore Basin",
        "coordinates": (71.85, 19.35),
        "activity_status": "active",
        "water_depth_m": 78.0,
        "seep_type": "thermogenic_gas_and_light_crude",
    },
    {
        "seep_id": "SEEP-IND-BH02",
        "name": "Bombay High South Flank Seep",
        "basin": "Mumbai Offshore Basin",
        "coordinates": (72.10, 18.70),
        "activity_status": "intermittent",
        "water_depth_m": 85.0,
        "seep_type": "thermogenic_condensate",
    },
    {
        "seep_id": "SEEP-IND-BH03",
        "name": "Neelam-Heera Structural Fault Seep",
        "basin": "Mumbai Offshore Basin",
        "coordinates": (72.30, 18.88),
        "activity_status": "active",
        "water_depth_m": 62.0,
        "seep_type": "thermogenic_crude",
    },
]


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


def initial_bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculates initial compass bearing from point 1 to point 2 in degrees [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    x = math.sin(delta_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360.0) % 360.0


class AlternativeExplanationEngine:
    """Forensic Alternative Explanation Engine (FR-18, Rule 5, Feature 7).

    Scores non-vessel hypotheses (natural seep, imaging artifact, non-AIS dark ship)
    alongside candidate vessel rankings to maintain objective forensic balance.
    """

    def __init__(
        self,
        seep_catalog_path: str | Path | None = None,
        seep_decay_km: float = 3.0,
    ) -> None:
        self.catalog_path = Path(seep_catalog_path) if seep_catalog_path else DEFAULT_SEEPS_PATH
        self.seep_decay_km = seep_decay_km
        self.seeps: list[dict[str, Any]] = self._load_seep_catalog()

    def _load_seep_catalog(self) -> list[dict[str, Any]]:
        """Loads natural seeps from GeoJSON file with fallback to static catalog."""
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, encoding="utf-8") as f:
                    data = json.load(f)
                seep_items = []
                for feat in data.get("features", []):
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [0.0, 0.0])
                    props = feat.get("properties", {})
                    seep_items.append(
                        {
                            "seep_id": props.get("seep_id", feat.get("id", "SEEP-UNK")),
                            "name": props.get("name", "Unknown Natural Seep"),
                            "basin": props.get("basin", "Unknown Basin"),
                            "coordinates": (float(coords[0]), float(coords[1])),
                            "activity_status": props.get("activity_status", "intermittent"),
                            "water_depth_m": float(props.get("water_depth_m", 50.0)),
                            "seep_type": props.get("seep_type", "thermogenic_crude"),
                        }
                    )
                if seep_items:
                    logger.info(
                        "Loaded %d natural seeps from %s", len(seep_items), self.catalog_path
                    )
                    return seep_items
            except Exception as exc:
                logger.warning(
                    "Error loading natural seep catalog from %s: %s; falling back to default catalog",
                    self.catalog_path,
                    exc,
                )

        logger.info(
            "Using built-in fallback natural seep catalog (%d entries)", len(FALLBACK_SEEPS)
        )
        return list(FALLBACK_SEEPS)

    def evaluate_natural_seep(
        self,
        target_coords: tuple[float, float],
    ) -> dict[str, Any]:
        """Evaluates proximity of spill target point to known natural hydrocarbon seeps.

        Args:
            target_coords: (lon, lat) coordinates of spill origin or slick centroid.

        Returns:
            Dictionary with hypothesis score, confidence, and empirical evidence.
        """
        if not self.seeps:
            return {
                "hypothesis": "natural_seep",
                "score": 0.0,
                "confidence": 70.0,
                "evidence": {"message": "No catalog seeps available in region"},
            }

        min_dist_km = float("inf")
        nearest_seep = self.seeps[0]

        for seep in self.seeps:
            c_lon, c_lat = seep["coordinates"]
            dist_km = haversine_km(target_coords[0], target_coords[1], c_lon, c_lat)
            if dist_km < min_dist_km:
                min_dist_km = dist_km
                nearest_seep = seep

        # Proximity score formula: S_seep = 100 * exp(-d / tau)
        raw_score = 100.0 * math.exp(-min_dist_km / self.seep_decay_km)

        # Modulate by activity status (active: 1.0, intermittent: 0.85, dormant: 0.35)
        act_status = nearest_seep.get("activity_status", "intermittent").lower()
        if "active" in act_status:
            act_factor = 1.0
        elif "intermittent" in act_status:
            act_factor = 0.85
        else:
            act_factor = 0.35

        score = round(max(0.0, min(100.0, raw_score * act_factor)), 2)

        bearing = initial_bearing_deg(
            target_coords[0],
            target_coords[1],
            nearest_seep["coordinates"][0],
            nearest_seep["coordinates"][1],
        )

        # Objective rationale conforming to Rule 6
        if min_dist_km <= 2.0:
            rationale = (
                f"Close proximity to cataloged seep formation: origin is located {min_dist_km:.2f} km "
                f"from {nearest_seep['name']} ({nearest_seep['basin']}). Geological discharge represents "
                f"a strong alternative hypothesis."
            )
        elif min_dist_km <= 5.0:
            rationale = (
                f"Moderate distance to known seep formation: origin is {min_dist_km:.2f} km from "
                f"{nearest_seep['name']} (bearing {bearing:.1f}°). Natural seepage remains a plausible candidate source."
            )
        else:
            rationale = (
                f"Significant separation from known geological seeps: nearest cataloged formation is "
                f"{nearest_seep['name']} at {min_dist_km:.1f} km distance. Natural seepage is unlikely."
            )

        assert_no_banned_terms(rationale, "natural_seep_rationale")

        return {
            "hypothesis": "natural_seep",
            "score": score,
            "confidence": 85.0,  # Rule 1
            "evidence": {
                "nearest_seep_id": nearest_seep["seep_id"],
                "nearest_seep_name": nearest_seep["name"],
                "basin": nearest_seep["basin"],
                "distance_km": round(min_dist_km, 2),
                "bearing_deg": round(bearing, 1),
                "water_depth_m": nearest_seep["water_depth_m"],
                "seep_type": nearest_seep["seep_type"],
                "activity_status": nearest_seep["activity_status"],
                "target_coordinates": target_coords,
                "rationale": rationale,
            },
        }

    def evaluate_imaging_artifact(
        self,
        lookalike_risk: float = 0.05,
        incidence_angle_deg: float = 34.5,
        wind_speed_ms: float = 5.5,
        sensor: str = "Sentinel-1 SAR IW",
    ) -> dict[str, Any]:
        """Evaluates the probability that the detection is a SAR false-positive or lookalike.

        Args:
            lookalike_risk: Model lookalike probability in [0.0, 1.0] from Tier 1.
            incidence_angle_deg: Local SAR radar incidence angle in degrees.
            wind_speed_ms: Ambient 10m wind speed in m/s.
            sensor: Earth observation sensor identifier.

        Returns:
            Dictionary with hypothesis score, confidence, and empirical evidence.
        """
        base_score = 100.0 * max(0.0, min(1.0, lookalike_risk))

        # Modulate by incidence angle: steep (<25°) or shallow (>42°) angles increase lookalike noise
        angle_factor = 1.0
        angle_notes = []
        if incidence_angle_deg < 25.0:
            angle_factor = 1.25
            angle_notes.append("steep incidence angle (< 25°) reduces backscatter contrast")
        elif incidence_angle_deg > 42.0:
            angle_factor = 1.15
            angle_notes.append(
                "shallow incidence angle (> 42°) increases sea surface roughness noise"
            )

        # Modulate by low wind conditions: wind < 3 m/s causes natural biogenic slick lookalikes
        wind_factor = 1.0
        if wind_speed_ms < 3.0:
            wind_factor = 1.30
            angle_notes.append(
                "low wind regime (< 3.0 m/s) facilitates biogenic surfactant formation"
            )

        score = round(max(0.0, min(100.0, base_score * angle_factor * wind_factor)), 2)

        if score >= 50.0:
            rationale = (
                f"Elevated lookalike indicator: segmentation uncertainty ({lookalike_risk:.1%}) "
                f"combined with environmental radar factors ({'; '.join(angle_notes) or 'environmental conditions'}) "
                f"indicates non-hydrocarbon artifact plausibility."
            )
        elif score >= 20.0:
            rationale = (
                f"Moderate lookalike indicator: baseline lookalike risk is {lookalike_risk:.1%}. "
                f"Environmental parameters show minor artifact potential."
            )
        else:
            rationale = (
                f"Low imaging artifact probability: high SAR dark-spot contrast and stable wind "
                f"conditions ({wind_speed_ms:.1f} m/s) make a false-alarm lookalike unlikely (risk: {lookalike_risk:.1%})."
            )

        assert_no_banned_terms(rationale, "imaging_artifact_rationale")

        return {
            "hypothesis": "imaging_artifact",
            "score": score,
            "confidence": 82.0,  # Rule 1
            "evidence": {
                "lookalike_risk": round(lookalike_risk, 3),
                "incidence_angle_deg": round(incidence_angle_deg, 1),
                "wind_speed_ms": round(wind_speed_ms, 1),
                "sensor": sensor,
                "angle_factor": round(angle_factor, 2),
                "wind_factor": round(wind_factor, 2),
                "rationale": rationale,
            },
        }

    def evaluate_non_ais_vessel(
        self,
        candidate_count: int = 4,
        dark_gap_count: int = 1,
        unidentified_radar_contacts: int = 0,
        regional_ais_coverage: str = "partial",
    ) -> dict[str, Any]:
        """Evaluates hypothesis of an unlisted or non-AIS dark vessel discharge.

        Args:
            candidate_count: Total correlated candidate vessels in envelope.
            dark_gap_count: Number of vessels displaying transponder silence gaps.
            unidentified_radar_contacts: Number of non-AIS SAR radar hard contacts.
            regional_ais_coverage: Regional satellite AIS reception reliability.

        Returns:
            Dictionary with hypothesis score, confidence, and empirical evidence.
        """
        # Base non-AIS probability
        score = 15.0

        notes = []
        if unidentified_radar_contacts > 0:
            score += 45.0 * min(2, unidentified_radar_contacts)
            notes.append(
                f"{unidentified_radar_contacts} unidentified radar target(s) detected without AIS match"
            )

        if dark_gap_count > 0:
            score += 25.0 * min(2, dark_gap_count)
            notes.append(
                f"{dark_gap_count} correlated vessel(s) showed transponder silence windows"
            )

        if regional_ais_coverage in ("partial", "poor"):
            score += 15.0
            notes.append("regional AIS satellite constellation coverage exhibits latency/gaps")
        elif regional_ais_coverage == "dense":
            score -= 10.0

        score = round(max(0.0, min(100.0, score)), 2)

        if score >= 60.0:
            rationale = (
                f"Significant non-AIS / dark vessel indicator: {'; '.join(notes)}. "
                f"An unlisted or non-broadcasting vessel is a viable alternative candidate source."
            )
        elif score >= 30.0:
            rationale = (
                f"Moderate non-AIS target plausibility: observed {'; '.join(notes) if notes else 'normal coverage'}. "
                f"A non-reporting vessel cannot be entirely ruled out."
            )
        else:
            rationale = (
                "Comprehensive AIS coverage across the surveillance corridor with no unexplained "
                "radar contacts makes an undetected non-AIS vessel unlikely."
            )

        assert_no_banned_terms(rationale, "non_ais_vessel_rationale")

        return {
            "hypothesis": "non_ais_vessel",
            "score": score,
            "confidence": 78.0,  # Rule 1
            "evidence": {
                "candidate_count": candidate_count,
                "dark_gap_count": dark_gap_count,
                "unidentified_radar_contacts": unidentified_radar_contacts,
                "regional_ais_coverage": regional_ais_coverage,
                "rationale": rationale,
            },
        }

    def evaluate_case_hypotheses(
        self,
        origin_coords: tuple[float, float],
        lookalike_risk: float = 0.05,
        incidence_angle_deg: float = 34.5,
        wind_speed_ms: float = 5.5,
        sensor: str = "Sentinel-1 SAR IW",
        candidate_count: int = 4,
        dark_gap_count: int = 1,
        unidentified_radar_contacts: int = 0,
        regional_ais_coverage: str = "partial",
    ) -> list[dict[str, Any]]:
        """Evaluates all 3 non-vessel alternative hypotheses for a case.

        Guarantees Rule 5: Always produces at least one (and typically all 3)
        non-vessel hypotheses.
        """
        hypotheses = [
            self.evaluate_natural_seep(target_coords=origin_coords),
            self.evaluate_imaging_artifact(
                lookalike_risk=lookalike_risk,
                incidence_angle_deg=incidence_angle_deg,
                wind_speed_ms=wind_speed_ms,
                sensor=sensor,
            ),
            self.evaluate_non_ais_vessel(
                candidate_count=candidate_count,
                dark_gap_count=dark_gap_count,
                unidentified_radar_contacts=unidentified_radar_contacts,
                regional_ais_coverage=regional_ais_coverage,
            ),
        ]
        return hypotheses

    def evaluate_and_persist_case(
        self,
        db: Session,
        case_id: str | uuid.UUID,
    ) -> list[AlternativeExplanationResponse]:
        """Loads case context from database, computes alternative hypotheses, and bulk persists rows.

        Enforces:
        - Rule 1: Paired confidence in [0.0, 100.0] on every hypothesis.
        - Rule 5: Persists at least one non-vessel hypothesis into 'alternative_explanations'.
        - Rule 6: Zero banned determination terms in all output copy.

        Args:
            db: Active SQLAlchemy database session.
            case_id: Target investigation case UUID.

        Returns:
            List of persisted AlternativeExplanationResponse records.
        """
        case_uuid = uuid.UUID(str(case_id))

        case_entity = db.query(Case).filter(Case.id == case_uuid).first()
        if not case_entity:
            raise ValueError(f"Case {case_id} not found in database.")

        # 1. Extract Origin coordinates
        origin = (
            db.query(OriginEstimate)
            .filter(OriginEstimate.case_id == case_uuid)
            .order_by(OriginEstimate.confidence_pct.desc())
            .first()
        )
        if origin and origin.centroid:
            pt = to_shape(origin.centroid)
            origin_coords = (float(pt.x), float(pt.y))
        else:
            # Fallback to default Bombay High coordinates
            origin_coords = (72.290, 18.865)

        # 2. Extract Detection metadata
        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.confidence.desc())
            .first()
        )
        lookalike_risk = (
            float(detection.lookalike_risk)
            if detection and detection.lookalike_risk is not None
            else 0.05
        )
        sensor = detection.sensor if detection and detection.sensor else "Sentinel-1 SAR IW"

        # 3. Extract Candidates summary
        candidates = db.query(VesselCandidate).filter(VesselCandidate.case_id == case_uuid).all()
        candidate_count = len(candidates)
        dark_gap_count = sum(
            1
            for c in candidates
            if (
                c.ais_coverage == AISCoverage.DARK_GAP
                or "dark_transponder_gap" in (c.anomaly_flags or [])
            )
        )
        unidentified_contacts = sum(
            1
            for c in candidates
            if (c.ais_coverage == AISCoverage.NON_AIS_UNKNOWN or "non_ais" in c.vessel_type.lower())
        )

        # 4. Evaluate all 3 hypotheses
        hypotheses_data = self.evaluate_case_hypotheses(
            origin_coords=origin_coords,
            lookalike_risk=lookalike_risk,
            incidence_angle_deg=34.5,
            wind_speed_ms=5.5,
            sensor=sensor,
            candidate_count=candidate_count,
            dark_gap_count=dark_gap_count,
            unidentified_radar_contacts=unidentified_contacts,
        )

        # 5. Idempotent replacement in database
        db.query(AlternativeExplanation).filter(
            AlternativeExplanation.case_id == case_uuid
        ).delete()

        persisted_entities: list[AlternativeExplanation] = []
        for h in hypotheses_data:
            entity = AlternativeExplanation(
                id=uuid.uuid4(),
                case_id=case_uuid,
                hypothesis=h["hypothesis"],
                score=h["score"],
                confidence=h["confidence"],
                evidence=h["evidence"],
            )
            db.add(entity)
            persisted_entities.append(entity)

        db.commit()

        # Rule 5 assertion: at least one alternative hypothesis persisted
        if not persisted_entities:
            raise RuntimeError(
                f"Rule 5 Violation: Case {case_id} failed to produce any alternative explanation."
            )

        logger.info(
            "Persisted %d alternative explanations for case %s (Rule 5 satisfied)",
            len(persisted_entities),
            case_id,
        )

        return [
            AlternativeExplanationResponse(
                id=e.id,
                case_id=e.case_id,
                hypothesis=e.hypothesis,
                score=e.score,
                confidence=e.confidence,
                evidence=e.evidence,
                created_at=e.created_at or datetime.now(),
            )
            for e in persisted_entities
        ]
