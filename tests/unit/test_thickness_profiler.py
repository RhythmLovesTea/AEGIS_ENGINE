"""Unit tests for Bonn Agreement BAOAC thickness profiler and volumetric estimation (TASK-015)."""

import unittest

from backend.services.tier2_morphometry.thickness_profiler import (
    BAOAC_TABLE,
    BAOACSpec,
    SlickThicknessProfile,
    ThicknessSegment,
    classify_baoac_from_radar_damping,
    compute_segment_volume,
    profile_slick_thickness,
)


class TestThicknessProfiler(unittest.TestCase):
    """Test suite for BAOAC thickness classification and volumetric estimation."""

    def test_baoac_table_specifications(self) -> None:
        """Verify BAOAC specification table parameters match international standards."""
        self.assertEqual(len(BAOAC_TABLE), 5)

        # Code 1: Sheen (0.04 - 0.30 um, nominal 0.15 um)
        c1 = BAOAC_TABLE[1]
        self.assertEqual(c1.name, "Sheen")
        self.assertAlmostEqual(c1.nominal_thickness_um, 0.15)
        self.assertAlmostEqual(c1.nominal_thickness_m, 0.15e-6)

        # Code 2: Rainbow (0.30 - 5.00 um, nominal 2.50 um)
        c2 = BAOAC_TABLE[2]
        self.assertEqual(c2.name, "Rainbow")
        self.assertAlmostEqual(c2.nominal_thickness_um, 2.50)

        # Code 3: Metallic (5.00 - 50.0 um, nominal 25.0 um)
        c3 = BAOAC_TABLE[3]
        self.assertEqual(c3.name, "Metallic")
        self.assertAlmostEqual(c3.nominal_thickness_um, 25.0)

        # Code 4: Discontinuous True Oil (50.0 - 200.0 um, nominal 100.0 um)
        c4 = BAOAC_TABLE[4]
        self.assertEqual(c4.name, "Discontinuous True Oil")
        self.assertAlmostEqual(c4.nominal_thickness_um, 100.0)

        # Code 5: Continuous True Oil (> 200.0 um, nominal 300.0 um)
        c5 = BAOAC_TABLE[5]
        self.assertEqual(c5.name, "Continuous True Oil")
        self.assertAlmostEqual(c5.nominal_thickness_um, 300.0)

    def test_classify_baoac_from_radar_damping(self) -> None:
        """Verify mapping of radar damping ratio to BAOAC codes."""
        self.assertEqual(classify_baoac_from_radar_damping(5.0), 1)   # Sheen
        self.assertEqual(classify_baoac_from_radar_damping(7.5), 2)   # Rainbow
        self.assertEqual(classify_baoac_from_radar_damping(10.0), 3)  # Metallic
        self.assertEqual(classify_baoac_from_radar_damping(13.0), 4)  # Discontinuous True Oil
        self.assertEqual(classify_baoac_from_radar_damping(16.0), 5)  # Continuous True Oil

        # Optical contrast override
        self.assertEqual(classify_baoac_from_radar_damping(8.0, optical_contrast=0.28), 5)
        self.assertEqual(classify_baoac_from_radar_damping(8.0, optical_contrast=0.18), 4)

    def test_compute_segment_volume(self) -> None:
        """Verify analytical volume computation V = Area * Thickness."""
        area = 100000.0  # 100,000 m^2

        # For Code 3: Metallic, nominal 25 um = 2.5e-5 m
        # Expected V_nom = 100,000 * 2.5e-5 = 2.5 m^3
        # Expected V_min = 100,000 * 5.0e-6 = 0.5 m^3
        # Expected V_max = 100,000 * 50.0e-6 = 5.0 m^3
        v_nom, v_min, v_max = compute_segment_volume(area, 3)
        self.assertAlmostEqual(v_nom, 2.5, places=3)
        self.assertAlmostEqual(v_min, 0.5, places=3)
        self.assertAlmostEqual(v_max, 5.0, places=3)

    def test_multi_segment_profiling_and_volume_integration(self) -> None:
        """Verify multi-segment volume integration V_total = sum(A_i * d_i)."""
        sub_segments = [
            {"segment_id": "sheen-tail", "area_m2": 600000.0, "baoac_code": 1},      # 600,000 * 0.15e-6 = 0.09 m^3
            {"segment_id": "rainbow-body", "area_m2": 250000.0, "baoac_code": 2},    # 250,000 * 2.5e-6 = 0.625 m^3
            {"segment_id": "metallic-core", "area_m2": 100000.0, "baoac_code": 3},   # 100,000 * 25e-6 = 2.5 m^3
            {"segment_id": "emulsion-head", "area_m2": 50000.0, "baoac_code": 4},    # 50,000 * 100e-6 = 5.0 m^3
        ]
        total_area = 1000000.0

        profile: SlickThicknessProfile = profile_slick_thickness(
            area_m2=total_area,
            sub_segments=sub_segments,
        )

        expected_total_volume = 0.09 + 0.625 + 2.5 + 5.0  # = 8.215 m^3
        self.assertAlmostEqual(profile.estimated_volume_m3, expected_total_volume, delta=0.01)
        self.assertEqual(len(profile.segments), 4)
        # Dominant code by volume severity is Code 4 (emulsion head has 5.0 m^3)
        self.assertEqual(profile.dominant_baoac_code, 4)
        self.assertLess(profile.volume_min_m3, profile.estimated_volume_m3)
        self.assertGreater(profile.volume_max_m3, profile.estimated_volume_m3)

    def test_empirical_slick_profiling(self) -> None:
        """Verify empirical distribution profiling when sub-segments are not explicitly provided."""
        area = 725100.0  # Benchmark tile area
        profile = profile_slick_thickness(area_m2=area, damping_ratio_db=9.0)

        self.assertEqual(profile.total_area_m2, area)
        self.assertGreater(profile.estimated_volume_m3, 0.0)
        self.assertLess(profile.volume_min_m3, profile.estimated_volume_m3)
        self.assertGreater(profile.volume_max_m3, profile.estimated_volume_m3)
        self.assertIn(profile.dominant_baoac_code, [1, 2, 3, 4, 5])

    def test_rule_1_confidence_scoring(self) -> None:
        """Enforce Rule 1 paired confidence score bounds and multi-sensor enhancement."""
        # Single sensor (SAR only)
        sar_only = profile_slick_thickness(area_m2=100000.0, damping_ratio_db=10.0)
        self.assertGreaterEqual(sar_only.confidence, 70.0)
        self.assertLessEqual(sar_only.confidence, 100.0)

        # Multi-sensor (SAR + optical contrast) should yield higher confidence
        multi_sensor = profile_slick_thickness(
            area_m2=100000.0, damping_ratio_db=10.0, optical_contrast=0.20
        )
        self.assertGreater(multi_sensor.confidence, sar_only.confidence)
        self.assertLessEqual(multi_sensor.confidence, 100.0)

    def test_invalid_area_raises_value_error(self) -> None:
        """Verify non-positive area raises ValueError."""
        with self.assertRaises(ValueError):
            profile_slick_thickness(area_m2=0.0)
        with self.assertRaises(ValueError):
            profile_slick_thickness(area_m2=-100.0)


if __name__ == "__main__":
    unittest.main()
