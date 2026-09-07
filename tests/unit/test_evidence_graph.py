"""AEGIS-Marine: Unit tests for Evidence Timeline & Node-Edge Graph Builders (TASK-032).

Verifies Feature 8 (Evidence Timeline) and Feature 11 / P5 (Interactive Evidence Graph):
- Chronological ordering of events.
- Verification of 6 forensic event stages (satellite pass, release window, vessel entry, anomaly trigger, CPA reached, drift progression).
- Directed Acyclic Graph (DAG) topology, node/edge structure, and topological sorting.
- Multi-candidate representation and MMSI filtering.
- Integration of Counterfactual Forward Simulation nodes and edges.
- Full compliance with:
  - Rule 1: Paired confidence score in [0.0, 100.0] on all items, nodes, edges, and payloads.
  - Rule 6: Strictly zero occurrences of banned determination terms.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import networkx as nx
from geoalchemy2.shape import from_shape
from scripts.lint_banned_terms import check_content
from shapely.geometry import Point, Polygon
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    AlternativeExplanation,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import (
    CounterfactualResult,
    EvidenceBundlePayload,
    EvidenceGraphPayload,
    EvidenceTimelinePayload,
)
from backend.services.explainability.evidence_graph import (
    EvidenceGraphBuilder,
    assert_no_banned_terms,
)


class TestEvidenceGraphBuilder(unittest.TestCase):
    """Unit test suite for Evidence Timeline and Interactive Evidence Graph."""

    def setUp(self) -> None:
        self.builder = EvidenceGraphBuilder(default_confidence_pct=88.0)
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

        self.t_obs = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)
        self.t_release = datetime(2026, 9, 6, 18, 0, 0, tzinfo=UTC)  # 12h prior

        # Detection fixture
        self.detection_dict = {
            "id": uuid.uuid4(),
            "case_id": self.case_uuid,
            "detection_time": self.t_obs,
            "confidence": 89.5,
            "data_source": "synthetic",
            "centroid": (72.518, 18.946),
        }

        # Characterization fixture
        self.char_dict = {
            "id": uuid.uuid4(),
            "case_id": self.case_uuid,
            "t_age_hours": 12.0,
            "age_confidence": 86.0,
            "surface_area_km2": 9.4,
            "volume_m3": 165.0,
            "thickness_classification": "BAOAC_4_CONTINUOUS_TRUE_COLOR",
            "slick_orientation_deg": 65.0,
        }

        # Origin Estimate fixture
        self.origin_dict = {
            "id": uuid.uuid4(),
            "case_id": self.case_uuid,
            "centroid": (72.290, 18.865),
            "confidence_pct": 91.0,
            "ellipse_major_km": 3.4,
            "ellipse_minor_km": 1.9,
            "origin_area_km2": 20.3,
        }

        # Benchmark suspect: Vessel A (PACIFIC PEARL, MMSI 419000101)
        self.vessel_a = {
            "id": uuid.uuid4(),
            "case_id": self.case_uuid,
            "mmsi": 419000101,
            "name": "PACIFIC PEARL",
            "vessel_type": "Tanker",
            "flag_state": "Panama",
            "s_culprit": 88.5,
            "confidence": 89.0,
            "ais_coverage": "full",
            "anomaly_flags": ["speed_drop_dumping"],
            "sub_scores": {
                "spatial": 98.0,
                "temporal": 94.0,
                "kinematic": 91.0,
                "anomaly": 85.0,
                "type": 100.0,
                "details": {
                    "d_m": 0.18,
                    "cpa_dist_km": 0.22,
                    "delta_hours": 0.08,
                    "speed_kts": 6.2,
                    "cog_deg": 68.0,
                    "a_speed": 1.0,
                    "a_dark": 0.0,
                    "cpa_coords": [72.291, 18.866],
                },
            },
        }

        # Innocent comparison vessel: Vessel B (MAERSK TAIPEI, MMSI 419000102)
        self.vessel_b = {
            "id": uuid.uuid4(),
            "case_id": self.case_uuid,
            "mmsi": 419000102,
            "name": "MAERSK TAIPEI",
            "vessel_type": "Container",
            "flag_state": "Singapore",
            "s_culprit": 22.0,
            "confidence": 82.0,
            "ais_coverage": "full",
            "anomaly_flags": [],
            "sub_scores": {
                "spatial": 18.0,
                "temporal": 25.0,
                "kinematic": 30.0,
                "anomaly": 10.0,
                "type": 40.0,
                "details": {
                    "d_m": 4.5,
                    "cpa_dist_km": 15.8,
                    "delta_hours": 3.2,
                    "speed_kts": 16.5,
                    "cog_deg": 190.0,
                    "a_speed": 0.0,
                    "a_dark": 0.0,
                    "cpa_coords": [72.450, 18.650],
                },
            },
        }

        # Alternative explanations
        self.alternatives = [
            {
                "id": uuid.uuid4(),
                "case_id": self.case_uuid,
                "hypothesis": "natural_seep",
                "score": 12.5,
                "confidence": 87.0,
                "evidence": {"nearest_seep_name": "Bombay High Shelf Alpha", "distance_km": 18.2},
            },
            {
                "id": uuid.uuid4(),
                "case_id": self.case_uuid,
                "hypothesis": "imaging_artifact",
                "score": 5.0,
                "confidence": 92.0,
                "evidence": {"lookalike_risk": 0.05},
            },
        ]

    def test_timeline_chronological_ordering(self) -> None:
        """Verify timeline events are strictly ordered by timestamp in ascending order."""
        timeline: EvidenceTimelinePayload = self.builder.build_timeline(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a],
            mmsi=419000101,
        )

        self.assertEqual(timeline.case_id, self.case_uuid)
        self.assertEqual(timeline.mmsi, 419000101)
        self.assertGreater(len(timeline.events), 0)

        # Assert strict ascending chronology
        for i in range(len(timeline.events) - 1):
            t_curr = timeline.events[i].timestamp
            t_next = timeline.events[i + 1].timestamp
            self.assertLessEqual(
                t_curr,
                t_next,
                f"Event {timeline.events[i].title} ({t_curr}) occurs after {timeline.events[i + 1].title} ({t_next})",
            )

        # Assert duration
        expected_duration = round(
            (timeline.events[-1].timestamp - timeline.events[0].timestamp).total_seconds() / 3600.0,
            2,
        )
        self.assertEqual(timeline.total_duration_hours, expected_duration)

    def test_timeline_event_stages(self) -> None:
        """Verify all 6 forensic event stages are represented in the timeline."""
        timeline: EvidenceTimelinePayload = self.builder.build_timeline(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a],
            mmsi=419000101,
        )

        event_types = {e.event_type for e in timeline.events}
        expected_stages = {
            "vessel_entry",
            "anomaly_detected",
            "cpa_reached",
            "release_window",
            "drift_progression",
            "satellite_pass",
        }

        self.assertTrue(
            expected_stages.issubset(event_types),
            f"Missing stages: {expected_stages - event_types}",
        )

        # Verify CPA details
        cpa_events = [e for e in timeline.events if e.event_type == "cpa_reached"]
        self.assertEqual(len(cpa_events), 1)
        cpa = cpa_events[0]
        self.assertIn("cpa_distance_km", cpa.properties)
        self.assertLess(cpa.properties["cpa_distance_km"], 1.0)

        # Verify Satellite Pass details
        sat_events = [e for e in timeline.events if e.event_type == "satellite_pass"]
        self.assertEqual(len(sat_events), 1)
        sat = sat_events[0]
        self.assertIn("surface_area_km2", sat.properties)
        self.assertEqual(sat.properties["surface_area_km2"], 9.4)

    def test_graph_topology_and_acyclic_structure(self) -> None:
        """Verify graph contains all node types, directed edges, and is strictly a DAG."""
        graph: EvidenceGraphPayload = self.builder.build_graph(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a],
            alternatives=self.alternatives,
            mmsi=419000101,
        )

        self.assertEqual(graph.case_id, self.case_uuid)
        self.assertTrue(graph.is_acyclic, "Evidence graph must be a Directed Acyclic Graph")

        node_types = {n.node_type for n in graph.nodes}
        expected_node_types = {
            "scene",
            "slick",
            "origin",
            "time_window",
            "ais_track",
            "vessel",
            "anomaly",
            "alternative_hypothesis",
        }
        self.assertTrue(
            expected_node_types.issubset(node_types),
            f"Missing node types: {expected_node_types - node_types}",
        )

        # Verify Edge Relations
        edge_relations = {e.relation for e in graph.edges}
        expected_relations = {
            "OBSERVED",
            "DRIFTED_FROM",
            "ESTIMATED_WINDOW",
            "BROADCAST_BY",
            "CORRELATED_WITH",
            "EXHIBITED",
            "COINCIDED_WITH",
            "EVALUATED_AGAINST",
        }
        self.assertTrue(
            expected_relations.issubset(edge_relations),
            f"Missing edge relations: {expected_relations - edge_relations}",
        )

        # Verify Topological Sort with NetworkX
        nx_g = nx.DiGraph()
        for n in graph.nodes:
            nx_g.add_node(n.id)
        for e in graph.edges:
            nx_g.add_edge(e.source, e.target)

        self.assertTrue(nx.is_directed_acyclic_graph(nx_g))
        self.assertGreater(len(graph.topological_order), 0)

        # Assert scene comes before slick, slick before origin, origin before time_window
        idx_scene = graph.topological_order.index(f"scene:{self.case_uuid}")
        idx_slick = graph.topological_order.index(f"slick:{self.case_uuid}")
        idx_origin = graph.topological_order.index(f"origin:{self.case_uuid}")
        idx_window = graph.topological_order.index(f"time_window:{self.case_uuid}")

        self.assertLess(idx_scene, idx_slick)
        self.assertLess(idx_slick, idx_origin)
        self.assertLess(idx_origin, idx_window)

    def test_graph_with_counterfactual_simulation(self) -> None:
        """Verify inclusion of Counterfactual Forward Simulation node and edges."""
        mock_cf = CounterfactualResult(
            case_id=self.case_uuid,
            mmsi=419000101,
            vessel_name="PACIFIC PEARL",
            seed_position=(72.290, 18.865),
            t_release=self.t_release,
            t_obs=self.t_obs,
            duration_hours=12.0,
            n_particles=2000,
            iou_pct=28.8,
            hausdorff_distance_m=2650.0,
            centroid_distance_m=49.0,
            similarity_score=49.2,
            simulated_polygon_geojson={
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            },
            simulated_centroid=(72.518, 18.946),
            observed_centroid=(72.518, 18.946),
            snapshots=[],
            confidence_pct=88.5,
            rationale="Simulated particle cloud displays high spatial overlap.",
        )

        graph: EvidenceGraphPayload = self.builder.build_graph(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a],
            alternatives=self.alternatives,
            counterfactuals=[mock_cf],
            mmsi=419000101,
        )

        cf_nodes = [n for n in graph.nodes if n.node_type == "counterfactual"]
        self.assertEqual(len(cf_nodes), 1)
        self.assertEqual(cf_nodes[0].properties["iou_pct"], 28.8)

        cf_edges = [e for e in graph.edges if e.relation in {"SIMULATED_FORWARD", "CONGRUENT_WITH"}]
        self.assertEqual(len(cf_edges), 2)
        self.assertTrue(graph.is_acyclic)

    def test_graph_multi_candidate_and_filter(self) -> None:
        """Verify multi-candidate graph structure and candidate MMSI filtering."""
        # Unfiltered: contains both vessels
        bundle_all = self.builder.build_bundle(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a, self.vessel_b],
            alternatives=self.alternatives,
        )

        vessel_nodes = [n for n in bundle_all.graph.nodes if n.node_type == "vessel"]
        self.assertEqual(len(vessel_nodes), 2)

        # Filtered to Vessel A only
        bundle_filtered = self.builder.build_bundle(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a, self.vessel_b],
            alternatives=self.alternatives,
            mmsi=419000101,
        )

        vessel_filtered_nodes = [n for n in bundle_filtered.graph.nodes if n.node_type == "vessel"]
        self.assertEqual(len(vessel_filtered_nodes), 1)
        self.assertEqual(vessel_filtered_nodes[0].id, "vessel:419000101")

    def test_rule_1_mandatory_paired_confidence(self) -> None:
        """Rule 1: Verify all timeline items, nodes, edges, and payloads contain valid confidence."""
        bundle: EvidenceBundlePayload = self.builder.build_bundle(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a, self.vessel_b],
            alternatives=self.alternatives,
        )

        # Payload confidence
        self.assertGreaterEqual(bundle.confidence_pct, 0.0)
        self.assertLessEqual(bundle.confidence_pct, 100.0)
        self.assertGreaterEqual(bundle.timeline.confidence_pct, 0.0)
        self.assertLessEqual(bundle.timeline.confidence_pct, 100.0)
        self.assertGreaterEqual(bundle.graph.confidence_pct, 0.0)
        self.assertLessEqual(bundle.graph.confidence_pct, 100.0)

        # All timeline items
        for item in bundle.timeline.events:
            self.assertGreaterEqual(item.confidence_pct, 0.0)
            self.assertLessEqual(item.confidence_pct, 100.0)

        # All graph nodes
        for node in bundle.graph.nodes:
            self.assertGreaterEqual(node.confidence_pct, 0.0)
            self.assertLessEqual(node.confidence_pct, 100.0)

        # All graph edges
        for edge in bundle.graph.edges:
            self.assertGreaterEqual(edge.confidence_pct, 0.0)
            self.assertLessEqual(edge.confidence_pct, 100.0)

    def test_rule_6_zero_banned_terms(self) -> None:
        """Rule 6: Verify strictly zero occurrences of banned terms across all copy."""
        dummy_path = Path("test_evidence_graph.py")

        bundle: EvidenceBundlePayload = self.builder.build_bundle(
            case_id=self.case_id,
            detection=self.detection_dict,
            characterization=self.char_dict,
            origin=self.origin_dict,
            candidates=[self.vessel_a, self.vessel_b],
            alternatives=self.alternatives,
        )

        for event in bundle.timeline.events:
            text = f"{event.title} {event.description}"
            violations = check_content(text, dummy_path)
            self.assertEqual(
                len(violations),
                0,
                f"Banned term violation in timeline event: {[v.rule_name for v in violations]}",
            )
            assert_no_banned_terms(text, f"timeline_{event.event_type}")

        for node in bundle.graph.nodes:
            text = f"{node.label}"
            violations = check_content(text, dummy_path)
            self.assertEqual(
                len(violations),
                0,
                f"Banned term violation in node label: {[v.rule_name for v in violations]}",
            )
            assert_no_banned_terms(text, f"node_{node.id}")

    def test_build_from_db_session(self) -> None:
        """Verify build_from_db loading case, candidates, and detection entities from database."""
        mock_db = MagicMock(spec=Session)

        mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.SCORING,
            created_by="analyst_test",
        )

        mock_poly = Polygon([(72.50, 18.93), (72.53, 18.93), (72.53, 18.96), (72.50, 18.96)])
        mock_det = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(mock_poly, srid=4326),
            centroid=from_shape(Point(72.518, 18.946), srid=4326),
            area_m2=9.4 * 1e6,
            confidence=89.0,
            sensor="Sentinel-1 SAR IW",
            detection_time=self.t_obs,
            data_source=DataSource.SYNTHETIC,
        )

        mock_char = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=12500.0,
            principal_axis_deg=65.0,
            baoac_code=4,
            estimated_volume_m3=165.0,
            t_age_hours=12.0,
            age_confidence=86.0,
        )

        mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(Point(72.290, 18.865), srid=4326),
            covariance_matrix={"sigma_xx": 1.2, "sigma_yy": 0.8, "sigma_xy": 0.3},
            time_window_start=self.t_release - timedelta(hours=1),
            time_window_end=self.t_release + timedelta(hours=1),
            confidence_pct=91.0,
            region_area_km2=20.3,
        )

        mock_cand = VesselCandidate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            mmsi=419000101,
            name="PACIFIC PEARL",
            vessel_type="Tanker",
            s_culprit=88.5,
            confidence=89.0,
            sub_scores=self.vessel_a["sub_scores"],
            anomaly_flags=self.vessel_a["anomaly_flags"],
            ais_coverage=AISCoverage.FULL,
        )

        mock_alt = AlternativeExplanation(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            hypothesis="natural_seep",
            score=12.5,
            confidence=87.0,
            evidence={"nearest_seep_name": "Bombay High Shelf Alpha"},
        )

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = mock_case
            elif model == VesselCandidate:
                q.filter.return_value.order_by.return_value.all.return_value = [mock_cand]
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = mock_det
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = mock_char
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = mock_origin
            elif model == AlternativeExplanation:
                q.filter.return_value.all.return_value = [mock_alt]
            return q

        mock_db.query.side_effect = mock_query

        bundle = self.builder.build_from_db(
            db=mock_db,
            case_id=self.case_id,
            mmsi=419000101,
        )

        self.assertEqual(bundle.case_id, self.case_uuid)
        self.assertEqual(bundle.mmsi, 419000101)
        self.assertGreater(len(bundle.timeline.events), 0)
        self.assertGreater(len(bundle.graph.nodes), 0)
        self.assertTrue(bundle.graph.is_acyclic)


if __name__ == "__main__":
    unittest.main()
