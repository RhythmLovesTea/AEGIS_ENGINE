"""AEGIS-Marine: Unit Tests for Analytic Hierarchy Process (AHP) Weight Manager.

Tests conform to:
- PRD Section 11 (FR-14, FR-15, C11, D6)
- Architecture Section 4.4
- Constitutional Rules:
  - Rule 6: Strictly zero occurrences of banned terms
  - Rule 7: 'Show your math' - AHP matrix, weights, and consistency ratio inspectable
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backend.app.models.entities import AHPConfig
from backend.app.schemas.vessel import AHPConfigResponse
from backend.services.tier4_correlation.ahp_manager import (
    CANONICAL_CI,
    CANONICAL_CR,
    CANONICAL_LAMBDA_MAX,
    CANONICAL_PAIRWISE_MATRIX,
    CANONICAL_WEIGHTS,
    CRITERIA_KEYS,
    MAX_CONSISTENCY_RATIO,
    SAATY_RI_TABLE,
    AHPWeightManager,
    InconsistentAHPMatrixError,
    compute_ahp_weights,
    default_ahp_manager,
)


class TestAHPWeightManager(unittest.TestCase):
    """Test suite for AHP pairwise weight derivation and Saaty consistency checks."""

    def setUp(self) -> None:
        self.manager = AHPWeightManager(default_version="v1.0")

    def test_canonical_ahp_matrix_and_weights(self) -> None:
        """Verify canonical matrix yields exact PRD/Architecture weights and CR = 0.0094 < 0.10."""
        result = compute_ahp_weights(CANONICAL_PAIRWISE_MATRIX)

        # 1. Verify criteria keys match
        self.assertEqual(result.criteria, CRITERIA_KEYS)

        # 2. Verify exact weights [0.30, 0.25, 0.15, 0.20, 0.10]
        self.assertEqual(result.weights["spatial"], 0.30)
        self.assertEqual(result.weights["temporal"], 0.25)
        self.assertEqual(result.weights["kinematic"], 0.15)
        self.assertEqual(result.weights["anomaly"], 0.20)
        self.assertEqual(result.weights["type"], 0.10)

        # 3. Verify weights sum strictly to 1.0
        total_weight = sum(result.weights.values())
        self.assertAlmostEqual(total_weight, 1.0, places=5)

        # 4. Verify Saaty consistency parameters (PRD Section 11 / TODO.md TASK-026)
        self.assertEqual(result.lambda_max, CANONICAL_LAMBDA_MAX)  # 5.042
        self.assertEqual(result.consistency_index, CANONICAL_CI)  # 0.0105
        self.assertEqual(result.consistency_ratio, CANONICAL_CR)  # 0.0094
        self.assertLess(result.consistency_ratio, MAX_CONSISTENCY_RATIO)  # CR < 0.10
        self.assertTrue(result.is_consistent)

    def test_canonical_config_response_schema(self) -> None:
        """Verify canonical config serializes cleanly to Pydantic AHPConfigResponse."""
        config = self.manager.get_canonical_config()
        self.assertIsInstance(config, AHPConfigResponse)
        self.assertEqual(config.version, "v1.0")
        self.assertEqual(config.weights, CANONICAL_WEIGHTS)
        self.assertEqual(config.consistency_ratio, 0.0094)
        self.assertLess(config.consistency_ratio, 0.10)

    def test_saaty_random_index_table(self) -> None:
        """Verify Saaty Random Index lookup table values."""
        self.assertEqual(SAATY_RI_TABLE[1], 0.00)
        self.assertEqual(SAATY_RI_TABLE[2], 0.00)
        self.assertEqual(SAATY_RI_TABLE[3], 0.58)
        self.assertEqual(SAATY_RI_TABLE[4], 0.90)
        self.assertEqual(SAATY_RI_TABLE[5], 1.12)  # Standard n=5 RI
        self.assertEqual(SAATY_RI_TABLE[6], 1.24)
        self.assertEqual(SAATY_RI_TABLE[7], 1.32)

    def test_eigenvector_derivation_algorithm_on_custom_matrix(self) -> None:
        """Verify Perron-Frobenius eigenvector derivation on perfectly consistent 3x3 matrix."""
        # Perfectly consistent matrix: A_ik = A_ij * A_jk
        # Criteria: [speed, course, draft] with relative ratios [4 : 2 : 1]
        matrix_3x3 = [
            [1.0, 2.0, 4.0],
            [0.5, 1.0, 2.0],
            [0.25, 0.5, 1.0],
        ]
        criteria = ["speed", "course", "draft"]
        result = compute_ahp_weights(matrix_3x3, criteria=criteria)

        # Expected weights: [4/7, 2/7, 1/7] ~ [0.5714, 0.2857, 0.1429]
        self.assertAlmostEqual(result.weights["speed"], 4.0 / 7.0, places=3)
        self.assertAlmostEqual(result.weights["course"], 2.0 / 7.0, places=3)
        self.assertAlmostEqual(result.weights["draft"], 1.0 / 7.0, places=3)
        self.assertAlmostEqual(sum(result.weights.values()), 1.0, places=3)

        # Perfectly consistent matrix has lambda_max = n = 3.0, CI = 0.0, CR = 0.0
        self.assertAlmostEqual(result.lambda_max, 3.0, places=3)
        self.assertAlmostEqual(result.consistency_ratio, 0.0, places=3)
        self.assertTrue(result.is_consistent)

    def test_inconsistent_matrix_rejection(self) -> None:
        """Verify that an inconsistent matrix (CR >= 0.10) raises InconsistentAHPMatrixError."""
        # Highly inconsistent cyclical matrix (A > B > C > A)
        inconsistent_matrix = [
            [1.0, 5.0, 0.2],
            [0.2, 1.0, 5.0],
            [5.0, 0.2, 1.0],
        ]
        # Should raise InconsistentAHPMatrixError when enforce_consistency=True
        with self.assertRaises(InconsistentAHPMatrixError):
            compute_ahp_weights(inconsistent_matrix, enforce_consistency=True)

        # When enforce_consistency=False, returns with is_consistent=False
        result = compute_ahp_weights(inconsistent_matrix, enforce_consistency=False)
        self.assertFalse(result.is_consistent)
        self.assertGreaterEqual(result.consistency_ratio, 0.10)

    def test_matrix_dimension_and_positive_validation(self) -> None:
        """Verify validation errors for non-square or invalid matrices."""
        with self.assertRaises(ValueError):
            compute_ahp_weights([])  # Empty matrix

        with self.assertRaises(ValueError):
            compute_ahp_weights([[1.0, 2.0], [0.5]])  # Non-square matrix

        with self.assertRaises(ValueError):
            compute_ahp_weights([[-1.0, 2.0], [0.5, 1.0]])  # Non-positive entry

    def test_db_persistence_and_retrieval(self) -> None:
        """Verify persistence to and retrieval from AHPConfig entity."""
        mock_session = MagicMock()

        # 1. Test fallback to canonical when DB returns None
        mock_session.query.return_value.filter.return_value.first.return_value = None
        config = self.manager.get_active_config(db_session=mock_session, version="v1.0")
        self.assertEqual(config.version, "v1.0")
        self.assertEqual(config.weights, CANONICAL_WEIGHTS)
        self.assertEqual(config.consistency_ratio, 0.0094)

        # 2. Test loading existing record from DB
        db_entity = AHPConfig(
            version="v2.0-custom",
            pairwise_matrix={"matrix": CANONICAL_PAIRWISE_MATRIX},
            weights={
                "spatial": 0.35,
                "temporal": 0.25,
                "kinematic": 0.15,
                "anomaly": 0.15,
                "type": 0.10,
            },
            consistency_ratio=0.012,
            created_at=datetime.now(UTC),
        )
        mock_session.query.return_value.filter.return_value.first.return_value = db_entity
        custom_config = self.manager.get_active_config(
            db_session=mock_session, version="v2.0-custom"
        )
        self.assertEqual(custom_config.version, "v2.0-custom")
        self.assertEqual(custom_config.weights["spatial"], 0.35)
        self.assertEqual(custom_config.consistency_ratio, 0.012)

        # 3. Test saving config
        new_payload = AHPConfigResponse(
            version="v3.0-test",
            pairwise_matrix=CANONICAL_PAIRWISE_MATRIX,
            weights=CANONICAL_WEIGHTS,
            consistency_ratio=0.0094,
            created_at=datetime.now(UTC),
        )
        mock_session.query.return_value.filter.return_value.first.return_value = None
        saved = self.manager.save_config(new_payload, db_session=mock_session)
        self.assertEqual(saved.version, "v3.0-test")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_singleton_export(self) -> None:
        """Verify default_ahp_manager singleton instance is functional."""
        config = default_ahp_manager.get_canonical_config()
        self.assertEqual(config.weights["spatial"], 0.30)
        self.assertEqual(config.consistency_ratio, 0.0094)


if __name__ == "__main__":
    unittest.main()
