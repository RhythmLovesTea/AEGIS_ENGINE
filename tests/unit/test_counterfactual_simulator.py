"""AEGIS-Marine: Unit tests for Counterfactual Forward Simulation Engine (TASK-031).

Tests conform to:
- PRD Section 11 & Architecture Section 4.5 (Feature 2, D2)
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0]
  - Rule 4: Data source identification and explicit coverage tracking
  - Rule 6: Strictly zero occurrences of banned terms verified via check_content
"""

import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import shapely.affinity
import shapely.geometry
from geoalchemy2.shape import from_shape
from scripts.lint_banned_terms import check_content
from shapely.geometry import Point
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.services.data_adapters.metocean_adapter import (
    generate_synthetic_metocean_dataset,
)
from backend.services.explainability.counterfactual_simulator import (
    CounterfactualSimulator,
    assert_no_banned_terms,
)


class TestCounterfactualSimulator(unittest.TestCase):
    """Unit test suite for Counterfactual Forward Simulation Engine."""

    def setUp(self) -> None:
        self.simulator = CounterfactualSimulator(
            default_n_particles=2000,
            time_step_minutes=15.0,
            horizontal_diffusivity_kh=2.0,
        )
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

        self.t_release = datetime(2026, 9, 6, 18, 0, 0, tzinfo=UTC)
        self.t_obs = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)  # 12h later

        # Observed slick polygon at t_obs (centered at 72.518, 18.946)
        center_lon, center_lat = 72.518, 18.946
        circle = Point(center_lon, center_lat).buffer(0.015)
        ellipse = shapely.affinity.scale(circle, xfact=2.5, yfact=0.9)
        self.observed_slick = shapely.affinity.rotate(
            ellipse, 40.0, origin=(center_lon, center_lat)
        )

        # Pre-generate synthetic metocean dataset covering simulation domain
        self.forcing_ds = generate_synthetic_metocean_dataset(
            bbox=(71.8, 18.4, 73.0, 19.5),
            time_start=datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC),
            time_end=datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC),
            grid_res_deg=0.1,
            time_step_hours=2.0,
        )

    def test_counterfactual_simulation_congruent_track(self) -> None:
        """Verify forward simulation seeded at true suspect release coordinates aligns with observed slick."""
        # Seed near Bombay High origin coordinates (72.290, 18.865)
        seed_coords = (72.290, 18.865)

        result = self.simulator.simulate_candidate(
            case_id=self.case_id,
            mmsi=419000101,
            seed_coords=seed_coords,
            t_release=self.t_release,
            t_obs=self.t_obs,
            observed_slick_geom=self.observed_slick,
            forcing_dataset=self.forcing_ds,
            n_particles=2000,
            vessel_name="PACIFIC PEARL",
            random_seed=42,
        )

        # 1. Assert result fields
        self.assertEqual(result.mmsi, 419000101)
        self.assertEqual(result.vessel_name, "PACIFIC PEARL")
        self.assertEqual(result.duration_hours, 12.0)
        self.assertEqual(len(result.seed_position), 2)
        self.assertEqual(len(result.simulated_centroid), 2)
        self.assertEqual(len(result.observed_centroid), 2)

        # 2. Geometric congruence assertions
        # Drift moves particles east-northeast towards observed slick
        self.assertGreater(result.similarity_score, 40.0)
        self.assertLess(result.centroid_distance_m, 3500.0)
        self.assertLess(result.hausdorff_distance_m, 7000.0)

        # 3. GeoJSON polygon validation
        self.assertEqual(result.simulated_polygon_geojson["type"], "Polygon")
        self.assertGreater(len(result.simulated_polygon_geojson["coordinates"][0]), 3)

        # 4. Snapshots validation
        self.assertGreater(len(result.snapshots), 2)
        first_snap = result.snapshots[0]
        self.assertIn("subsample_coords", first_snap)
        self.assertGreater(len(first_snap["subsample_coords"]), 0)

        # 5. Rule 1: Paired confidence
        self.assertGreaterEqual(result.confidence_pct, 0.0)
        self.assertLessEqual(result.confidence_pct, 100.0)

    def test_counterfactual_simulation_divergent_track(self) -> None:
        """Verify forward simulation seeded at a distant innocent vessel position yields low/zero overlap."""
        # Innocent vessel position far to the southeast
        divergent_seed = (72.850, 18.200)

        result = self.simulator.simulate_candidate(
            case_id=self.case_id,
            mmsi=419000102,
            seed_coords=divergent_seed,
            t_release=self.t_release,
            t_obs=self.t_obs,
            observed_slick_geom=self.observed_slick,
            forcing_dataset=self.forcing_ds,
            n_particles=1000,
            vessel_name="MAERSK TAIPEI",
            random_seed=42,
        )

        # Geometric mismatch assertions
        self.assertEqual(result.iou_pct, 0.0)
        self.assertGreater(result.centroid_distance_m, 20000.0)  # > 20 km away
        self.assertGreater(result.hausdorff_distance_m, 20000.0)
        self.assertLess(result.similarity_score, 15.0)
        self.assertIn("low geometric overlap", result.rationale.lower())

    def test_deterministic_reproducibility(self) -> None:
        """Verify identical random seed reproduces identical metrics and centroid coordinates."""
        seed_coords = (72.290, 18.865)

        res1 = self.simulator.simulate_candidate(
            case_id=self.case_id,
            mmsi=419000101,
            seed_coords=seed_coords,
            t_release=self.t_release,
            t_obs=self.t_obs,
            observed_slick_geom=self.observed_slick,
            forcing_dataset=self.forcing_ds,
            n_particles=1000,
            random_seed=123,
        )

        res2 = self.simulator.simulate_candidate(
            case_id=self.case_id,
            mmsi=419000101,
            seed_coords=seed_coords,
            t_release=self.t_release,
            t_obs=self.t_obs,
            observed_slick_geom=self.observed_slick,
            forcing_dataset=self.forcing_ds,
            n_particles=1000,
            random_seed=123,
        )

        self.assertEqual(res1.iou_pct, res2.iou_pct)
        self.assertEqual(res1.centroid_distance_m, res2.centroid_distance_m)
        self.assertEqual(res1.hausdorff_distance_m, res2.hausdorff_distance_m)
        self.assertEqual(res1.simulated_centroid, res2.simulated_centroid)

    def test_counterfactual_from_db_session(self) -> None:
        """Verify simulate_from_db loading case, candidate, and detection entities from database."""
        mock_db = MagicMock(spec=Session)

        mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.SCORING,
            created_by="analyst_test",
        )

        mock_det = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(self.observed_slick, srid=4326),
            centroid=from_shape(self.observed_slick.centroid, srid=4326),
            detection_time=self.t_obs,
            confidence=88.5,
            data_source=DataSource.SYNTHETIC,
        )

        mock_char = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            t_age_hours=12.0,
            age_confidence=85.0,
        )

        mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(Point(72.290, 18.865), srid=4326),
            confidence_pct=89.0,
        )

        mock_cand = VesselCandidate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            mmsi=419000101,
            name="PACIFIC PEARL",
            vessel_type="Tanker",
            s_culprit=88.5,
            confidence=89.0,
            sub_scores={
                "spatial": 98.0,
                "temporal": 95.0,
                "details": {"cpa_coords": [72.290, 18.865]},
            },
            ais_coverage=AISCoverage.FULL,
        )

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = mock_case
            elif model == VesselCandidate:
                q.filter.return_value.first.return_value = mock_cand
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = mock_det
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = mock_char
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = mock_origin
            return q

        mock_db.query.side_effect = mock_query

        res = self.simulator.simulate_from_db(
            db=mock_db,
            case_id=self.case_id,
            mmsi=419000101,
            forcing_dataset=self.forcing_ds,
            n_particles=1000,
            random_seed=42,
        )

        self.assertEqual(res.mmsi, 419000101)
        self.assertEqual(res.vessel_name, "PACIFIC PEARL")
        self.assertGreater(res.confidence_pct, 0.0)
        self.assertGreater(len(res.snapshots), 0)

    def test_rule_6_zero_banned_terms(self) -> None:
        """Rule 6: Verify strictly zero occurrences of banned terms in counterfactual rationales."""
        dummy_path = Path("test_counterfactual.py")

        result = self.simulator.simulate_candidate(
            case_id=self.case_id,
            mmsi=419000101,
            seed_coords=(72.290, 18.865),
            t_release=self.t_release,
            t_obs=self.t_obs,
            observed_slick_geom=self.observed_slick,
            forcing_dataset=self.forcing_ds,
            n_particles=1000,
            vessel_name="PACIFIC PEARL",
            random_seed=42,
        )

        violations = check_content(result.rationale, dummy_path)
        self.assertEqual(
            len(violations),
            0,
            f"Banned term violation in counterfactual rationale: {[v.rule_name for v in violations]}",
        )
        assert_no_banned_terms(result.rationale, "counterfactual_rationale")


if __name__ == "__main__":
    unittest.main()
