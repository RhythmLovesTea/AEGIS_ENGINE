"""AEGIS-Marine: Unit Tests for Multi-Criteria Attribution Scoring Engine (S_culprit).

Tests conform to:
- PRD Section 11 (FR-14, FR-16, C11, D1)
- Architecture Section 4.4
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0]
  - Rule 2: Stored 5-component sub-scores (spatial, temporal, kinematic, anomaly, type)
  - Rule 3: Nearest vessel is not automatically top-ranked (multi-criteria synthesis)
  - Rule 4: Explicit ais_coverage flags ('full' | 'partial' | 'dark_gap' | 'non_ais_unknown')
  - Rule 6: Strictly zero occurrences of banned terms
  - Rule 7: AHP weight application
"""

import math
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.app.schemas.common import AISCoverageEnum
from backend.app.schemas.vessel import SubScores
from backend.services.data_adapters.ais_adapter import AISAdapter
from backend.services.tier4_correlation.ahp_manager import CANONICAL_WEIGHTS
from backend.services.tier4_correlation.anomaly_detector import VesselAnomalyDetector
from backend.services.tier4_correlation.scoring_engine import (
    ScoredCandidateVessel,
    ScoringEngine,
    compute_anomaly_subscore,
    compute_kinematic_alignment_score,
    compute_mahalanobis_spatial_score,
    compute_temporal_coincidence_score,
    get_vessel_type_prior,
)
from backend.services.tier4_correlation.trajectory_reconstruction import (
    TrajectoryReconstructor,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SYNTHETIC_DIR = BASE_DIR / "data" / "synthetic"


class TestScoringEngine(unittest.TestCase):
    """Test suite for Tier 4 Attribution Scoring Engine and Sub-Score Derivations."""

    def setUp(self) -> None:
        self.engine = ScoringEngine(
            tau_hours=1.5,
            weights=dict(CANONICAL_WEIGHTS),
            ahp_version="v1.0",
        )
        self.origin_centroid = (72.290, 18.865)
        self.covariance = {
            "var_lon": 0.000185,
            "var_lat": 0.000142,
            "cov_lon_lat": 9.5e-05,
        }
        self.t_release = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)
        self.slick_orientation_deg = 65.0

    def test_spatial_mahalanobis_subscore(self) -> None:
        """Verify spatial sub-score computation via Mahalanobis distance D_M."""
        # 1. Directly at centroid -> D_M = 0, S_spatial = 100.0
        s_0, dm_0 = compute_mahalanobis_spatial_score(
            vessel_cpa_coords=self.origin_centroid,
            origin_centroid=self.origin_centroid,
            covariance_matrix=self.covariance,
        )
        self.assertEqual(dm_0, 0.0)
        self.assertEqual(s_0, 100.0)

        # 2. Near centroid (~200m away, along major axis) -> High score > 90
        near_coords = (72.291, 18.866)
        s_near, dm_near = compute_mahalanobis_spatial_score(
            vessel_cpa_coords=near_coords,
            origin_centroid=self.origin_centroid,
            covariance_matrix=self.covariance,
        )
        self.assertLess(dm_near, 1.0)
        self.assertGreater(s_near, 90.0)

        # 3. Far away (~15km north) -> D_M > 5.0, S_spatial < 1.0
        far_coords = (72.290, 19.000)
        s_far, dm_far = compute_mahalanobis_spatial_score(
            vessel_cpa_coords=far_coords,
            origin_centroid=self.origin_centroid,
            covariance_matrix=self.covariance,
        )
        self.assertGreater(dm_far, 5.0)
        self.assertLess(s_far, 1.0)

    def test_temporal_decay_subscore(self) -> None:
        """Verify temporal coincidence exponential decay score with tau = 1.5h."""
        # 1. Exact coincidence -> delta_t = 0, S_temporal = 100.0
        s_0, dt_0 = compute_temporal_coincidence_score(
            t_cpa=self.t_release,
            t_release=self.t_release,
            tau_hours=1.5,
        )
        self.assertEqual(dt_0, 0.0)
        self.assertEqual(s_0, 100.0)

        # 2. Offset = tau = 1.5 hours -> 100 / e ~ 36.79
        t_1_5h = self.t_release + timedelta(hours=1.5)
        s_1_5, dt_1_5 = compute_temporal_coincidence_score(
            t_cpa=t_1_5h,
            t_release=self.t_release,
            tau_hours=1.5,
        )
        self.assertAlmostEqual(dt_1_5, 1.5, places=3)
        self.assertAlmostEqual(s_1_5, 100.0 / math.e, places=1)

        # 3. Offset = 2 * tau = 3.0 hours -> 100 / e^2 ~ 13.53
        t_3h = self.t_release - timedelta(hours=3.0)
        s_3h, dt_3h = compute_temporal_coincidence_score(
            t_cpa=t_3h,
            t_release=self.t_release,
            tau_hours=1.5,
        )
        self.assertAlmostEqual(dt_3h, 3.0, places=3)
        self.assertAlmostEqual(s_3h, 100.0 / (math.e**2), places=1)

    def test_kinematic_alignment_subscore(self) -> None:
        """Verify kinematic heading alignment with slick principal orientation."""
        # 1. Perfect collinear alignment (65.0 deg vs 65.0 deg, speed 6.0 kts) -> 100.0
        s_align, diff_0 = compute_kinematic_alignment_score(
            vessel_heading_deg=65.0,
            slick_orientation_deg=65.0,
            sog_kts=6.0,
        )
        self.assertEqual(diff_0, 0.0)
        self.assertEqual(s_align, 100.0)

        # 2. Opposite direction collinear alignment (245.0 deg vs 65.0 deg) -> |cos(180)| = 1.0 -> 100.0
        s_opp, diff_opp = compute_kinematic_alignment_score(
            vessel_heading_deg=245.0,
            slick_orientation_deg=65.0,
            sog_kts=6.0,
        )
        self.assertEqual(diff_opp, 180.0)
        self.assertEqual(s_opp, 100.0)

        # 3. Orthogonal crossing (155.0 deg vs 65.0 deg) -> |cos(90)| = 0.0 -> 0.0
        s_ortho, diff_ortho = compute_kinematic_alignment_score(
            vessel_heading_deg=155.0,
            slick_orientation_deg=65.0,
            sog_kts=6.0,
        )
        self.assertEqual(diff_ortho, 90.0)
        self.assertEqual(s_ortho, 0.0)

        # 4. Stationary / drifting vessel (speed 0.2 kts) -> speed modulation dampens score
        s_stat, _ = compute_kinematic_alignment_score(
            vessel_heading_deg=65.0,
            slick_orientation_deg=65.0,
            sog_kts=0.2,
        )
        self.assertLess(s_stat, 25.0)

    def test_anomaly_subscore_formula(self) -> None:
        """Verify behavioral anomaly combination formula: 100 * (0.4 As + 0.3 Ac + 0.3 Ad)."""
        # All zero -> 0.0
        self.assertEqual(compute_anomaly_subscore(0.0, 0.0, 0.0), 0.0)

        # Pure speed drop dumping (As = 1.0) -> 40.0
        self.assertEqual(compute_anomaly_subscore(1.0, 0.0, 0.0), 40.0)

        # Pure transponder dark gap (Ad = 1.0) -> 30.0
        self.assertEqual(compute_anomaly_subscore(0.0, 0.0, 1.0), 30.0)

        # Full anomalies -> 100.0
        self.assertEqual(compute_anomaly_subscore(1.0, 1.0, 1.0), 100.0)

    def test_vessel_type_priors(self) -> None:
        """Verify vessel type categorical priors per PRD Section 11."""
        self.assertEqual(get_vessel_type_prior("Tanker"), 100.0)
        self.assertEqual(get_vessel_type_prior("Crude Oil Tanker"), 100.0)
        self.assertEqual(get_vessel_type_prior("Cargo"), 75.0)
        self.assertEqual(get_vessel_type_prior("Container Ship"), 75.0)
        self.assertEqual(get_vessel_type_prior("Offshore"), 50.0)
        self.assertEqual(get_vessel_type_prior("Fishing"), 30.0)
        self.assertEqual(get_vessel_type_prior("Pleasure Craft"), 5.0)
        self.assertEqual(get_vessel_type_prior(None), 20.0)

    def test_synthetic_benchmark_ranking_validation(self) -> None:
        """Verify attribution ranking on the official synthetic benchmark dataset.

        PRD / TODO.md Acceptance Criteria:
          - Vessel A (PACIFIC PEARL, 419000101): Ranked #1 with high S_culprit (> 80.0)
          - Vessel D (SEA SHADOW, 419000104): Flagged as dark_gap, ranked among top suspects
          - Vessel B (MAERSK TAIPEI, 419000102): Innocent transit, low score
        """
        # 1. Load synthetic AIS data
        csv_path = SYNTHETIC_DIR / "synthetic_ais_tracks.csv"
        adapter = AISAdapter()
        records = adapter.load_records_from_file(csv_path, default_source="synthetic")

        # 2. Reconstruct trajectories
        reconstructor = TrajectoryReconstructor(step_seconds=60.0)
        trajectories = reconstructor.reconstruct_all(
            records=records,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        # 3. Detect anomalies
        anomaly_detector = VesselAnomalyDetector()
        anomalies = {
            mmsi: anomaly_detector.assess_trajectory(traj, origin_centroid=self.origin_centroid)
            for mmsi, traj in trajectories.items()
        }

        # 4. Score and rank candidates
        ranked_vessels = self.engine.rank_candidates(
            trajectories=trajectories,
            anomalies=anomalies,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
            slick_orientation_deg=self.slick_orientation_deg,
            origin_covariance=self.covariance,
        )

        self.assertGreaterEqual(len(ranked_vessels), 4)

        # 5. Assert Vessel A (PACIFIC PEARL) is strictly ranked #1
        top1 = ranked_vessels[0]
        self.assertEqual(top1.mmsi, 419000101)
        self.assertEqual(top1.name, "PACIFIC PEARL")
        self.assertEqual(top1.rank, 1)
        self.assertGreater(top1.s_culprit, 80.0)

        # Verify Vessel A sub-scores (Rule 2)
        self.assertGreater(top1.sub_scores.spatial, 90.0)
        self.assertGreater(top1.sub_scores.temporal, 90.0)
        self.assertGreater(top1.sub_scores.kinematic, 90.0)
        self.assertEqual(top1.sub_scores.type, 100.0)
        self.assertIn("speed_drop_dumping", top1.anomaly_flags)

        # 6. Assert Vessel D (SEA SHADOW) has dark_gap flag
        vessel_d_matches = [v for v in ranked_vessels if v.mmsi == 419000104]
        self.assertEqual(len(vessel_d_matches), 1)
        vessel_d = vessel_d_matches[0]
        self.assertEqual(vessel_d.ais_coverage, AISCoverageEnum.DARK_GAP)
        self.assertIn("dark_transponder_gap", vessel_d.anomaly_flags)

        # 7. Assert Vessel B (MAERSK TAIPEI) is ranked below suspects
        vessel_b_matches = [v for v in ranked_vessels if v.mmsi == 419000102]
        self.assertEqual(len(vessel_b_matches), 1)
        vessel_b = vessel_b_matches[0]
        self.assertLess(vessel_b.s_culprit, 40.0)
        self.assertGreater(top1.s_culprit, vessel_b.s_culprit + 40.0)

        # 8. Assert all candidates satisfy Rule 1 and Rule 2
        for v in ranked_vessels:
            self.assertIsInstance(v, ScoredCandidateVessel)
            self.assertGreaterEqual(v.confidence, 0.0)
            self.assertLessEqual(v.confidence, 100.0)
            self.assertIsInstance(v.sub_scores, SubScores)
            self.assertGreaterEqual(len(v.evidence_refs), 5)
            # Serialization test
            as_dict = v.to_dict()
            self.assertIn("sub_scores", as_dict)
            self.assertIn("s_culprit", as_dict)


if __name__ == "__main__":
    unittest.main()
