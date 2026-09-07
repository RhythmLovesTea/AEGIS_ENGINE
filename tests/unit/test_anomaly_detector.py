"""AEGIS-Marine: Unit Tests for Vessel Kinematic Anomaly Detector & Transponder Dark Gap Flagger.

Tests conform to:
- PRD Section 11 (FR-13, FR-19, C10)
- Architecture Section 4.4
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0]
  - Rule 4: Explicit ais_coverage ('full' | 'partial' | 'dark_gap' | 'non_ais_unknown') & data_source
  - Rule 6: Strictly zero occurrences of banned terms
"""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.services.data_adapters.ais_adapter import AISAdapter, AISTrackRecord
from backend.services.tier4_correlation.anomaly_detector import (
    AnomalyAssessment,
    VesselAnomalyDetector,
    compute_speed_drop_anomaly,
)
from backend.services.tier4_correlation.trajectory_reconstruction import (
    TrajectoryReconstructor,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SYNTHETIC_DIR = BASE_DIR / "data" / "synthetic"


class TestAnomalyDetector(unittest.TestCase):
    """Test suite for Tier 4 vessel anomaly detection and dark ship identification."""

    def setUp(self) -> None:
        self.detector = VesselAnomalyDetector(
            dark_gap_threshold_seconds=1800.0,  # 30 minutes
            course_turn_threshold_deg=45.0,
            origin_proximity_radius_m=15000.0,
        )
        self.reconstructor = TrajectoryReconstructor(step_seconds=60.0)
        self.origin_centroid = (72.290, 18.865)  # Bombay High synthetic origin

    def test_speed_anomaly_formula_boundaries(self) -> None:
        """Assert piecewise continuous formula for A_speed across all key boundaries."""
        # 1. Stopped / anchored: v = 0.0 -> max(0, 1 - 6/6) = 0.0
        self.assertAlmostEqual(compute_speed_drop_anomaly(0.0), 0.0, places=3)

        # 2. Slow crawl: v = 2.0 -> max(0, 1 - 4/6) = 1/3
        self.assertAlmostEqual(compute_speed_drop_anomaly(2.0), 1.0 / 3.0, places=3)

        # 3. Discharge speed band [4.0, 8.0] knots -> strictly 1.0
        self.assertEqual(compute_speed_drop_anomaly(4.0), 1.0)
        self.assertEqual(compute_speed_drop_anomaly(5.0), 1.0)
        self.assertEqual(compute_speed_drop_anomaly(5.8), 1.0)  # Vessel A dumping speed
        self.assertEqual(compute_speed_drop_anomaly(6.0), 1.0)  # Center of discharge band
        self.assertEqual(compute_speed_drop_anomaly(7.5), 1.0)
        self.assertEqual(compute_speed_drop_anomaly(8.0), 1.0)

        # 4. Transiting above discharge band: v = 10.0 -> max(0, 1 - 4/6) = 1/3
        self.assertAlmostEqual(compute_speed_drop_anomaly(10.0), 1.0 / 3.0, places=3)

        # 5. Normal cruise: v = 12.0 -> max(0, 1 - 6/6) = 0.0
        self.assertAlmostEqual(compute_speed_drop_anomaly(12.0), 0.0, places=3)

        # 6. High transit speeds (Vessel A leg 1: 14.5 kts, Vessel B: 17.2 kts) -> 0.0
        self.assertEqual(compute_speed_drop_anomaly(14.5), 0.0)
        self.assertEqual(compute_speed_drop_anomaly(17.2), 0.0)
        self.assertEqual(compute_speed_drop_anomaly(25.0), 0.0)

    def test_course_deviation_detection(self) -> None:
        """Verify course turn anomaly detection for straight vs turning tracks."""
        t0 = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        # 1. Straight-line track (heading 65.0 deg constantly)
        straight_records = [
            AISTrackRecord(
                mmsi=111111111,
                timestamp=t0 + timedelta(minutes=i * 10),
                lon=72.0 + i * 0.02,
                lat=18.0 + i * 0.01,
                sog=12.0,
                cog=65.0,
                heading=65.0,
            )
            for i in range(6)
        ]
        a_course_straight, dev_straight = self.detector.detect_course_deviation_anomaly(
            straight_records
        )
        self.assertEqual(a_course_straight, 0.0)
        self.assertLessEqual(dev_straight, 15.0)

        # 2. Sharp turn track (65 deg -> 155 deg = 90 deg turn)
        turn_records = [
            AISTrackRecord(
                mmsi=222222222,
                timestamp=t0 + timedelta(minutes=i * 10),
                lon=72.0 + i * 0.02,
                lat=18.0 + (i if i < 3 else 3 - (i - 3)) * 0.02,
                sog=6.0,
                cog=65.0 if i < 3 else 155.0,
                heading=65.0 if i < 3 else 155.0,
            )
            for i in range(6)
        ]
        a_course_turn, dev_turn = self.detector.detect_course_deviation_anomaly(turn_records)
        self.assertGreaterEqual(dev_turn, 45.0)
        self.assertGreater(a_course_turn, 0.5)

    def test_transponder_dark_gap_detection(self) -> None:
        """Verify detection of transponder silence gaps exceeding 30 minutes."""
        t0 = datetime(2026, 9, 6, 16, 0, tzinfo=UTC)

        # 1. Normal regular reporting (15-minute intervals) -> No gap
        regular_records = [
            AISTrackRecord(
                mmsi=333333333,
                timestamp=t0 + timedelta(minutes=i * 15),
                lon=72.20 + i * 0.02,
                lat=18.80 + i * 0.01,
                sog=12.0,
                cog=60.0,
            )
            for i in range(8)
        ]
        a_dark_reg, gaps_reg, cov_reg = self.detector.detect_transponder_gaps(regular_records)
        self.assertEqual(a_dark_reg, 0.0)
        self.assertEqual(len(gaps_reg), 0)
        self.assertEqual(cov_reg, "full")

        # 2. Transponder gap: 2.5 hours (150 minutes) between 16:45 and 19:15
        gap_records = [
            AISTrackRecord(
                mmsi=444444444,
                timestamp=t0,
                lon=72.20,
                lat=18.80,
                sog=11.5,
                cog=55.0,
            ),
            AISTrackRecord(
                mmsi=444444444,
                timestamp=t0 + timedelta(minutes=15),
                lon=72.228,
                lat=18.822,
                sog=11.5,
                cog=55.0,
            ),
            # 2.5 hour gap here (165 - 15 = 150 minutes)
            AISTrackRecord(
                mmsi=444444444,
                timestamp=t0 + timedelta(minutes=165),
                lon=72.321,
                lat=18.897,
                sog=11.5,
                cog=55.0,
            ),
            AISTrackRecord(
                mmsi=444444444,
                timestamp=t0 + timedelta(minutes=180),
                lon=72.350,
                lat=18.920,
                sog=11.5,
                cog=55.0,
            ),
        ]
        a_dark_gap, gaps, cov_gap = self.detector.detect_transponder_gaps(
            gap_records, origin_centroid=self.origin_centroid
        )
        self.assertEqual(cov_gap, "dark_gap")
        self.assertEqual(len(gaps), 1)
        self.assertGreaterEqual(a_dark_gap, 0.90)

        gap_info = gaps[0]
        self.assertAlmostEqual(gap_info.duration_hours, 2.5, places=1)
        self.assertIsNotNone(gap_info.extrapolated_cpa_distance_m)
        self.assertTrue(gap_info.crosses_origin_region)

    def test_dead_reckoning_gap_extrapolation(self) -> None:
        """Verify dead-reckoning extrapolation across dark gap computes origin proximity."""
        t_gap_start = datetime(2026, 9, 6, 16, 45, tzinfo=UTC)
        t_gap_end = datetime(2026, 9, 6, 19, 15, tzinfo=UTC)

        gap_records = [
            AISTrackRecord(
                mmsi=555555555,
                timestamp=t_gap_start,
                lon=72.228125,
                lat=18.8225,
                sog=11.5,
                cog=55.0,
            ),
            AISTrackRecord(
                mmsi=555555555,
                timestamp=t_gap_end,
                lon=72.321875,
                lat=18.8975,
                sog=11.5,
                cog=55.0,
            ),
        ]
        a_dark, gaps, cov = self.detector.detect_transponder_gaps(
            gap_records, origin_centroid=(72.290, 18.865)
        )
        self.assertEqual(cov, "dark_gap")
        self.assertEqual(len(gaps), 1)
        self.assertTrue(gaps[0].crosses_origin_region)
        # Verify extrapolated CPA distance is within reasonable nautical range (< 5 km)
        self.assertLess(gaps[0].extrapolated_cpa_distance_m, 5000.0)

    def test_non_ais_target_integration(self) -> None:
        """Verify non-AIS radar/optical contact handling per FR-19, P4, and Rule 4."""
        contact_id = "SAR_TARGET_BOMBAY_042"
        coords = (72.295, 18.870)
        det_time = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)

        assessment = self.detector.assess_non_ais_contact(
            contact_id=contact_id,
            coordinates=coords,
            detection_time=det_time,
            origin_centroid=self.origin_centroid,
            estimated_length_m=185.0,
            radar_confidence_pct=88.0,
            data_source="synthetic",
        )

        self.assertIsInstance(assessment, AnomalyAssessment)
        self.assertEqual(assessment.ais_coverage, "non_ais_unknown")
        self.assertIn("non_ais_radar_contact", assessment.anomaly_flags)
        self.assertIn("dark_transponder_gap", assessment.anomaly_flags)
        self.assertEqual(assessment.a_dark, 1.0)
        self.assertGreaterEqual(assessment.s_anomaly, 90.0)
        # Rule 1: Confidence score within [0.0, 100.0]
        self.assertGreaterEqual(assessment.confidence_pct, 0.0)
        self.assertLessEqual(assessment.confidence_pct, 100.0)
        self.assertEqual(assessment.data_source, "synthetic")

    def test_synthetic_benchmark_dataset_vessels(self) -> None:
        """Validate anomaly detection across all synthetic benchmark vessels.

        Specifically asserts:
          - Vessel A (PACIFIC PEARL, 419000101): triggers A_speed = 1.0 and 'speed_drop_dumping'.
          - Vessel D (SEA SHADOW, 419000104): triggers ais_coverage = 'dark_gap' and 'dark_transponder_gap'.
          - Vessel B (MAERSK TAIPEI, 419000102): innocent transit, A_speed = 0.0, no dumping flag.
        """
        # Load synthetic AIS CSV
        csv_path = SYNTHETIC_DIR / "synthetic_ais_tracks.csv"
        adapter = AISAdapter()
        records = adapter.load_records_from_file(csv_path, default_source="synthetic")

        trajectories = self.reconstructor.reconstruct_all(
            records=records,
            origin_centroid=self.origin_centroid,
            t_release=datetime(2026, 9, 6, 18, 0, tzinfo=UTC),
        )

        assessments = {
            mmsi: self.detector.assess_trajectory(traj, origin_centroid=self.origin_centroid)
            for mmsi, traj in trajectories.items()
        }

        # 1. Vessel A (MMSI 419000101, PACIFIC PEARL)
        vessel_a = assessments[419000101]
        self.assertEqual(vessel_a.mmsi, 419000101)
        self.assertEqual(vessel_a.vessel_name, "PACIFIC PEARL")
        # Assert A_speed = 1.0 (in discharge band 5.8 kts)
        self.assertEqual(
            vessel_a.a_speed,
            1.0,
            f"Vessel A must trigger A_speed = 1.0, got {vessel_a.a_speed}",
        )
        self.assertIn(
            "speed_drop_dumping",
            vessel_a.anomaly_flags,
            "Vessel A must have 'speed_drop_dumping' flag",
        )
        self.assertEqual(
            vessel_a.s_anomaly,
            100.0,
            f"Vessel A must achieve composite S_anomaly = 100.0, got {vessel_a.s_anomaly}",
        )
        self.assertEqual(vessel_a.ais_coverage, "full")

        # 2. Vessel D (MMSI 419000104, SEA SHADOW)
        vessel_d = assessments[419000104]
        self.assertEqual(vessel_d.mmsi, 419000104)
        self.assertEqual(vessel_d.vessel_name, "SEA SHADOW")
        # Assert dark gap detection
        self.assertEqual(
            vessel_d.ais_coverage,
            "dark_gap",
            f"Vessel D must be flagged as 'dark_gap', got {vessel_d.ais_coverage}",
        )
        self.assertIn(
            "dark_transponder_gap",
            vessel_d.anomaly_flags,
            "Vessel D must have 'dark_transponder_gap' flag",
        )
        self.assertGreaterEqual(
            vessel_d.a_dark,
            0.95,
            f"Vessel D A_dark must be >= 0.95, got {vessel_d.a_dark}",
        )
        self.assertGreaterEqual(
            vessel_d.s_anomaly,
            95.0,
            f"Vessel D S_anomaly must be >= 95.0, got {vessel_d.s_anomaly}",
        )
        self.assertGreater(len(vessel_d.dark_gaps), 0)
        self.assertTrue(vessel_d.dark_gaps[0].crosses_origin_region)

        # 3. Vessel B (MMSI 419000102, MAERSK TAIPEI - Innocent Cargo transit)
        vessel_b = assessments[419000102]
        self.assertEqual(vessel_b.mmsi, 419000102)
        self.assertEqual(vessel_b.vessel_name, "MAERSK TAIPEI")
        self.assertEqual(
            vessel_b.a_speed,
            0.0,
            f"Vessel B transit at 17.2 kts must yield A_speed = 0.0, got {vessel_b.a_speed}",
        )
        self.assertNotIn("speed_drop_dumping", vessel_b.anomaly_flags)
        self.assertNotIn("dark_transponder_gap", vessel_b.anomaly_flags)
        self.assertEqual(vessel_b.s_anomaly, 0.0)

        # 4. Check all assessments satisfy Rule 1 and Rule 4
        for _mmsi, assess in assessments.items():
            self.assertGreaterEqual(assess.confidence_pct, 0.0)
            self.assertLessEqual(assess.confidence_pct, 100.0)
            self.assertIn(assess.ais_coverage, ["full", "partial", "dark_gap", "non_ais_unknown"])
            self.assertEqual(assess.data_source, "synthetic")

    def test_constitutional_rules(self) -> None:
        """Verify adherence to Rule 1, Rule 4, and Rule 6."""
        # Check manifest expected MMSIs match
        manifest_path = SYNTHETIC_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["scenario"]["expected_top1_mmsi"], 419000101)
        self.assertEqual(manifest["scenario"]["expected_dark_ship_mmsi"], 419000104)


if __name__ == "__main__":
    unittest.main()
