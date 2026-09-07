"""Unit tests for vessel kinematic trajectory reconstruction (TASK-024)."""

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.services.data_adapters.ais_adapter import AISAdapter, AISTrackRecord
from backend.services.tier4_correlation.trajectory_reconstruction import (
    ClosestPointOfApproach,
    ReconstructedTrajectory,
    TrajectoryReconstructor,
    get_utm_epsg,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


class TestTrajectoryReconstruction(unittest.TestCase):
    """Test suite for cubic-spline trajectory reconstruction and CPA analysis."""

    def setUp(self) -> None:
        """Set up benchmark coordinates and times."""
        self.origin_centroid = (72.29, 18.865)  # [lon, lat]
        self.t_release = datetime(2026, 9, 6, 18, 0, 0, tzinfo=UTC)
        self.reconstructor = TrajectoryReconstructor(step_seconds=60.0)

    def test_utm_projection_code_calculation(self) -> None:
        """Verify get_utm_epsg returns correct UTM zone EPSG code."""
        # Bombay High at ~72.3E, 18.9N is in UTM Zone 43N (EPSG:32643)
        epsg = get_utm_epsg(72.29, 18.865)
        self.assertEqual(epsg, 32643)

        # Southern Hemisphere test
        epsg_south = get_utm_epsg(72.29, -18.865)
        self.assertEqual(epsg_south, 32743)

    def test_trajectory_reconstruction_single_point(self) -> None:
        """Verify graceful fallback for vessel with only 1 AIS report."""
        single_record = [
            AISTrackRecord(
                mmsi=123456789,
                timestamp=self.t_release,
                lon=72.29,
                lat=18.865,
                sog=10.0,
                cog=90.0,
                vessel_name="SOLO VESSEL",
                vessel_type="Cargo",
            )
        ]

        traj = self.reconstructor.reconstruct_vessel_trajectory(
            records=single_record,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        self.assertIsInstance(traj, ReconstructedTrajectory)
        self.assertEqual(traj.n_discrete_reports, 1)
        self.assertEqual(traj.n_interpolated_points, 1)
        self.assertAlmostEqual(traj.cpa.distance_m, 0.0, delta=5.0)
        self.assertEqual(traj.cpa.timestamp, self.t_release)

    def test_trajectory_reconstruction_two_points_linear(self) -> None:
        """Verify linear interpolation and derivative speed for 2 discrete reports."""
        t0 = self.t_release
        t1 = t0 + timedelta(hours=1)
        # 1 hour east transit: ~0.1 deg lon at 18.865N is ~10.5 km (~5.67 kts)
        records = [
            AISTrackRecord(
                mmsi=111222333,
                timestamp=t0,
                lon=72.20,
                lat=18.865,
                sog=5.7,
                cog=90.0,
                vessel_name="LINEAR SHIP",
                vessel_type="Tanker",
            ),
            AISTrackRecord(
                mmsi=111222333,
                timestamp=t1,
                lon=72.30,
                lat=18.865,
                sog=5.7,
                cog=90.0,
                vessel_name="LINEAR SHIP",
                vessel_type="Tanker",
            ),
        ]

        traj = self.reconstructor.reconstruct_vessel_trajectory(
            records=records,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        self.assertEqual(traj.n_discrete_reports, 2)
        self.assertEqual(traj.n_interpolated_points, 61)  # 60 minutes + 1 endpoint
        self.assertGreater(traj.cpa.sog_kts, 4.0)
        self.assertLess(traj.cpa.sog_kts, 8.0)
        # Heading should be approximately East (~90 deg)
        self.assertAlmostEqual(traj.cpa.cog_deg, 90.0, delta=5.0)

    def test_cubic_spline_interpolation_uniform_intervals(self) -> None:
        """Verify cubic spline produces continuous 1-minute points with velocity derivatives."""
        t_base = self.t_release - timedelta(hours=2)
        # 5 discrete points spaced 30 min apart
        discrete = []
        for i in range(5):
            t_cur = t_base + timedelta(minutes=i * 30)
            discrete.append(
                AISTrackRecord(
                    mmsi=999888777,
                    timestamp=t_cur,
                    lon=72.10 + i * 0.05,
                    lat=18.80 + i * 0.03,
                    sog=12.0,
                    cog=60.0,
                    vessel_name="SPLINE TESTER",
                    vessel_type="Cargo",
                )
            )

        traj = self.reconstructor.reconstruct_vessel_trajectory(
            records=discrete,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        self.assertEqual(traj.n_discrete_reports, 5)
        # 2 hours * 60 min + 1 = 121 points
        self.assertEqual(traj.n_interpolated_points, 121)

        # Check consecutive intervals are exactly 60 seconds
        for k in range(len(traj.interpolated_points) - 1):
            dt_sec = (
                traj.interpolated_points[k + 1].timestamp - traj.interpolated_points[k].timestamp
            ).total_seconds()
            self.assertAlmostEqual(dt_sec, 60.0, delta=0.1)

        # Rule 1 compliance: paired confidence
        self.assertGreaterEqual(traj.confidence_pct, 0.0)
        self.assertLessEqual(traj.confidence_pct, 100.0)

    def test_closest_point_of_approach_accuracy(self) -> None:
        """Verify analytical minimization finds exact CPA location and time."""
        t_mid = self.t_release
        t_start = t_mid - timedelta(hours=1)
        t_end = t_mid + timedelta(hours=1)

        # Vessel moving along constant latitude passing directly across origin at t_mid
        records = [
            AISTrackRecord(
                mmsi=555444333,
                timestamp=t_start,
                lon=72.19,
                lat=18.865,
                sog=10.0,
                cog=90.0,
                vessel_name="CPA TESTER",
                vessel_type="Tanker",
            ),
            AISTrackRecord(
                mmsi=555444333,
                timestamp=t_mid,
                lon=72.29,
                lat=18.865,  # Exactly at origin centroid
                sog=10.0,
                cog=90.0,
                vessel_name="CPA TESTER",
                vessel_type="Tanker",
            ),
            AISTrackRecord(
                mmsi=555444333,
                timestamp=t_end,
                lon=72.39,
                lat=18.865,
                sog=10.0,
                cog=90.0,
                vessel_name="CPA TESTER",
                vessel_type="Tanker",
            ),
        ]

        traj = self.reconstructor.reconstruct_vessel_trajectory(
            records=records,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        cpa = traj.cpa
        self.assertIsInstance(cpa, ClosestPointOfApproach)
        # CPA distance to origin should be nearly 0 meters
        self.assertLess(cpa.distance_m, 100.0)
        # CPA time should be within 2 minutes of t_mid
        time_diff_sec = abs((cpa.timestamp - t_mid).total_seconds())
        self.assertLess(time_diff_sec, 120.0)
        # Time delta to release should be near 0 hours
        self.assertIsNotNone(cpa.time_delta_to_release_hours)
        self.assertLess(cpa.time_delta_to_release_hours, 0.1)

    def test_synthetic_benchmark_pacific_pearl_cpa(self) -> None:
        """Verify benchmark vessel A (PACIFIC PEARL, MMSI 419000101) passes directly through origin."""
        adapter = AISAdapter(synthetic_dir=DATA_DIR)
        csv_file = DATA_DIR / "synthetic_ais_tracks.csv"
        all_records = adapter.load_records_from_file(csv_file, default_source="synthetic")

        pearl_records = [r for r in all_records if r.mmsi == 419000101]
        self.assertGreater(len(pearl_records), 10)

        traj = self.reconstructor.reconstruct_vessel_trajectory(
            records=pearl_records,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        # 1. PACIFIC PEARL passes right through ground truth origin
        self.assertLess(traj.cpa.distance_m, 400.0, "PACIFIC PEARL must pass within 400m of origin")

        # 2. CPA occurs within 15 minutes of estimated release time (18:00 UTC)
        diff_minutes = abs((traj.cpa.timestamp - self.t_release).total_seconds()) / 60.0
        self.assertLess(diff_minutes, 15.0)

        # 3. Vessel slows down into discharge band (4.0 - 8.0 kts) around origin
        self.assertGreaterEqual(traj.cpa.sog_kts, 4.0)
        self.assertLessEqual(traj.cpa.sog_kts, 8.5)

        # 4. GeoJSON export contains valid LineString
        geojson = traj.to_geojson_feature()
        self.assertEqual(geojson["type"], "Feature")
        self.assertEqual(geojson["geometry"]["type"], "LineString")
        self.assertEqual(len(geojson["geometry"]["coordinates"]), traj.n_interpolated_points)

    def test_reconstruct_all_multi_vessel(self) -> None:
        """Verify batch reconstruction across multiple vessels comparing CPA proximity."""
        adapter = AISAdapter(synthetic_dir=DATA_DIR)
        csv_file = DATA_DIR / "synthetic_ais_tracks.csv"
        all_records = adapter.load_records_from_file(csv_file, default_source="synthetic")

        all_trajs = self.reconstructor.reconstruct_all(
            records=all_records,
            origin_centroid=self.origin_centroid,
            t_release=self.t_release,
        )

        # All 5 benchmark vessels should be successfully reconstructed
        self.assertEqual(len(all_trajs), 5)
        self.assertIn(419000101, all_trajs)  # PACIFIC PEARL
        self.assertIn(419000102, all_trajs)  # MAERSK TAIPEI (Innocent transit)

        pearl_cpa = all_trajs[419000101].cpa
        maersk_cpa = all_trajs[419000102].cpa

        # PACIFIC PEARL passes close to origin (< 0.5 km)
        self.assertLess(pearl_cpa.distance_km, 0.5)

        # MAERSK TAIPEI transits far to the north (> 10 km away)
        self.assertGreater(maersk_cpa.distance_km, 10.0)


if __name__ == "__main__":
    unittest.main()
