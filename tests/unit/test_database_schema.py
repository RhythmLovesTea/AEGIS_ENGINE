"""Unit tests verifying TASK-004 database models and Alembic migration."""

import unittest
from pathlib import Path

from backend.app.models.base import Base
from backend.app.models.entities import (
    AHPConfig,
    AISCoverage,
    AlternativeExplanation,
    AuditLog,
    Case,
    CaseStatus,
    DataSource,
    Dossier,
    ForwardForecast,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)


class TestDatabaseSchema(unittest.TestCase):
    def test_all_models_registered_in_metadata(self) -> None:
        """Verify all tables defined in Architecture Section 6 exist in Base.metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected_tables = {
            "cases",
            "slick_detections",
            "slick_characterizations",
            "origin_estimates",
            "forward_forecasts",
            "vessel_candidates",
            "alternative_explanations",
            "ahp_configs",
            "dossiers",
            "audit_logs",
        }
        for table in expected_tables:
            self.assertIn(table, table_names, f"Table '{table}' missing from metadata")

    def test_rule_1_confidence_fields_enforced(self) -> None:
        """Enforce Rule 1: Every score and estimate must carry confidence/uncertainty."""
        # SlickDetection must have confidence
        self.assertTrue(hasattr(SlickDetection, "confidence"))
        # SlickCharacterization must have age_confidence
        self.assertTrue(hasattr(SlickCharacterization, "age_confidence"))
        # OriginEstimate must have confidence_pct
        self.assertTrue(hasattr(OriginEstimate, "confidence_pct"))
        # VesselCandidate must have confidence
        self.assertTrue(hasattr(VesselCandidate, "confidence"))
        # AlternativeExplanation must have confidence
        self.assertTrue(hasattr(AlternativeExplanation, "confidence"))

    def test_rule_2_sub_scores_persisted_in_vessel_candidate(self) -> None:
        """Enforce Rule 2: VesselCandidate persists sub_scores as stored column."""
        self.assertTrue(hasattr(VesselCandidate, "sub_scores"))
        col = VesselCandidate.__table__.columns["sub_scores"]
        self.assertEqual(col.type.__class__.__name__, "JSONB")

    def test_rule_4_dark_gap_enum_present(self) -> None:
        """Enforce Rule 4: dark_gap and non_ais_unknown must be valid AISCoverage enum values."""
        self.assertEqual(AISCoverage.DARK_GAP.value, "dark_gap")
        self.assertEqual(AISCoverage.NON_AIS_UNKNOWN.value, "non_ais_unknown")
        col = VesselCandidate.__table__.columns["ais_coverage"]
        self.assertIsNotNone(col)

    def test_rule_5_alternative_explanation_model_exists(self) -> None:
        """Enforce Rule 5: AlternativeExplanation table exists with hypothesis, score, evidence."""
        self.assertTrue(hasattr(AlternativeExplanation, "hypothesis"))
        self.assertTrue(hasattr(AlternativeExplanation, "score"))
        self.assertTrue(hasattr(AlternativeExplanation, "evidence"))

    def test_rule_7_ahp_config_model_exists(self) -> None:
        """Enforce Rule 7: AHPConfig stores version, pairwise_matrix, weights, consistency_ratio."""
        self.assertTrue(hasattr(AHPConfig, "version"))
        self.assertTrue(hasattr(AHPConfig, "pairwise_matrix"))
        self.assertTrue(hasattr(AHPConfig, "weights"))
        self.assertTrue(hasattr(AHPConfig, "consistency_ratio"))

    def test_alembic_files_exist(self) -> None:
        """Verify Alembic migration configuration and revision files exist."""
        root_dir = Path(__file__).resolve().parents[2]
        alembic_ini = root_dir / "backend" / "alembic.ini"
        env_py = root_dir / "backend" / "alembic" / "env.py"
        rev_1 = root_dir / "backend" / "alembic" / "versions" / "0001_initial_schema.py"

        self.assertTrue(alembic_ini.exists(), "alembic.ini missing")
        self.assertTrue(env_py.exists(), "env.py missing")
        self.assertTrue(rev_1.exists(), "0001_initial_schema.py missing")


if __name__ == "__main__":
    unittest.main()
