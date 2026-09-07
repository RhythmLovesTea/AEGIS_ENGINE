"""AEGIS-Marine: Unit Tests for Automated Forensic PDF Legal Dossier Generator (TASK-034).

Tests conform to:
- PRD Section 11 (C13) & Architecture Sections 4.7 & 6
- Constitutional Rules:
  - Rule 1: Mandatory paired confidence scores across all items
  - Rule 4: Explicit surfacing of dark vessels and transponder gaps
  - Rule 5: Presence of non-vessel alternative hypotheses
  - Rule 6: Strictly zero occurrences of banned terms verified via check_content
- ISO/IEC 27037 Digital Forensic Chain-of-Custody (SHA-256 integrity)
"""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
from scripts.lint_banned_terms import check_content
from sqlalchemy.orm import Session

from backend.app.models.entities import AuditLog, Dossier
from backend.app.schemas.dossier import DossierResult
from backend.services.dossier.dossier_generator import (
    DEFAULT_MODEL_VERSIONS,
    DossierGenerator,
)


def _create_sample_sar_chip_b64() -> str:
    """Generates a small test PNG image as base64 data URI."""
    img = Image.new("RGB", (64, 64), color=(20, 30, 45))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


class TestDossierGenerator(unittest.TestCase):
    """Comprehensive test suite for DossierGenerator."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name)
        self.generator = DossierGenerator(storage_dir=self.storage_path)

        self.case_uuid = uuid.uuid4()
        self.timestamp = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)

        self.detection_fixture = {
            "sensor": "Sentinel-1A C-SAR IW",
            "detection_time": self.timestamp.isoformat(),
            "data_source": "synthetic",
            "centroid": {"type": "Point", "coordinates": [72.1523, 18.9124]},
            "polygon": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [72.14, 18.90],
                        [72.16, 18.90],
                        [72.16, 18.92],
                        [72.14, 18.92],
                        [72.14, 18.90],
                    ]
                ],
            },
            "area_m2": 4_850_000.0,
            "confidence": 94.2,  # Rule 1
            "lookalike_risk": 0.04,
        }

        self.characterization_fixture = {
            "perimeter_m": 12_400.0,
            "principal_axis_deg": 68.5,
            "baoac_code": 3,
            "estimated_volume_m3": 75.8,
            "t_age_hours": 4.2,
            "age_confidence": 88.0,  # Rule 1
        }

        self.origin_fixture = {
            "centroid": {"type": "Point", "coordinates": [72.0812, 18.8450]},
            "time_window_start": datetime(2026, 9, 7, 7, 30, 0, tzinfo=UTC).isoformat(),
            "time_window_end": datetime(2026, 9, 7, 8, 30, 0, tzinfo=UTC).isoformat(),
            "confidence_pct": 91.5,  # Rule 1
            "region_area_km2": 18.4,
        }

        self.candidates_fixture = [
            {
                "mmsi": 412345678,
                "imo": 9876543,
                "name": "PACIFIC TITAN",
                "flag_state": "Panama",
                "vessel_type": "Crude Oil Tanker",
                "s_culprit": 87.6,
                "confidence": 92.0,  # Rule 1
                "sub_scores": {
                    "spatial": 91.0,
                    "temporal": 89.5,
                    "kinematic": 84.0,
                    "anomaly": 86.0,
                    "type": 88.0,
                },
                "anomaly_flags": ["speed_drop_dumping", "course_deviation"],
                "ais_coverage": "full",
            },
            {
                "mmsi": 567890123,
                "imo": 9123456,
                "name": "NEPTUNE PIONEER",
                "flag_state": "Liberia",
                "vessel_type": "Chemical Tanker",
                "s_culprit": 62.3,
                "confidence": 78.5,  # Rule 1
                "sub_scores": {
                    "spatial": 65.0,
                    "temporal": 60.0,
                    "kinematic": 58.0,
                    "anomaly": 70.0,
                    "type": 55.0,
                },
                "anomaly_flags": [],
                "ais_coverage": "full",
            },
            {
                "mmsi": 999000111,
                "imo": None,
                "name": "UNFLAGGED CONTACT BRAVO",
                "flag_state": "Unknown",
                "vessel_type": "Bunkering Barge",
                "s_culprit": 51.4,
                "confidence": 72.0,  # Rule 1
                "sub_scores": {
                    "spatial": 58.0,
                    "temporal": 54.0,
                    "kinematic": 49.0,
                    "anomaly": 60.0,
                    "type": 42.0,
                },
                "anomaly_flags": ["dark_transponder_gap"],
                "ais_coverage": "dark_gap",  # Rule 4
            },
        ]

        self.alternatives_fixture = [
            {
                "hypothesis": "natural_seep",
                "score": 12.5,
                "confidence": 95.0,  # Rule 1
                "evidence": {
                    "geological_basin": "Mumbai Offshore Basin (Bombay High)",
                    "distance_km": 48.2,
                    "explanation": "Nearest active seep is 48.2 km distant; historical bathymetry unaligned.",
                },
            },
            {
                "hypothesis": "imaging_artifact",
                "score": 6.0,
                "confidence": 92.0,  # Rule 1
                "evidence": {
                    "wind_speed_ms": 5.2,
                    "spatial_anomaly": "High backscatter contrast exceeding lookalike threshold",
                },
            },
            {
                "hypothesis": "non_ais_vessel",
                "score": 38.0,
                "confidence": 75.0,  # Rule 1
                "evidence": {
                    "explanation": "Radar reflectivity anomalies suggest possible unflagged small craft in vicinity.",
                },
            },
        ]

        self.environmental_fixture = {
            "current_speed_ms": 0.35,
            "current_dir_deg": 72.0,
            "wind_speed_ms": 5.8,
            "wind_dir_deg": 250.0,
            "sst_c": 28.1,
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_weasyprint_pdf_generation(self) -> None:
        """Verify WeasyPrint compiles complete PDF with correct magic header and size."""
        sar_chip = _create_sample_sar_chip_b64()
        result = self.generator.generate_dossier(
            case_id=self.case_uuid,
            detection=self.detection_fixture,
            characterization=self.characterization_fixture,
            origin=self.origin_fixture,
            candidates=self.candidates_fixture,
            alternatives=self.alternatives_fixture,
            environmental=self.environmental_fixture,
            sar_chip_b64=sar_chip,
            engine="weasyprint",
        )

        self.assertIsInstance(result, DossierResult)
        self.assertIsNotNone(result.pdf_bytes)
        self.assertTrue(result.pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(result.file_size_bytes, 10_000)
        self.assertEqual(len(result.sha256_hash), 64)
        self.assertTrue(result.verification_qr_b64.startswith("data:image/png;base64,"))

        # Check saved file on disk
        pdf_file = Path(
            result.pdf_ref.replace("s3://aegis-storage/dossiers/", str(self.storage_path) + "/")
        )
        self.assertTrue(pdf_file.exists())
        self.assertEqual(pdf_file.read_bytes()[:5], b"%PDF-")

    def test_reportlab_fallback_pdf_generation(self) -> None:
        """Verify ReportLab fallback compiles complete PDF with valid structure."""
        result = self.generator.generate_dossier(
            case_id=self.case_uuid,
            detection=self.detection_fixture,
            characterization=self.characterization_fixture,
            origin=self.origin_fixture,
            candidates=self.candidates_fixture,
            alternatives=self.alternatives_fixture,
            environmental=self.environmental_fixture,
            engine="reportlab",
        )

        self.assertIsInstance(result, DossierResult)
        self.assertIsNotNone(result.pdf_bytes)
        self.assertTrue(result.pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(result.file_size_bytes, 2000)
        self.assertEqual(len(result.sha256_hash), 64)

    def test_canonical_sha256_determinism_and_verification(self) -> None:
        """Verify SHA-256 digest is deterministic and tamper-evident."""
        hash_1 = self.generator.compute_canonical_sha256(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            model_versions=DEFAULT_MODEL_VERSIONS,
            generated_at=self.timestamp,
        )

        hash_2 = self.generator.compute_canonical_sha256(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            model_versions=DEFAULT_MODEL_VERSIONS,
            generated_at=self.timestamp,
        )

        self.assertEqual(hash_1, hash_2)

        # Integrity verification passes
        is_valid = self.generator.verify_dossier_integrity(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            model_versions=DEFAULT_MODEL_VERSIONS,
            generated_at=self.timestamp,
            expected_sha256=hash_1,
        )
        self.assertTrue(is_valid)

        # Tampered candidate score alters digest
        tampered_candidates = [dict(c) for c in self.candidates_fixture]
        tampered_candidates[0]["s_culprit"] = 99.9
        tampered_hash = self.generator.compute_canonical_sha256(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=tampered_candidates,
            alternatives_data=self.alternatives_fixture,
            model_versions=DEFAULT_MODEL_VERSIONS,
            generated_at=self.timestamp,
        )
        self.assertNotEqual(hash_1, tampered_hash)

    def test_all_six_sections_rendered_in_html(self) -> None:
        """Verify all 6 required sections exist in the rendered HTML output."""
        context = self.generator.prepare_template_context(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            environmental_data=self.environmental_fixture,
            sar_chip_b64=None,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            verification_qr_b64="data:image/png;base64,mock",
            generated_at=self.timestamp,
            generated_by="AEGIS Automated Forensic Pipeline",
            model_versions=DEFAULT_MODEL_VERSIONS,
        )

        rendered_html = self.generator.render_html("dossier_template.html", context)

        # Section 1
        self.assertIn("1. Executive Incident Summary", rendered_html)
        self.assertIn("Sentinel-1A C-SAR IW", rendered_html)

        # Section 2
        self.assertIn("2. Slick Morphometry, Volume &amp; Spreading Aging Inversion", rendered_html)
        self.assertIn("Bonn Agreement Oil Appearance Code", rendered_html)
        self.assertIn("4.2 hours", rendered_html)

        # Section 3
        self.assertIn(
            "3. Hydrodynamic Hindcast Origin Cloud &amp; Environmental Forcing Summary",
            rendered_html,
        )
        self.assertIn("OpenDrift / OpenOil", rendered_html)
        self.assertIn("18.40 km&sup2;", rendered_html)

        # Section 4
        self.assertIn("4. Ranked Candidate Suspects Table", rendered_html)
        self.assertIn("PACIFIC TITAN", rendered_html)
        self.assertIn("NEPTUNE PIONEER", rendered_html)

        # Section 5
        self.assertIn("5. Alternative Explanations Evaluated", rendered_html)
        self.assertIn("Natural Geological Hydrocarbon Seep", rendered_html)

        # Section 6
        self.assertIn("6. Mandatory Responsible-Use Notice", rendered_html)
        self.assertIn("MARPOL 73/78 Annex I", rendered_html)

        # Footer & Stamp
        self.assertIn("Cryptographic Chain-of-Custody Integrity Digest (SHA-256)", rendered_html)
        self.assertIn(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", rendered_html
        )

    def test_rule_1_compliance_mandatory_confidence(self) -> None:
        """Constitutional Rule 1: Every estimate and score must have paired confidence."""
        bad_candidates = [
            {
                "mmsi": 111222333,
                "name": "TEST VESSEL",
                "vessel_type": "Tanker",
                "s_culprit": 80.0,
                # Missing 'confidence'
                "sub_scores": {
                    "spatial": 80,
                    "temporal": 80,
                    "kinematic": 80,
                    "anomaly": 80,
                    "type": 80,
                },
                "anomaly_flags": [],
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            self.generator.generate_dossier(
                case_id=self.case_uuid,
                detection=self.detection_fixture,
                characterization=self.characterization_fixture,
                origin=self.origin_fixture,
                candidates=bad_candidates,
                alternatives=self.alternatives_fixture,
            )
        self.assertIn("Rule 1 Violation", str(ctx.exception))

    def test_rule_4_compliance_dark_vessels_surfaced(self) -> None:
        """Constitutional Rule 4: Transponder gaps and dark vessels are explicitly surfaced."""
        result = self.generator.generate_dossier(
            case_id=self.case_uuid,
            detection=self.detection_fixture,
            characterization=self.characterization_fixture,
            origin=self.origin_fixture,
            candidates=self.candidates_fixture,
            alternatives=self.alternatives_fixture,
            engine="reportlab",
        )
        self.assertIsNotNone(result.pdf_bytes)

        # Check rendered HTML contains DARK GAP
        context = self.generator.prepare_template_context(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            environmental_data=None,
            sar_chip_b64=None,
            sha256_hash="0" * 64,
            verification_qr_b64="data:image/png;base64,test",
            generated_at=self.timestamp,
            generated_by="AEGIS",
            model_versions=DEFAULT_MODEL_VERSIONS,
        )
        html = self.generator.render_html("dossier_template.html", context)
        self.assertIn("DARK GAP", html)
        self.assertIn("UNFLAGGED CONTACT BRAVO", html)

    def test_rule_5_compliance_alternative_hypotheses_required(self) -> None:
        """Constitutional Rule 5: Non-vessel alternatives must be evaluated."""
        with self.assertRaises(ValueError) as ctx:
            self.generator.generate_dossier(
                case_id=self.case_uuid,
                detection=self.detection_fixture,
                characterization=self.characterization_fixture,
                origin=self.origin_fixture,
                candidates=self.candidates_fixture,
                alternatives=[],  # Empty alternatives violates Rule 5
            )
        self.assertIn("Rule 5 Violation", str(ctx.exception))

    def test_rule_6_zero_banned_terms(self) -> None:
        """Constitutional Rule 6: Strictly zero occurrences of banned determination terms."""
        context = self.generator.prepare_template_context(
            case_id=self.case_uuid,
            detection_data=self.detection_fixture,
            characterization_data=self.characterization_fixture,
            origin_data=self.origin_fixture,
            candidates_data=self.candidates_fixture,
            alternatives_data=self.alternatives_fixture,
            environmental_data=self.environmental_fixture,
            sar_chip_b64=None,
            sha256_hash="f" * 64,
            verification_qr_b64="data:image/png;base64,test",
            generated_at=self.timestamp,
            generated_by="AEGIS",
            model_versions=DEFAULT_MODEL_VERSIONS,
        )
        rendered_html = self.generator.render_html("dossier_template.html", context)

        # Run banned terms CI check
        violations = check_content(rendered_html, Path("dossier_rendered.html"))
        self.assertEqual(len(violations), 0, f"Found banned terms: {violations}")

        # Injecting a banned term must raise ValueError
        bad_context = context.copy()
        bad_context["generated_by"] = "Identified responsible vessel tribunal"  # noqa: banned-terms
        with self.assertRaises(ValueError) as ctx:
            self.generator.render_html("dossier_template.html", bad_context)
        self.assertIn("Rule 6 Violation", str(ctx.exception))

    def test_database_persistence(self) -> None:
        """Verify Dossier and AuditLog records are written when db_session is provided."""
        mock_db = MagicMock(spec=Session)

        result = self.generator.generate_dossier(
            case_id=self.case_uuid,
            detection=self.detection_fixture,
            characterization=self.characterization_fixture,
            origin=self.origin_fixture,
            candidates=self.candidates_fixture,
            alternatives=self.alternatives_fixture,
            db_session=mock_db,
            engine="reportlab",
        )

        self.assertIsInstance(result, DossierResult)
        self.assertTrue(mock_db.add.called)
        self.assertEqual(mock_db.add.call_count, 2)  # Dossier + AuditLog
        self.assertTrue(mock_db.commit.called)

        # Inspect added objects
        added_objs = [call[0][0] for call in mock_db.add.call_args_list]
        dossier_records = [o for o in added_objs if isinstance(o, Dossier)]
        audit_records = [o for o in added_objs if isinstance(o, AuditLog)]

        self.assertEqual(len(dossier_records), 1)
        self.assertEqual(len(audit_records), 1)

        dossier_entity = dossier_records[0]
        self.assertEqual(dossier_entity.case_id, self.case_uuid)
        self.assertEqual(dossier_entity.sha256_hash, result.sha256_hash)
        self.assertEqual(dossier_entity.pdf_ref, result.pdf_ref)

        audit_entity = audit_records[0]
        self.assertEqual(audit_entity.case_id, self.case_uuid)
        self.assertEqual(audit_entity.action, "generate_legal_dossier")


if __name__ == "__main__":
    unittest.main()
