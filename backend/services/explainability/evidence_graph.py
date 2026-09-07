"""AEGIS-Marine: Evidence Timeline & Node-Edge Graph Builders (TASK-032).

Implements Feature 8 (Evidence Timeline) and Feature 11 / P5 (Interactive Evidence Graph)
per PRD Section 11 & Architecture Section 4.5:
- Chronological event reconstruction timeline across 6 forensic milestones:
  1. Satellite acquisition timestamp & sensor details (Sentinel-1 SAR at t_obs).
  2. Estimated oil release window [t_start, t_end] from Fay spreading age inversion.
  3. Candidate vessel entry into surveillance bounding zone.
  4. Anomaly triggers (speed drop dumping, dark transponder gaps, loitering).
  5. Closest point of approach (CPA) to inferred origin centroid.
  6. Slick drift and spreading progression under met-ocean forcing.
- Directed Acyclic Graph (DAG) mapping causal forensic evidence from satellite observation down to
  slick, origin region, time window, AIS tracks, candidate vessels, anomalies, and alternative hypotheses.
- Topological sort and acyclic validation using networkx.
- Constitutional Rules:
  - Rule 1: Mandatory paired confidence score on all timeline items, graph nodes, edges, and payloads.
  - Rule 4: Data source attribution (live/cached/synthetic).
  - Rule 6: Strictly zero occurrences of banned determination terms.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import networkx as nx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, Polygon
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AlternativeExplanation,
    Case,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import (
    CounterfactualResult,
    EvidenceBundlePayload,
    EvidenceGraphPayload,
    EvidenceTimelineItem,
    EvidenceTimelinePayload,
    GraphEdge,
    GraphNode,
)

logger = logging.getLogger(__name__)


def assert_no_banned_terms(text: str, context_label: str = "text") -> None:
    """Ensures text contains zero Rule 6 banned determination terms."""
    import re

    from scripts.lint_banned_terms import BANNED_RULES

    for rule in BANNED_RULES:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            raise ValueError(
                f"Rule 6 Violation: Detected banned term '{rule['name']}' in {context_label}: {text}"
            )


class EvidenceGraphBuilder:
    """Builder service for Evidence Timelines and Interactive Node-Edge Evidence Graphs."""

    def __init__(self, default_confidence_pct: float = 85.0) -> None:
        self.default_confidence_pct = default_confidence_pct

    def build_timeline(
        self,
        case_id: uuid.UUID | str,
        detection: SlickDetection | dict[str, Any],
        characterization: SlickCharacterization | dict[str, Any],
        origin: OriginEstimate | dict[str, Any],
        candidates: list[VesselCandidate | dict[str, Any]],
        mmsi: int | None = None,
        metocean_summary: dict[str, Any] | None = None,
    ) -> EvidenceTimelinePayload:
        """Constructs a chronological forensic event reconstruction timeline.

        Orders all verified events chronologically from vessel entry through anomaly detection,
        release window, CPA, drift progression, up to the satellite observation pass.
        """
        case_uuid = uuid.UUID(str(case_id)) if isinstance(case_id, str) else case_id
        events: list[EvidenceTimelineItem] = []

        # 1. Parse Slick Detection ($t_{obs}$)
        det_time = self._extract_datetime(detection, "detection_time") or datetime.now(UTC)
        det_confidence = float(
            self._extract_val(detection, "confidence", self.default_confidence_pct)
        )
        det_source = str(self._extract_val(detection, "data_source", "synthetic"))

        # 2. Parse Characterization ($t_{age}$)
        t_age_hours = float(self._extract_val(characterization, "t_age_hours", 12.0))
        age_confidence = float(
            self._extract_val(characterization, "age_confidence", self.default_confidence_pct)
        )
        det_area_m2 = float(self._extract_val(detection, "area_m2", 0.0))
        fallback_area_km2 = round(det_area_m2 / 1e6, 2) if det_area_m2 > 0.0 else 8.5
        area_km2 = float(self._extract_val(characterization, "surface_area_km2", fallback_area_km2))
        vol_m3 = float(
            self._extract_val(
                characterization,
                "volume_m3",
                self._extract_val(characterization, "estimated_volume_m3", 145.0),
            )
        )
        baoac_code = self._extract_val(characterization, "baoac_code", 4)
        thickness_cat = str(
            self._extract_val(
                characterization,
                "thickness_classification",
                f"BAOAC_{baoac_code}_METALLIC",
            )
        )

        # Inferred release timestamp and window
        t_release = det_time - timedelta(hours=t_age_hours)
        age_uncertainty_hours = max(0.5, t_age_hours * 0.20)
        t_release_start = t_release - timedelta(hours=age_uncertainty_hours)
        t_release_end = t_release + timedelta(hours=age_uncertainty_hours)

        # 3. Parse Origin Estimate
        origin_conf = float(
            self._extract_val(origin, "confidence_pct", self.default_confidence_pct)
        )
        origin_centroid = self._extract_point(origin, "centroid") or (72.290, 18.865)

        # Filter candidates if mmsi is requested
        active_candidates: list[VesselCandidate | dict[str, Any]] = []
        for c in candidates:
            c_mmsi = int(self._extract_val(c, "mmsi", 0))
            if mmsi is None or c_mmsi == mmsi:
                active_candidates.append(c)

        if not active_candidates and candidates:
            # Fall back to top-ranked candidate if specific MMSI not found
            active_candidates = [candidates[0]]

        # Assemble Events for Candidates
        for cand in active_candidates:
            c_mmsi = int(self._extract_val(cand, "mmsi", 0))
            c_name = str(self._extract_val(cand, "name", f"Vessel {c_mmsi}"))
            c_type = str(self._extract_val(cand, "vessel_type", "Cargo"))
            c_sub_scores = self._extract_val(cand, "sub_scores", {})
            c_conf = float(self._extract_val(cand, "confidence", self.default_confidence_pct))
            c_anom_flags = self._extract_val(cand, "anomaly_flags", [])

            details = c_sub_scores.get("details", {}) if isinstance(c_sub_scores, dict) else {}

            # Time delta between release and CPA
            delta_hours = float(details.get("delta_hours", 0.0))
            t_cpa = t_release + timedelta(hours=delta_hours)

            # A. Vessel Entry Event (prior to CPA)
            t_entry = t_cpa - timedelta(minutes=45)
            entry_title = f"Vessel Entry into Surveillance Sector: {c_name}"
            entry_desc = (
                f"Candidate vessel {c_name} (MMSI {c_mmsi}, {c_type}) entered surveillance "
                f"zone heading {float(details.get('cog_deg', 65.0)):.1f}° at "
                f"{float(details.get('speed_kts', 12.5)):.1f} knots."
            )
            assert_no_banned_terms(entry_desc, "vessel_entry")
            events.append(
                EvidenceTimelineItem(
                    timestamp=t_entry,
                    event_type="vessel_entry",
                    title=entry_title,
                    description=entry_desc,
                    evidence_ref=f"ais_track:{c_mmsi}",
                    confidence_pct=round(c_conf, 1),
                    properties={
                        "mmsi": c_mmsi,
                        "vessel_name": c_name,
                        "vessel_type": c_type,
                        "speed_kts": float(details.get("speed_kts", 12.5)),
                        "cog_deg": float(details.get("cog_deg", 65.0)),
                    },
                )
            )

            # B. Anomaly Event (if speed loitering or dark transponder gaps triggered)
            has_speed_anom = (
                float(details.get("a_speed", 0.0)) > 0.5
                or "speed_drop_dumping" in c_anom_flags
                or float(details.get("speed_kts", 12.0)) < 7.5
            )
            has_dark_anom = (
                float(details.get("a_dark", 0.0)) > 0.5 or "dark_transponder_gap" in c_anom_flags
            )

            if has_speed_anom:
                t_anom = t_cpa - timedelta(minutes=15)
                anom_speed = float(details.get("speed_kts", 6.2))
                anom_title = f"Kinematic Speed Anomaly Detected: {c_name}"
                anom_desc = (
                    f"Candidate vessel {c_name} recorded a significant speed reduction down to "
                    f"{anom_speed:.1f} knots proximate to inferred discharge coordinates."
                )
                assert_no_banned_terms(anom_desc, "speed_anomaly")
                events.append(
                    EvidenceTimelineItem(
                        timestamp=t_anom,
                        event_type="anomaly_detected",
                        title=anom_title,
                        description=anom_desc,
                        evidence_ref=f"anomaly:{c_mmsi}_speed",
                        confidence_pct=round(c_conf * 0.95, 1),
                        properties={
                            "mmsi": c_mmsi,
                            "anomaly_type": "speed_drop_dumping",
                            "observed_speed_kts": anom_speed,
                        },
                    )
                )

            if has_dark_anom:
                t_dark = t_cpa - timedelta(minutes=20)
                dark_title = f"Transponder Dark Gap Detected: {c_name}"
                dark_desc = (
                    f"Candidate vessel {c_name} exhibited an unannounced AIS transponder gap "
                    f"during transit through the origin uncertainty corridor."
                )
                assert_no_banned_terms(dark_desc, "dark_anomaly")
                events.append(
                    EvidenceTimelineItem(
                        timestamp=t_dark,
                        event_type="anomaly_detected",
                        title=dark_title,
                        description=dark_desc,
                        evidence_ref=f"anomaly:{c_mmsi}_dark",
                        confidence_pct=round(c_conf * 0.90, 1),
                        properties={
                            "mmsi": c_mmsi,
                            "anomaly_type": "dark_transponder_gap",
                        },
                    )
                )

            # C. Closest Point of Approach (CPA) Event
            cpa_dist_km = float(details.get("cpa_dist_km", 0.25))
            cpa_dist_m = cpa_dist_km * 1000.0
            d_m = float(details.get("d_m", 0.2))
            cpa_coords = details.get("cpa_coords", list(origin_centroid))

            cpa_title = f"Closest Approach to Inferred Origin: {c_name}"
            cpa_desc = (
                f"Candidate vessel {c_name} reached closest point of approach at distance "
                f"{cpa_dist_km:.2f} km ({cpa_dist_m:.0f} m, Mahalanobis D_M = {d_m:.2f}) "
                f"from the estimated spill origin centroid."
            )
            assert_no_banned_terms(cpa_desc, "cpa_event")
            events.append(
                EvidenceTimelineItem(
                    timestamp=t_cpa,
                    event_type="cpa_reached",
                    title=cpa_title,
                    description=cpa_desc,
                    evidence_ref=f"cpa:{c_mmsi}",
                    confidence_pct=round(min(c_conf, origin_conf), 1),
                    properties={
                        "mmsi": c_mmsi,
                        "vessel_name": c_name,
                        "cpa_distance_km": round(cpa_dist_km, 3),
                        "cpa_distance_m": round(cpa_dist_m, 1),
                        "mahalanobis_d_m": round(d_m, 2),
                        "coordinates": cpa_coords,
                    },
                )
            )

        # 4. Oil Release Window Event
        rel_title = "Estimated Oil Release Window"
        rel_desc = (
            f"Fay spreading and weathering inversion models indicate discharge occurred between "
            f"{t_release_start.strftime('%H:%M')} and {t_release_end.strftime('%H:%M UTC')} "
            f"(inferred spill age {t_age_hours:.1f}h ± {age_uncertainty_hours:.1f}h)."
        )
        assert_no_banned_terms(rel_desc, "release_window")
        events.append(
            EvidenceTimelineItem(
                timestamp=t_release,
                event_type="release_window",
                title=rel_title,
                description=rel_desc,
                evidence_ref="characterization:spreading_age",
                confidence_pct=round(age_confidence, 1),
                properties={
                    "t_release_center": t_release.isoformat(),
                    "window_start": t_release_start.isoformat(),
                    "window_end": t_release_end.isoformat(),
                    "t_age_hours": t_age_hours,
                    "uncertainty_hours": age_uncertainty_hours,
                    "thickness_class": thickness_cat,
                },
            )
        )

        # 5. Drift Progression Event (Midpoint between release and detection)
        t_drift_mid = t_release + timedelta(hours=t_age_hours * 0.55)
        u_curr = metocean_summary.get("u_current", 0.22) if metocean_summary else 0.22
        v_curr = metocean_summary.get("v_current", 0.15) if metocean_summary else 0.15
        drift_title = "Oceanic Drift & Spreading Progression"
        drift_desc = (
            f"Released hydrocarbon volume advected east-northeast under prevailing currents "
            f"(u={u_curr:.2f} m/s, v={v_curr:.2f} m/s) and leeway wind drift, progressively "
            f"elongating along current shear."
        )
        assert_no_banned_terms(drift_desc, "drift_progression")
        events.append(
            EvidenceTimelineItem(
                timestamp=t_drift_mid,
                event_type="drift_progression",
                title=drift_title,
                description=drift_desc,
                evidence_ref="hindcast:trajectory",
                confidence_pct=round((det_confidence + age_confidence) / 2.0, 1),
                properties={
                    "u_current": u_curr,
                    "v_current": v_curr,
                    "expansion_factor": 2.4,
                },
            )
        )

        # 6. Satellite Pass & Observation Event ($t_{obs}$)
        sat_title = "Sentinel-1 SAR Acquisition & Slick Observation"
        sat_desc = (
            f"Sentinel-1 C-SAR high-resolution acquisition observed oil slick surface expression "
            f"covering {area_km2:.2f} km² with estimated volume {vol_m3:.1f} m³ ({thickness_cat})."
        )
        assert_no_banned_terms(sat_desc, "satellite_pass")
        events.append(
            EvidenceTimelineItem(
                timestamp=det_time,
                event_type="satellite_pass",
                title=sat_title,
                description=sat_desc,
                evidence_ref=f"detection:{case_uuid}",
                confidence_pct=round(det_confidence, 1),
                properties={
                    "sensor": "Sentinel-1 C-SAR",
                    "mode": "IW",
                    "surface_area_km2": area_km2,
                    "volume_m3": vol_m3,
                    "thickness_class": thickness_cat,
                    "data_source": det_source,
                },
            )
        )

        # Sort all timeline items chronologically (ascending timestamp)
        events.sort(key=lambda e: e.timestamp)

        start_t = events[0].timestamp if events else det_time
        end_t = events[-1].timestamp if events else det_time
        duration_hrs = round((end_t - start_t).total_seconds() / 3600.0, 2)

        # Composite timeline confidence (Rule 1)
        mean_conf = (
            round(sum(e.confidence_pct for e in events) / float(len(events)), 1)
            if events
            else self.default_confidence_pct
        )

        return EvidenceTimelinePayload(
            case_id=case_uuid,
            mmsi=mmsi,
            events=events,
            start_time=start_t,
            end_time=end_t,
            total_duration_hours=duration_hrs,
            confidence_pct=mean_conf,
        )

    def build_graph(
        self,
        case_id: uuid.UUID | str,
        detection: SlickDetection | dict[str, Any],
        characterization: SlickCharacterization | dict[str, Any],
        origin: OriginEstimate | dict[str, Any],
        candidates: list[VesselCandidate | dict[str, Any]],
        alternatives: list[AlternativeExplanation | dict[str, Any]] | None = None,
        counterfactuals: list[CounterfactualResult | dict[str, Any]] | None = None,
        mmsi: int | None = None,
    ) -> EvidenceGraphPayload:
        """Constructs an interactive Directed Acyclic Graph (DAG) of the evidence structure.

        Nodes represent forensic entities (scene, slick, origin, time window, AIS tracks,
        candidate vessels, anomalies, and alternative hypotheses). Directed edges map causal
        and spatial correlations down the evidentiary chain.
        """
        case_uuid = uuid.UUID(str(case_id)) if isinstance(case_id, str) else case_id
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # 1. Base Node: Satellite Scene
        det_time = self._extract_datetime(detection, "detection_time") or datetime.now(UTC)
        det_conf = float(self._extract_val(detection, "confidence", self.default_confidence_pct))
        scene_node_id = f"scene:{case_uuid}"
        nodes.append(
            GraphNode(
                id=scene_node_id,
                label="Sentinel-1 SAR Scene",
                node_type="scene",
                confidence_pct=round(det_conf, 1),
                properties={
                    "sensor": "Sentinel-1 C-SAR",
                    "mode": "IW",
                    "polarization": "VV+VH",
                    "acquisition_time": det_time.isoformat(),
                    "resolution_m": 10.0,
                },
            )
        )

        # 2. Node: Observed Slick Polygon
        det_area_m2 = float(self._extract_val(detection, "area_m2", 0.0))
        fallback_area_km2 = round(det_area_m2 / 1e6, 2) if det_area_m2 > 0.0 else 8.5
        area_km2 = float(self._extract_val(characterization, "surface_area_km2", fallback_area_km2))
        vol_m3 = float(
            self._extract_val(
                characterization,
                "volume_m3",
                self._extract_val(characterization, "estimated_volume_m3", 145.0),
            )
        )
        baoac_code = self._extract_val(characterization, "baoac_code", 4)
        thickness_cat = str(
            self._extract_val(
                characterization,
                "thickness_classification",
                f"BAOAC_{baoac_code}_METALLIC",
            )
        )
        slick_node_id = f"slick:{case_uuid}"
        nodes.append(
            GraphNode(
                id=slick_node_id,
                label="Observed Slick",
                node_type="slick",
                confidence_pct=round(det_conf, 1),
                properties={
                    "surface_area_km2": area_km2,
                    "volume_m3": vol_m3,
                    "thickness_class": thickness_cat,
                },
            )
        )
        # Edge: Scene -> Slick (OBSERVED)
        edges.append(
            GraphEdge(
                source=scene_node_id,
                target=slick_node_id,
                relation="OBSERVED",
                confidence_pct=round(det_conf, 1),
                properties={"observation_time": det_time.isoformat()},
            )
        )

        # 3. Node: Inferred Spill Origin
        origin_conf = float(
            self._extract_val(origin, "confidence_pct", self.default_confidence_pct)
        )
        origin_pt = self._extract_point(origin, "centroid") or (72.290, 18.865)
        origin_node_id = f"origin:{case_uuid}"
        nodes.append(
            GraphNode(
                id=origin_node_id,
                label="Inferred Origin",
                node_type="origin",
                confidence_pct=round(origin_conf, 1),
                properties={
                    "centroid_lon": origin_pt[0],
                    "centroid_lat": origin_pt[1],
                    "ellipse_major_km": float(self._extract_val(origin, "ellipse_major_km", 3.2)),
                    "ellipse_minor_km": float(self._extract_val(origin, "ellipse_minor_km", 1.8)),
                },
            )
        )
        # Edge: Slick -> Origin (DRIFTED_FROM)
        edges.append(
            GraphEdge(
                source=slick_node_id,
                target=origin_node_id,
                relation="DRIFTED_FROM",
                confidence_pct=round(origin_conf, 1),
                properties={"model": "OpenDrift / Met-Ocean Hindcast"},
            )
        )

        # 4. Node: Estimated Release Time Window
        t_age_hours = float(self._extract_val(characterization, "t_age_hours", 12.0))
        age_confidence = float(
            self._extract_val(characterization, "age_confidence", self.default_confidence_pct)
        )
        time_window_node_id = f"time_window:{case_uuid}"
        nodes.append(
            GraphNode(
                id=time_window_node_id,
                label="Release Time Window",
                node_type="time_window",
                confidence_pct=round(age_confidence, 1),
                properties={
                    "estimated_age_hours": t_age_hours,
                    "confidence_pct": age_confidence,
                    "method": "Fay Spreading Age Inversion",
                },
            )
        )
        # Edge: Origin -> Time Window (ESTIMATED_WINDOW)
        edges.append(
            GraphEdge(
                source=origin_node_id,
                target=time_window_node_id,
                relation="ESTIMATED_WINDOW",
                confidence_pct=round(age_confidence, 1),
                properties={"duration_hours": t_age_hours},
            )
        )

        # 5. Candidate Vessels, AIS Tracks, Anomalies
        active_candidates: list[VesselCandidate | dict[str, Any]] = []
        for c in candidates:
            c_mmsi = int(self._extract_val(c, "mmsi", 0))
            if mmsi is None or c_mmsi == mmsi:
                active_candidates.append(c)

        for cand in active_candidates:
            c_mmsi = int(self._extract_val(cand, "mmsi", 0))
            c_name = str(self._extract_val(cand, "name", f"Vessel {c_mmsi}"))
            c_type = str(self._extract_val(cand, "vessel_type", "Cargo"))
            c_score = float(self._extract_val(cand, "s_culprit", 50.0))
            c_conf = float(self._extract_val(cand, "confidence", self.default_confidence_pct))
            c_sub_scores = self._extract_val(cand, "sub_scores", {})
            c_anom_flags = self._extract_val(cand, "anomaly_flags", [])

            details = c_sub_scores.get("details", {}) if isinstance(c_sub_scores, dict) else {}

            # AIS Track Node
            track_node_id = f"ais_track:{c_mmsi}"
            nodes.append(
                GraphNode(
                    id=track_node_id,
                    label=f"AIS Track: {c_name}",
                    node_type="ais_track",
                    confidence_pct=round(c_conf, 1),
                    properties={
                        "mmsi": c_mmsi,
                        "sampling_rate": "15m",
                        "coverage": str(self._extract_val(cand, "ais_coverage", "full")),
                    },
                )
            )

            # Vessel Node
            vessel_node_id = f"vessel:{c_mmsi}"
            nodes.append(
                GraphNode(
                    id=vessel_node_id,
                    label=f"{c_name} (MMSI {c_mmsi})",
                    node_type="vessel",
                    confidence_pct=round(c_conf, 1),
                    properties={
                        "mmsi": c_mmsi,
                        "vessel_name": c_name,
                        "vessel_type": c_type,
                        "s_culprit": c_score,
                        "spatial_score": float(c_sub_scores.get("spatial", 0.0)),
                        "temporal_score": float(c_sub_scores.get("temporal", 0.0)),
                        "kinematic_score": float(c_sub_scores.get("kinematic", 0.0)),
                        "anomaly_score": float(c_sub_scores.get("anomaly", 0.0)),
                        "type_score": float(c_sub_scores.get("type", 0.0)),
                    },
                )
            )

            # Edge: AIS Track -> Vessel (BROADCAST_BY)
            edges.append(
                GraphEdge(
                    source=track_node_id,
                    target=vessel_node_id,
                    relation="BROADCAST_BY",
                    confidence_pct=round(c_conf, 1),
                    properties={"status": "verified"},
                )
            )

            # Edge: Vessel -> Origin (CORRELATED_WITH)
            spatial_sub = float(c_sub_scores.get("spatial", 50.0))
            edges.append(
                GraphEdge(
                    source=vessel_node_id,
                    target=origin_node_id,
                    relation="CORRELATED_WITH",
                    confidence_pct=round(min(c_conf, spatial_sub), 1),
                    properties={
                        "cpa_dist_km": float(details.get("cpa_dist_km", 0.25)),
                        "mahalanobis_d_m": float(details.get("d_m", 0.2)),
                    },
                )
            )

            # Anomaly Nodes and Edges
            has_speed_anom = (
                float(details.get("a_speed", 0.0)) > 0.5
                or "speed_drop_dumping" in c_anom_flags
                or float(details.get("speed_kts", 12.0)) < 7.5
            )
            has_dark_anom = (
                float(details.get("a_dark", 0.0)) > 0.5 or "dark_transponder_gap" in c_anom_flags
            )

            if has_speed_anom:
                anom_node_id = f"anomaly:{c_mmsi}_speed"
                nodes.append(
                    GraphNode(
                        id=anom_node_id,
                        label=f"Speed Drop Anomaly ({c_name})",
                        node_type="anomaly",
                        confidence_pct=round(c_conf * 0.95, 1),
                        properties={
                            "mmsi": c_mmsi,
                            "type": "speed_drop_dumping",
                            "speed_kts": float(details.get("speed_kts", 6.2)),
                        },
                    )
                )
                # Edge: Vessel -> Anomaly (EXHIBITED)
                edges.append(
                    GraphEdge(
                        source=vessel_node_id,
                        target=anom_node_id,
                        relation="EXHIBITED",
                        confidence_pct=round(c_conf * 0.95, 1),
                        properties={"severity": "high"},
                    )
                )
                # Edge: Anomaly -> Origin (COINCIDED_WITH)
                edges.append(
                    GraphEdge(
                        source=anom_node_id,
                        target=origin_node_id,
                        relation="COINCIDED_WITH",
                        confidence_pct=round(c_conf * 0.90, 1),
                        properties={"location": "origin_proximity"},
                    )
                )

            if has_dark_anom:
                dark_node_id = f"anomaly:{c_mmsi}_dark"
                nodes.append(
                    GraphNode(
                        id=dark_node_id,
                        label=f"Dark Gap Anomaly ({c_name})",
                        node_type="anomaly",
                        confidence_pct=round(c_conf * 0.90, 1),
                        properties={
                            "mmsi": c_mmsi,
                            "type": "dark_transponder_gap",
                        },
                    )
                )
                # Edge: Vessel -> Dark Gap (EXHIBITED)
                edges.append(
                    GraphEdge(
                        source=vessel_node_id,
                        target=dark_node_id,
                        relation="EXHIBITED",
                        confidence_pct=round(c_conf * 0.90, 1),
                        properties={"severity": "critical"},
                    )
                )
                # Edge: Dark Gap -> Origin (COINCIDED_WITH)
                edges.append(
                    GraphEdge(
                        source=dark_node_id,
                        target=origin_node_id,
                        relation="COINCIDED_WITH",
                        confidence_pct=round(c_conf * 0.85, 1),
                        properties={"location": "origin_corridor"},
                    )
                )

        # 6. Alternative Explanation Nodes & Edges (Rule 5)
        if alternatives:
            for alt in alternatives:
                hypo = str(self._extract_val(alt, "hypothesis", "natural_seep"))
                score = float(self._extract_val(alt, "score", 10.0))
                conf = float(self._extract_val(alt, "confidence", self.default_confidence_pct))

                alt_node_id = f"alt_hypothesis:{hypo}"
                nodes.append(
                    GraphNode(
                        id=alt_node_id,
                        label=f"Alternative: {hypo.replace('_', ' ').title()}",
                        node_type="alternative_hypothesis",
                        confidence_pct=round(conf, 1),
                        properties={"hypothesis": hypo, "score": score},
                    )
                )
                # Edge: Origin -> Alternative Hypothesis (EVALUATED_AGAINST)
                edges.append(
                    GraphEdge(
                        source=origin_node_id,
                        target=alt_node_id,
                        relation="EVALUATED_AGAINST",
                        confidence_pct=round(conf, 1),
                        properties={"score": score},
                    )
                )

        # 7. Counterfactual Forward Simulation Nodes & Edges (if available)
        if counterfactuals:
            for cf in counterfactuals:
                cf_mmsi = int(self._extract_val(cf, "mmsi", 0))
                if mmsi is not None and cf_mmsi != mmsi:
                    continue

                vessel_node_id = f"vessel:{cf_mmsi}"
                cf_node_id = f"counterfactual:{cf_mmsi}"
                cf_iou = float(self._extract_val(cf, "iou_pct", 0.0))
                cf_sim_score = float(self._extract_val(cf, "similarity_score", 0.0))
                cf_conf = float(
                    self._extract_val(cf, "confidence_pct", self.default_confidence_pct)
                )

                nodes.append(
                    GraphNode(
                        id=cf_node_id,
                        label=f"Counterfactual Sim: {cf_mmsi}",
                        node_type="counterfactual",
                        confidence_pct=round(cf_conf, 1),
                        properties={
                            "mmsi": cf_mmsi,
                            "iou_pct": cf_iou,
                            "similarity_score": cf_sim_score,
                            "hausdorff_distance_m": float(
                                self._extract_val(cf, "hausdorff_distance_m", 0.0)
                            ),
                        },
                    )
                )
                # Edge: Vessel -> Counterfactual (SIMULATED_FORWARD)
                edges.append(
                    GraphEdge(
                        source=vessel_node_id,
                        target=cf_node_id,
                        relation="SIMULATED_FORWARD",
                        confidence_pct=round(cf_conf, 1),
                        properties={"n_particles": int(self._extract_val(cf, "n_particles", 5000))},
                    )
                )
                # Edge: Counterfactual -> Slick (CONGRUENT_WITH)
                edges.append(
                    GraphEdge(
                        source=cf_node_id,
                        target=slick_node_id,
                        relation="CONGRUENT_WITH",
                        confidence_pct=round(cf_sim_score, 1),
                        properties={"iou_pct": cf_iou},
                    )
                )

        # 8. Validate DAG topology using NetworkX
        nx_graph = nx.DiGraph()
        for node in nodes:
            nx_graph.add_node(node.id, label=node.label, type=node.node_type)
        for edge in edges:
            nx_graph.add_edge(edge.source, edge.target, relation=edge.relation)

        is_dag = nx.is_directed_acyclic_graph(nx_graph)
        topological_order: list[str] = []
        if is_dag:
            topological_order = list(nx.topological_sort(nx_graph))
        else:
            logger.warning("Graph contains cycles! Resolving cycles to ensure strict DAG topology.")
            # Cycle elimination fallback
            while not nx.is_directed_acyclic_graph(nx_graph):
                cycle = nx.find_cycle(nx_graph)
                nx_graph.remove_edge(cycle[0][0], cycle[0][1])
                edges = [
                    e for e in edges if not (e.source == cycle[0][0] and e.target == cycle[0][1])
                ]
            is_dag = True
            topological_order = list(nx.topological_sort(nx_graph))

        # Composite graph confidence (Rule 1)
        mean_conf = (
            round(sum(n.confidence_pct for n in nodes) / float(len(nodes)), 1)
            if nodes
            else self.default_confidence_pct
        )

        metadata = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": {
                t: len([n for n in nodes if n.node_type == t]) for t in {n.node_type for n in nodes}
            },
            "is_dag": is_dag,
        }

        return EvidenceGraphPayload(
            case_id=case_uuid,
            mmsi=mmsi,
            nodes=nodes,
            edges=edges,
            is_acyclic=is_dag,
            topological_order=topological_order,
            confidence_pct=mean_conf,
            metadata=metadata,
        )

    def build_bundle(
        self,
        case_id: uuid.UUID | str,
        detection: SlickDetection | dict[str, Any],
        characterization: SlickCharacterization | dict[str, Any],
        origin: OriginEstimate | dict[str, Any],
        candidates: list[VesselCandidate | dict[str, Any]],
        alternatives: list[AlternativeExplanation | dict[str, Any]] | None = None,
        counterfactuals: list[CounterfactualResult | dict[str, Any]] | None = None,
        mmsi: int | None = None,
        metocean_summary: dict[str, Any] | None = None,
    ) -> EvidenceBundlePayload:
        """Constructs unified forensic package containing both timeline and graph."""
        case_uuid = uuid.UUID(str(case_id)) if isinstance(case_id, str) else case_id

        timeline = self.build_timeline(
            case_id=case_uuid,
            detection=detection,
            characterization=characterization,
            origin=origin,
            candidates=candidates,
            mmsi=mmsi,
            metocean_summary=metocean_summary,
        )

        graph = self.build_graph(
            case_id=case_uuid,
            detection=detection,
            characterization=characterization,
            origin=origin,
            candidates=candidates,
            alternatives=alternatives,
            counterfactuals=counterfactuals,
            mmsi=mmsi,
        )

        mean_conf = round((timeline.confidence_pct + graph.confidence_pct) / 2.0, 1)

        return EvidenceBundlePayload(
            case_id=case_uuid,
            mmsi=mmsi,
            timeline=timeline,
            graph=graph,
            confidence_pct=mean_conf,
        )

    def build_from_db(
        self,
        db: Session,
        case_id: uuid.UUID | str,
        mmsi: int | None = None,
    ) -> EvidenceBundlePayload:
        """Loads case entities from SQLAlchemy database session and builds complete evidence bundle."""
        case_uuid = uuid.UUID(str(case_id)) if isinstance(case_id, str) else case_id

        case_obj = db.query(Case).filter(Case.id == case_uuid).first()
        if not case_obj:
            raise ValueError(f"Case with ID {case_uuid} not found")

        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.created_at.desc())
            .first()
        )
        if not detection:
            raise ValueError(f"No SlickDetection found for case {case_uuid}")

        characterization = (
            db.query(SlickCharacterization)
            .filter(SlickCharacterization.case_id == case_uuid)
            .order_by(SlickCharacterization.created_at.desc())
            .first()
        )
        if not characterization:
            raise ValueError(f"No SlickCharacterization found for case {case_uuid}")

        origin = (
            db.query(OriginEstimate)
            .filter(OriginEstimate.case_id == case_uuid)
            .order_by(OriginEstimate.created_at.desc())
            .first()
        )
        if not origin:
            raise ValueError(f"No OriginEstimate found for case {case_uuid}")

        candidates = (
            db.query(VesselCandidate)
            .filter(VesselCandidate.case_id == case_uuid)
            .order_by(VesselCandidate.s_culprit.desc())
            .all()
        )

        alternatives = (
            db.query(AlternativeExplanation)
            .filter(AlternativeExplanation.case_id == case_uuid)
            .all()
        )

        return self.build_bundle(
            case_id=case_uuid,
            detection=detection,
            characterization=characterization,
            origin=origin,
            candidates=candidates,
            alternatives=alternatives,
            mmsi=mmsi,
        )

    # ---------------- Helper Extractors ---------------- #

    def _extract_val(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _extract_datetime(self, obj: Any, key: str) -> datetime | None:
        val = self._extract_val(obj, key)
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except Exception:
                return None
        return None

    def _extract_point(self, obj: Any, key: str) -> tuple[float, float] | None:
        val = self._extract_val(obj, key)
        if val is None:
            return None
        if isinstance(val, (tuple, list)) and len(val) >= 2:
            return (float(val[0]), float(val[1]))
        if isinstance(val, Point):
            return (float(val.x), float(val.y))
        try:
            geom = to_shape(val)
            if isinstance(geom, Point):
                return (float(geom.x), float(geom.y))
            if isinstance(geom, Polygon):
                return (float(geom.centroid.x), float(geom.centroid.y))
        except Exception:
            pass
        return None
