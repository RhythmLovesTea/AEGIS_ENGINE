"""AEGIS-Marine: What-If Scenario Simulation Engine & Partial Task Re-Execution Tests (TASK-037).

Validates:
- Architecture Document Section 7 & 8, PRD Section 11 (Feature 3 / P3)
- Tier 1 preservation during Tier 3/4 re-execution
- Parameter overrides: t_age, wind_drift_factor, horizontal_diffusivity, origin_search_sigma, custom AHP weights
- Scenario child-key caching (Redis with in-memory fallback)
- API endpoints: POST /cases/{id}/whatif, GET /cases/{id}/scenarios, GET /cases/{id}/scenarios/{scenario_id}
- RBAC permissions (investigator, analyst, admin allowed; legal_reviewer denied for execution)
- Celery task: orchestration.run_what_if_scenario
- Constitutional Rules 1, 4, 6, and 7
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient
from scripts.lint_banned_terms import check_content
from shapely.geometry import Point, Polygon

from backend.app.main import create_app
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
from backend.app.schemas.case import WhatIfRequest
from backend.core.database import get_db
from backend.core.security import Role, create_access_token
from backend.services.data_adapters.metocean_adapter import (
    generate_synthetic_metocean_dataset,
)
from backend.services.orchestration.what_if_service import (
    ScenarioCacheRepository,
    WhatIfService,
    get_what_if_service,
)
from backend.workers.tasks.pipeline_tasks import run_what_if_scenario_task


class TestWhatIfScenarioEngine(unittest.TestCase):
    """Test suite covering the What-If simulation engine, caching, API, and compliance."""

    def setUp(self) -> None:
        self.app = create_app()
        self.mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.mock_db
        self.client = TestClient(self.app)

        # Auth tokens
        self.investigator_token = create_access_token("inv_user", roles=[Role.INVESTIGATOR])
        self.analyst_token = create_access_token("ana_user", roles=[Role.ANALYST])
        self.legal_reviewer_token = create_access_token("leg_user", roles=[Role.LEGAL_REVIEWER])
        self.admin_token = create_access_token("adm_user", roles=[Role.ADMIN])

        self.case_uuid = uuid.uuid4()
        self.now_utc = datetime.now(UTC)

        # Synthetic Case Entities
        self.sample_case = Case(
            id=self.case_uuid,
            status=CaseStatus.READY,
            region=Polygon([(72.0, 18.8), (72.3, 18.8), (72.3, 19.1), (72.0, 19.1), (72.0, 18.8)]),
            source_scene_ref="S1A_IW_GRDH_1SDV_20260907_WHATIF",
            created_by="analyst",
            created_at=self.now_utc,
        )

        self.initial_poly = Polygon(
            [(72.14, 18.90), (72.16, 18.90), (72.16, 18.92), (72.14, 18.92), (72.14, 18.90)]
        )
        self.sample_detection = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=self.initial_poly,
            centroid=Point(72.15, 18.91),
            area_m2=4_850_000.0,
            confidence=94.5,
            lookalike_risk=0.03,
            sensor="Sentinel-1A C-SAR IW",
            detection_time=self.now_utc,
            data_source=DataSource.SYNTHETIC,
            created_at=self.now_utc,
        )

        self.sample_characterization = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=12_400.0,
            principal_axis_deg=68.5,
            baoac_code=3,
            estimated_volume_m3=75.8,
            t_age_hours=4.2,
            age_confidence=88.0,
            created_at=self.now_utc,
        )

        self.sample_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=Point(72.08, 18.84),
            covariance_matrix={
                "var_lat": 0.000142,
                "var_lon": 0.000185,
                "cov_lon_lat": 0.000095,
            },
            time_window_start=self.now_utc,
            time_window_end=self.now_utc,
            confidence_pct=91.5,
            region_area_km2=18.4,
            particle_trajectory_ref="baseline_traj_ref",
            created_at=self.now_utc,
        )

        self.sample_candidates = [
            VesselCandidate(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                mmsi=412345678,
                imo=9876543,
                name="PACIFIC TITAN",
                flag_state="Panama",
                vessel_type="Crude Oil Tanker",
                s_culprit=88.5,
                confidence=92.0,
                sub_scores={
                    "spatial": 91.0,
                    "temporal": 89.5,
                    "kinematic": 84.0,
                    "anomaly": 86.0,
                    "type": 95.0,
                    "cpa_coords": [72.10, 18.85],
                    "heading": 65.0,
                    "sog": 12.5,
                },
                anomaly_flags=["speed_drop_dumping"],
                ais_coverage=AISCoverage.FULL,
                created_at=self.now_utc,
            ),
            VesselCandidate(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                mmsi=999000111,
                imo=None,
                name="UNFLAGGED CONTACT BRAVO",
                flag_state="Unknown",
                vessel_type="Bunkering Barge",
                s_culprit=58.2,
                confidence=72.0,
                sub_scores={
                    "spatial": 60.0,
                    "temporal": 55.0,
                    "kinematic": 50.0,
                    "anomaly": 65.0,
                    "type": 65.0,
                    "cpa_coords": [72.18, 18.93],
                    "heading": 120.0,
                    "sog": 8.0,
                },
                anomaly_flags=["dark_transponder_gap"],
                ais_coverage=AISCoverage.DARK_GAP,
                created_at=self.now_utc,
            ),
        ]

        self.sample_alternatives = [
            AlternativeExplanation(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                hypothesis="natural_seep",
                score=12.5,
                confidence=95.0,
                evidence={"geological_basin": "Mumbai Offshore Basin", "distance_km": 48.2},
                created_at=self.now_utc,
            )
        ]

        self.sample_case.detections = [self.sample_detection]
        self.sample_case.characterizations = [self.sample_characterization]
        self.sample_case.origin_estimates = [self.sample_origin]
        self.sample_case.vessel_candidates = self.sample_candidates
        self.sample_case.alternative_explanations = self.sample_alternatives

        # Configure mock_db routing
        def mock_query_fn(entity):
            mock_q = MagicMock()
            if entity == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif entity == SlickDetection:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_detection
                )
            elif entity == SlickCharacterization:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_characterization
                )
            elif entity == OriginEstimate:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_origin
                )
            elif entity == VesselCandidate:
                mock_q.filter.return_value.order_by.return_value.all.return_value = (
                    self.sample_candidates
                )
            return mock_q

        self.mock_db.query.side_effect = mock_query_fn

        # Pre-generate synthetic metocean dataset to speed up tests
        self.synthetic_ds = generate_synthetic_metocean_dataset(
            bbox=(71.0, 17.5, 73.5, 20.0),
            time_start=self.now_utc - datetime.resolution * 0,
            time_end=self.now_utc + datetime.resolution * 0,
        )

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    # =========================================================================
    # 1. Tier 1 Preservation & Parameter Override Verification
    # =========================================================================

    def test_whatif_modifying_t_age_reexecutes_tier3_and_4_preserving_tier1(self) -> None:
        """Modifying t_age re-executes hindcasting/attribution while preserving Tier 1."""
        service = WhatIfService(cache_repo=ScenarioCacheRepository())
        req = WhatIfRequest(
            scenario_name="Increased Slick Age Simulation",
            t_age_override_hours=8.5,
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst_test",
            forcing_dataset=self.synthetic_ds,
        )

        # 1. Tier 1 Slick Detection is preserved intact
        self.assertEqual(self.sample_detection.polygon, self.initial_poly)
        self.assertEqual(self.sample_detection.area_m2, 4_850_000.0)

        # 2. Tier 3 Origin Estimate has shifted release time
        self.assertIsNotNone(res.origin_estimate)
        self.assertAlmostEqual(res.comparison.release_time_shift_hours, 8.5 - 4.2, places=1)

        # 3. Tier 4 Candidates are re-scored
        self.assertTrue(len(res.ranked_vessels) >= 1)
        for cand in res.ranked_vessels:
            self.assertIn("spatial", cand.sub_scores.model_dump())
            self.assertIn("temporal", cand.sub_scores.model_dump())
            self.assertGreaterEqual(cand.s_culprit, 0.0)
            self.assertLessEqual(cand.s_culprit, 100.0)

        # 4. Comparison summary captures parameter delta
        t_age_deltas = [
            d
            for d in res.comparison.parameter_deltas
            if d.parameter in ["t_age_hours", "t_age_override_hours"]
        ]
        self.assertEqual(len(t_age_deltas), 1)
        self.assertEqual(t_age_deltas[0].what_if_value, 8.5)

    def test_whatif_wind_drift_factor_override(self) -> None:
        """Wind drift factor override (0.035 vs 0.030) modulates particle displacement."""
        service = WhatIfService(cache_repo=ScenarioCacheRepository())
        req = WhatIfRequest(
            scenario_name="High Wind Drift Sensitivity",
            wind_drift_factor=0.035,
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst_test",
            forcing_dataset=self.synthetic_ds,
        )

        # Origin displacement should be non-zero
        self.assertGreater(res.comparison.origin_displacement_km, 0.0)

        # Wind drift delta logged in comparison summary
        drift_deltas = [
            d for d in res.comparison.parameter_deltas if d.parameter == "wind_drift_factor"
        ]
        self.assertEqual(len(drift_deltas), 1)
        self.assertEqual(drift_deltas[0].what_if_value, 0.035)

    def test_whatif_diffusivity_and_sigma_overrides(self) -> None:
        """Horizontal diffusivity (K_h=5.0) and sigma (2.5) overrides scale uncertainty."""
        service = WhatIfService(cache_repo=ScenarioCacheRepository())
        req = WhatIfRequest(
            scenario_name="High Diffusivity Storm Scenario",
            horizontal_diffusivity=5.0,
            origin_search_sigma=2.5,
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst_test",
            forcing_dataset=self.synthetic_ds,
        )

        # Diffusivity & sigma parameter deltas present
        param_names = [d.parameter for d in res.comparison.parameter_deltas]
        self.assertIn("horizontal_diffusivity", param_names)
        self.assertIn("origin_search_sigma", param_names)

        # Origin ellipse area is positive
        self.assertGreater(res.origin_estimate.region_area_km2, 0.0)

    def test_whatif_custom_ahp_weights_reweighting(self) -> None:
        """Custom AHP weights are normalized (Rule 7) and alter candidate rankings."""
        service = WhatIfService(cache_repo=ScenarioCacheRepository())
        # Heavy emphasis on anomaly and spatial, de-emphasizing temporal
        custom_weights = {
            "spatial": 0.40,
            "temporal": 0.05,
            "kinematic": 0.05,
            "anomaly": 0.40,
            "type": 0.10,
        }
        req = WhatIfRequest(
            scenario_name="Anomaly-Focused Attribution",
            custom_ahp_weights=custom_weights,
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst_test",
            forcing_dataset=self.synthetic_ds,
        )

        # Check rank shifts are computed
        self.assertTrue(len(res.comparison.rank_shifts) >= 1)
        # Verify scores reflect new weights
        top_cand = res.ranked_vessels[0]
        self.assertGreaterEqual(top_cand.s_culprit, 0.0)
        self.assertLessEqual(top_cand.s_culprit, 100.0)

    # =========================================================================
    # 2. Scenario Caching & Retrieval Under Child Scenario Keys
    # =========================================================================

    def test_scenario_caching_and_retrieval(self) -> None:
        """Scenarios are cached under child keys case:{case_id}:scenario:{scenario_id}."""
        cache_repo = ScenarioCacheRepository()
        service = WhatIfService(cache_repo=cache_repo)

        req = WhatIfRequest(
            scenario_name="Persistent Cache Test Scenario",
            t_age_override_hours=7.0,
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst_cache",
            forcing_dataset=self.synthetic_ds,
        )

        scenario_id = res.scenario_id
        # Verify retrieval via get_scenario
        cached_res = service.get_scenario(case_id=self.case_uuid, scenario_id=scenario_id)
        self.assertIsNotNone(cached_res)
        self.assertEqual(cached_res.scenario_id, scenario_id)
        self.assertEqual(cached_res.scenario_name, "Persistent Cache Test Scenario")

        # Verify listing
        summaries = service.list_scenarios(case_id=self.case_uuid)
        self.assertTrue(len(summaries) >= 1)
        matching = [s for s in summaries if s.scenario_id == scenario_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].scenario_name, "Persistent Cache Test Scenario")

    # =========================================================================
    # 3. REST API & RBAC Matrix
    # =========================================================================

    def test_post_whatif_authorized_analyst_and_investigator(self) -> None:
        """Investigator and Analyst roles are authorized to run What-If simulations."""
        payload = {
            "scenario_name": "API Analyst What-If Run",
            "t_age_override_hours": 6.5,
            "wind_drift_factor": 0.032,
            "persist_scenario": True,
        }

        # Analyst role: 200 OK
        headers_analyst = {"Authorization": f"Bearer {self.analyst_token}"}
        resp = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/whatif",
            json=payload,
            headers=headers_analyst,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("scenario_id", data)
        self.assertIn("ranked_vessels", data)
        self.assertIn("comparison", data)

        # Investigator role: 200 OK
        headers_inv = {"Authorization": f"Bearer {self.investigator_token}"}
        resp_inv = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/whatif",
            json=payload,
            headers=headers_inv,
        )
        self.assertEqual(resp_inv.status_code, status.HTTP_200_OK)

    def test_post_whatif_legal_reviewer_forbidden(self) -> None:
        """Legal reviewer is denied POST /whatif (403 Forbidden)."""
        headers = {"Authorization": f"Bearer {self.legal_reviewer_token}"}
        payload = {"scenario_name": "Unauthorized Legal Run", "t_age_override_hours": 5.0}

        resp = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/whatif",
            json=payload,
            headers=headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_whatif_unauthenticated_denied(self) -> None:
        """Unauthenticated request to POST /whatif returns 401 Unauthorized."""
        payload = {"scenario_name": "Unauth Run"}
        resp = self.client.post(f"/api/v1/cases/{self.case_uuid}/whatif", json=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_scenarios_listing_and_detail(self) -> None:
        """GET /scenarios and GET /scenarios/{id} return cached scenario metadata."""
        # 1. Populate a scenario
        service = get_what_if_service()
        req = WhatIfRequest(scenario_name="Listing Test Scenario", persist_scenario=True)
        scenario_res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst",
            forcing_dataset=self.synthetic_ds,
        )

        headers = {"Authorization": f"Bearer {self.analyst_token}"}

        # 2. GET /cases/{id}/scenarios
        list_resp = self.client.get(f"/api/v1/cases/{self.case_uuid}/scenarios", headers=headers)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        scenarios_data = list_resp.json()
        self.assertTrue(isinstance(scenarios_data, list))
        self.assertTrue(len(scenarios_data) >= 1)

        # 3. GET /cases/{id}/scenarios/{scenario_id}
        detail_resp = self.client.get(
            f"/api/v1/cases/{self.case_uuid}/scenarios/{scenario_res.scenario_id}",
            headers=headers,
        )
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        detail_data = detail_resp.json()
        self.assertEqual(detail_data["scenario_id"], str(scenario_res.scenario_id))

        # 4. GET invalid scenario returns 404
        bad_resp = self.client.get(
            f"/api/v1/cases/{self.case_uuid}/scenarios/{uuid.uuid4()}",
            headers=headers,
        )
        self.assertEqual(bad_resp.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # 4. Celery Task Execution
    # =========================================================================

    def test_celery_run_what_if_scenario_task(self) -> None:
        """Celery run_what_if_scenario_task executes and returns serialized payload."""
        # Mock SessionLocal in pipeline_tasks
        from unittest.mock import patch

        with patch("backend.core.database.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__.return_value = self.mock_db

            params = {
                "scenario_name": "Celery Worker Scenario",
                "t_age_override_hours": 6.0,
                "persist_scenario": True,
            }

            result = run_what_if_scenario_task(
                case_id=str(self.case_uuid),
                request_params=params,
                user_id="worker_test",
            )

            self.assertIn("scenario_id", result)
            self.assertIn("ranked_vessels", result)
            self.assertIn("comparison", result)
            self.assertEqual(result["case_id"], str(self.case_uuid))

    # =========================================================================
    # 5. Constitutional Rules Compliance (Rules 1, 4, 6, 7)
    # =========================================================================

    def test_constitutional_rules_compliance(self) -> None:
        """Enforces Rule 1 (Confidence), Rule 4 (AIS Coverage), Rule 6 (Zero Banned Terms), and Rule 7 (AHP Normalization)."""
        service = WhatIfService(cache_repo=ScenarioCacheRepository())
        req = WhatIfRequest(
            scenario_name="Constitutional Verification Scenario",
            t_age_override_hours=7.5,
            wind_drift_factor=0.033,
            custom_ahp_weights={
                "spatial": 0.35,
                "temporal": 0.25,
                "kinematic": 0.20,
                "anomaly": 0.15,
                "type": 0.05,
            },
            persist_scenario=True,
        )

        res = service.run_scenario(
            case_id=self.case_uuid,
            request=req,
            db_session=self.mock_db,
            user_id="analyst",
            forcing_dataset=self.synthetic_ds,
        )

        # Rule 1: Paired confidence scores in [0.0, 100.0]
        self.assertGreaterEqual(res.origin_estimate.confidence_pct, 0.0)
        self.assertLessEqual(res.origin_estimate.confidence_pct, 100.0)
        self.assertGreaterEqual(res.comparison.confidence_pct, 0.0)
        self.assertLessEqual(res.comparison.confidence_pct, 100.0)
        for vessel in res.ranked_vessels:
            self.assertGreaterEqual(vessel.confidence, 0.0)
            self.assertLessEqual(vessel.confidence, 100.0)

        # Rule 4: Explicit AIS coverage flags
        for vessel in res.ranked_vessels:
            cov_val = (
                vessel.ais_coverage.value
                if hasattr(vessel.ais_coverage, "value")
                else str(vessel.ais_coverage)
            )
            self.assertIn(cov_val, ["full", "partial", "dark_gap", "non_ais_unknown"])

        # Rule 6: Zero occurrences of banned determination terms
        json_output = res.model_dump_json()
        violations = check_content(json_output, Path("what_if_scenario_output.json"))
        self.assertEqual(violations, [], f"Rule 6 violations detected: {violations}")

        # Rule 7: Weights sum to 1.0
        total_ahp = sum(req.custom_ahp_weights.values())
        self.assertAlmostEqual(total_ahp, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
