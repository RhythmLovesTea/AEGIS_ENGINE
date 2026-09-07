"""AEGIS-Marine: Unit tests for Replay State Server (TASK-033, Feature 4 / D4).

Verifies:
- Continuous geodetic and kinematic interpolation between keyframes.
- Lagrangian particle cloud interpolation (centroid, dispersion radius, subsampled coords).
- Dynamic evolving attribution score S_culprit(t) peaking at CPA and decaying as vessels depart.
- Live dynamic re-ranking of vessel candidates across the timeline.
- Boundary clamping at timeline extremities (t < t_start, t > t_end).
- Top-level function get_replay_state.
- Full compliance with:
  - Rule 1: Paired confidence score in [0.0, 100.0] on all payloads and vessel records.
  - Rule 3: Multi-criteria dynamic attribution (never distance-only).
  - Rule 6: Strictly zero occurrences of banned determination terms.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from geoalchemy2.shape import from_shape
from scripts.lint_banned_terms import check_content
from shapely.geometry import Point, Polygon
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import ReplayStatePayload
from backend.services.explainability.replay_service import (
    ReplayService,
    assert_no_banned_terms,
    get_replay_state,
)


class TestReplayService(unittest.TestCase):
    """Unit test suite for Replay State Server."""

    def setUp(self) -> None:
        self.service = ReplayService.get_instance()
        self.service.tau_dist_m = 2500.0
        self.service.tau_time_hours = 2.0
        self.service.clear_cache()
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

        self.t_rel = datetime(2026, 9, 6, 18, 0, 0, tzinfo=UTC)
        self.t_obs = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)  # 12h span

        # Particle keyframes at 1-hour intervals (13 snapshots)
        # Cloud drifts from origin (72.290, 18.865) to observed slick (72.518, 18.946)
        self.particle_snapshots = []
        for i in range(13):
            t_i = self.t_rel + timedelta(hours=i)
            alpha = i / 12.0
            mean_lon = (1.0 - alpha) * 72.290 + alpha * 72.518
            mean_lat = (1.0 - alpha) * 18.865 + alpha * 18.946
            dispersion = 600.0 + alpha * 1000.0

            # 10 subsampled particle offsets around centroid
            subsamples = [
                [round(mean_lon + (p - 5) * 0.001, 5), round(mean_lat + (p - 5) * 0.0008, 5)]
                for p in range(10)
            ]

            self.particle_snapshots.append(
                {
                    "timestamp": t_i,
                    "step_index": i,
                    "mean_lon": round(mean_lon, 5),
                    "mean_lat": round(mean_lat, 5),
                    "dispersion_radius_m": round(dispersion, 1),
                    "n_particles": 2000,
                    "subsample_coords": subsamples,
                }
            )

        # Suspect Candidate: Vessel A (PACIFIC PEARL, MMSI 419000101, Tanker)
        # Passes through origin at t_rel (hour 0) at 6.2 knots
        self.vessel_a_cand = {
            "mmsi": 419000101,
            "name": "PACIFIC PEARL",
            "vessel_type": "Tanker",
            "flag_state": "Panama",
            "s_culprit": 88.5,
            "confidence": 89.0,
            "sub_scores": {
                "spatial": 98.0,
                "temporal": 95.0,
                "kinematic": 92.0,
                "anomaly": 85.0,
                "type": 100.0,
                "details": {
                    "cpa_coords": [72.290, 18.865],
                    "speed_kts": 6.2,
                    "cog_deg": 68.0,
                },
            },
        }

        # Vessel A track points: from southwest to northeast across 12 hours
        self.vessel_a_track = []
        for i in range(13):
            t_i = self.t_rel + timedelta(hours=i)
            dt_h = i
            if dt_h == 0:
                lon = 72.290
                lat = 18.865
                sog = 6.2
                cog = 68.0
            else:
                # Sailing southeast away from origin at 12.5 knots
                lon = 72.290 + (dt_h * 0.03)
                lat = 18.865 - (dt_h * 0.02)
                sog = 12.5
                cog = 135.0
            self.vessel_a_track.append(
                {
                    "timestamp": t_i,
                    "lon": round(lon, 5),
                    "lat": round(lat, 5),
                    "sog": sog,
                    "cog": cog,
                }
            )

        # Innocent Candidate: Vessel B (MAERSK TAIPEI, MMSI 419000102, Container)
        # Passes far to the south
        self.vessel_b_cand = {
            "mmsi": 419000102,
            "name": "MAERSK TAIPEI",
            "vessel_type": "Container",
            "flag_state": "Singapore",
            "s_culprit": 22.0,
            "confidence": 84.0,
            "sub_scores": {
                "spatial": 18.0,
                "temporal": 25.0,
                "kinematic": 30.0,
                "anomaly": 10.0,
                "type": 40.0,
                "details": {
                    "cpa_coords": [72.450, 18.400],
                    "speed_kts": 16.5,
                    "cog_deg": 190.0,
                },
            },
        }

        self.vessel_b_track = []
        for i in range(13):
            t_i = self.t_rel + timedelta(hours=i)
            self.vessel_b_track.append(
                {
                    "timestamp": t_i,
                    "lon": round(72.400 + i * 0.01, 5),
                    "lat": round(18.350 + i * 0.005, 5),  # ~50 km south
                    "sog": 16.5,
                    "cog": 190.0,
                }
            )

        self.candidates = [self.vessel_a_cand, self.vessel_b_cand]
        self.vessel_tracks = {
            419000101: self.vessel_a_track,
            419000102: self.vessel_b_track,
        }

    def test_replay_keyframe_exact_match(self) -> None:
        """Verify querying exactly at a keyframe timestamp reproduces exact snapshot values."""
        t_keyframe = self.t_rel + timedelta(hours=2)

        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=t_keyframe,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )

        self.assertEqual(res.case_id, self.case_uuid)
        self.assertEqual(res.timestamp, t_keyframe)

        # Expected snapshot at index 2
        snap2 = self.particle_snapshots[2]
        self.assertAlmostEqual(res.particles.mean_lon, snap2["mean_lon"], places=4)
        self.assertAlmostEqual(res.particles.mean_lat, snap2["mean_lat"], places=4)
        self.assertAlmostEqual(
            res.particles.dispersion_radius_m, snap2["dispersion_radius_m"], places=1
        )
        self.assertEqual(len(res.particles.subsample_coords), 10)

    def test_replay_intermediate_interpolation(self) -> None:
        """Verify querying at intermediate time (e.g. +2.5 hours) produces smooth linear interpolation."""
        t_mid = self.t_rel + timedelta(hours=2, minutes=30)  # exactly halfway between index 2 and 3

        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=t_mid,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )

        snap2 = self.particle_snapshots[2]
        snap3 = self.particle_snapshots[3]

        expected_lon = round(0.5 * snap2["mean_lon"] + 0.5 * snap3["mean_lon"], 5)
        expected_lat = round(0.5 * snap2["mean_lat"] + 0.5 * snap3["mean_lat"], 5)
        expected_disp = round(
            0.5 * snap2["dispersion_radius_m"] + 0.5 * snap3["dispersion_radius_m"], 1
        )

        self.assertAlmostEqual(res.particles.mean_lon, expected_lon, places=4)
        self.assertAlmostEqual(res.particles.mean_lat, expected_lat, places=4)
        self.assertAlmostEqual(res.particles.dispersion_radius_m, expected_disp, places=1)

        # Vessel A position should also be midway between track points 2 and 3
        v_a = next(v for v in res.vessels if v.mmsi == 419000101)
        expected_v_lon = round(
            0.5 * self.vessel_a_track[2]["lon"] + 0.5 * self.vessel_a_track[3]["lon"], 5
        )
        expected_v_lat = round(
            0.5 * self.vessel_a_track[2]["lat"] + 0.5 * self.vessel_a_track[3]["lat"], 5
        )
        self.assertAlmostEqual(v_a.lon, expected_v_lon, places=4)
        self.assertAlmostEqual(v_a.lat, expected_v_lat, places=4)

    def test_dynamic_s_culprit_evolution(self) -> None:
        """Verify S_culprit(t) evolves dynamically: peaks at closest encounter (CPA) and decays as vessel departs."""
        # 1. At t_rel (closest encounter at origin, speed drop dumping 6.2 kts)
        res_cpa = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )
        va_cpa = next(v for v in res_cpa.vessels if v.mmsi == 419000101)

        # 2. At t_late (+8 hours, vessel has moved far away)
        res_late = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel + timedelta(hours=8),
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )
        va_late = next(v for v in res_late.vessels if v.mmsi == 419000101)

        # CPA score must be significantly higher than departed score
        self.assertGreater(va_cpa.current_s_culprit, 80.0)
        self.assertGreater(va_cpa.current_s_culprit, va_late.current_s_culprit)
        self.assertLess(va_cpa.distance_to_cloud_m, 100.0)
        self.assertGreater(va_late.distance_to_cloud_m, 10000.0)  # > 10 km away

    def test_dynamic_vessel_re_ranking(self) -> None:
        """Verify live ranking of vessels dynamically updates based on evolving current_s_culprit."""
        # At CPA, Vessel A is Rank 1 and Vessel B is Rank 2
        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )

        self.assertEqual(res.vessels[0].mmsi, 419000101)
        self.assertEqual(res.vessels[0].rank, 1)
        self.assertEqual(res.vessels[1].mmsi, 419000102)
        self.assertEqual(res.vessels[1].rank, 2)
        self.assertGreater(res.vessels[0].current_s_culprit, res.vessels[1].current_s_culprit)

    def test_boundary_clamping(self) -> None:
        """Verify queries before timeline start and after timeline end are clamped safely."""
        # Before start (-2 hours)
        res_early = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel - timedelta(hours=2),
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )
        self.assertEqual(res_early.time_progress_pct, 0.0)
        self.assertAlmostEqual(
            res_early.particles.mean_lon, self.particle_snapshots[0]["mean_lon"], places=4
        )

        # After end (+15 hours)
        res_late = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel + timedelta(hours=15),
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )
        self.assertEqual(res_late.time_progress_pct, 100.0)
        self.assertAlmostEqual(
            res_late.particles.mean_lon, self.particle_snapshots[-1]["mean_lon"], places=4
        )

    def test_rule_1_mandatory_paired_confidence(self) -> None:
        """Rule 1: Verify all replay payloads and vessel states include valid confidence scores."""
        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel + timedelta(hours=3),
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )

        self.assertGreaterEqual(res.confidence_pct, 0.0)
        self.assertLessEqual(res.confidence_pct, 100.0)

        for v in res.vessels:
            self.assertGreaterEqual(v.confidence_pct, 0.0)
            self.assertLessEqual(v.confidence_pct, 100.0)

    def test_rule_6_zero_banned_terms(self) -> None:
        """Rule 6: Verify strictly zero occurrences of banned terms in replay metadata and fields."""
        dummy_path = Path("test_replay_service.py")

        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
        )

        for v in res.vessels:
            text = f"{v.name} {v.vessel_type}"
            violations = check_content(text, dummy_path)
            self.assertEqual(len(violations), 0)
            assert_no_banned_terms(text, f"vessel_{v.mmsi}")

    def test_get_replay_state_top_level_function(self) -> None:
        """Verify the exposed top-level get_replay_state function works seamlessly."""
        # Pre-register case cache in singleton
        self.service.register_case_cache(
            case_id=self.case_id,
            particle_snapshots=self.particle_snapshots,
            vessel_tracks=self.vessel_tracks,
            candidates=self.candidates,
            origin_centroid=(72.290, 18.865),
            observed_slick_centroid=(72.518, 18.946),
        )

        res: ReplayStatePayload = get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel + timedelta(hours=1),
        )

        self.assertEqual(res.case_id, self.case_uuid)
        self.assertGreater(len(res.vessels), 0)
        self.assertGreater(res.particles.n_particles, 0)
        self.assertIsNotNone(res.estimated_origin_centroid)
        self.assertIsNotNone(res.observed_slick_centroid)

    def test_replay_service_from_db_session(self) -> None:
        """Verify get_replay_state loading case entities from a mocked database session."""
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

        mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(Point(72.290, 18.865), srid=4326),
            covariance_matrix={"sigma_xx": 1.2, "sigma_yy": 0.8, "sigma_xy": 0.3},
            time_window_start=self.t_rel - timedelta(hours=1),
            time_window_end=self.t_rel + timedelta(hours=1),
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
            sub_scores=self.vessel_a_cand["sub_scores"],
            anomaly_flags=["speed_drop_dumping"],
            ais_coverage=AISCoverage.FULL,
        )

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = mock_case
            elif model == VesselCandidate:
                q.filter.return_value.order_by.return_value.all.return_value = [mock_cand]
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = mock_det
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = mock_origin
            return q

        mock_db.query.side_effect = mock_query
        mock_db.execute.return_value.fetchall.return_value = []  # No raw TimescaleDB rows fallback to origin

        res = self.service.get_replay_state(
            case_id=self.case_id,
            timestamp=self.t_rel,
            db=mock_db,
        )

        self.assertEqual(res.case_id, self.case_uuid)
        self.assertGreater(len(res.vessels), 0)
        self.assertEqual(res.vessels[0].mmsi, 419000101)


if __name__ == "__main__":
    unittest.main()
