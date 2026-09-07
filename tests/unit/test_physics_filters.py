"""Unit tests for radar backscatter polarimetry and lookalike rejection filters (TASK-010)."""

import math
import unittest

from backend.services.tier1_segmentation.physics_filters import (
    MIN_DAMPING_RATIO_DB_THRESHOLD,
    SENTINEL1_C_BAND_WAVELENGTH_M,
    compute_bragg_wavelength,
    compute_copolarization_difference,
    compute_damping_ratio,
    evaluate_biogenic_vegetation_index,
    evaluate_composite_lookalike,
    evaluate_wind_lookalike_risk,
)


class TestPhysicsFilters(unittest.TestCase):
    """Test suite for SAR polarimetric physics and lookalike rejection filters."""

    def test_bragg_wavelength_calculation(self):
        """Test ocean surface Bragg resonance wavelength calculation."""
        # For Sentinel-1 C-band (~0.055465m) at 35 degrees incidence:
        # lambda_B = 0.055465 / (2 * sin(35 deg)) = 0.055465 / (2 * 0.573576) ~= 0.04835 m (~4.8 cm capillary-gravity wave)
        wavelength_35 = compute_bragg_wavelength(35.0)
        expected_35 = SENTINEL1_C_BAND_WAVELENGTH_M / (2.0 * math.sin(math.radians(35.0)))
        self.assertAlmostEqual(wavelength_35, expected_35, places=5)
        self.assertGreater(wavelength_35, 0.03)
        self.assertLess(wavelength_35, 0.10)

        # Higher incidence angle gives shorter Bragg resonant wave
        wavelength_45 = compute_bragg_wavelength(45.0)
        self.assertLess(wavelength_45, wavelength_35)

        # Invalid angles raise ValueError
        with self.assertRaises(ValueError):
            compute_bragg_wavelength(0.0)
        with self.assertRaises(ValueError):
            compute_bragg_wavelength(90.0)
        with self.assertRaises(ValueError):
            compute_bragg_wavelength(-10.0)

    def test_damping_ratio_analysis(self):
        """Test radar backscatter damping ratio in linear and decibel scale."""
        # Clean background: -8.0 dB, Slick backscatter: -15.0 dB -> DR = 7.0 dB
        res_slick = compute_damping_ratio(sigma0_clean_db=-8.0, sigma0_slick_db=-15.0)
        self.assertEqual(res_slick.dr_db, 7.0)
        self.assertAlmostEqual(res_slick.dr_linear, 5.01, places=1)
        self.assertTrue(res_slick.is_damped)
        self.assertGreaterEqual(res_slick.damping_confidence, 60.0)
        self.assertLessEqual(res_slick.damping_confidence, 100.0)

        # Marginal/weak damping below threshold (e.g. 2.0 dB)
        res_weak = compute_damping_ratio(sigma0_clean_db=-8.0, sigma0_slick_db=-10.0)
        self.assertEqual(res_weak.dr_db, 2.0)
        self.assertFalse(res_weak.is_damped)
        self.assertLess(res_weak.damping_confidence, 60.0)

        # Inverted or zero damping
        res_inverted = compute_damping_ratio(sigma0_clean_db=-15.0, sigma0_slick_db=-10.0)
        self.assertFalse(res_inverted.is_damped)
        self.assertEqual(res_inverted.damping_confidence, 0.0)

    def test_copolarization_difference(self):
        """Test co-polarization difference calculation."""
        # Linear values
        pd = compute_copolarization_difference(sigma0_vv_linear=0.08, sigma0_hh_linear=0.05)
        self.assertAlmostEqual(pd, 0.03, places=5)

    def test_wind_lookalike_risk(self):
        """Test environmental wind speed operational window limits."""
        # Low wind calm sea (1.5 m/s < 3.0 m/s threshold)
        risk_calm, reason_calm = evaluate_wind_lookalike_risk(1.5)
        self.assertGreater(risk_calm, 0.0)
        self.assertEqual(reason_calm, "low_wind_calm_water_lookalike")

        # Zero wind -> maximum risk
        risk_zero, _ = evaluate_wind_lookalike_risk(0.0)
        self.assertEqual(risk_zero, 1.0)

        # Optimal wind (6.5 m/s) -> 0 risk
        risk_optimal, reason_opt = evaluate_wind_lookalike_risk(6.5)
        self.assertEqual(risk_optimal, 0.0)
        self.assertEqual(reason_opt, "optimal_wind_conditions")

        # Moderate wind (13.0 m/s) -> moderate damping loss
        risk_mod, reason_mod = evaluate_wind_lookalike_risk(13.0)
        self.assertGreater(risk_mod, 0.0)
        self.assertEqual(reason_mod, "moderate_wind_damping_loss")

        # High wind (16.0 m/s > 14.0 m/s) -> high dispersion risk
        risk_high, reason_high = evaluate_wind_lookalike_risk(16.0)
        self.assertGreater(risk_high, 0.0)
        self.assertEqual(reason_high, "high_wind_dispersion")

    def test_biogenic_vegetation_discrimination(self):
        """Test optical NDVI and FAI vegetation index biogenic rejection."""
        # Case 1: Algal bloom (high NIR reflectance relative to RED)
        # Red: 0.04, NIR: 0.12 -> NDVI = (0.12 - 0.04) / 0.16 = 0.50 (bloom)
        ndvi_bloom, fai_bloom, is_bloom = evaluate_biogenic_vegetation_index(
            red_reflectance_b4=0.04,
            nir_reflectance_b8=0.12,
            swir1_reflectance_b11=0.02,
        )
        self.assertAlmostEqual(ndvi_bloom, 0.5, places=2)
        self.assertTrue(is_bloom)
        self.assertIsNotNone(fai_bloom)

        # Case 2: Mineral oil / clean water (low NIR reflectance, negative or very low NDVI)
        # Red: 0.05, NIR: 0.03 -> NDVI = -0.25 (not biogenic)
        ndvi_clean, fai_clean, is_clean = evaluate_biogenic_vegetation_index(
            red_reflectance_b4=0.05,
            nir_reflectance_b8=0.03,
            swir1_reflectance_b11=0.01,
        )
        self.assertLess(ndvi_clean, 0.15)
        self.assertFalse(is_clean)

    def test_composite_lookalike_genuine_slick(self):
        """Test composite evaluation for a genuine high-confidence oil spill."""
        # Strong damping (7.5 dB), optimal wind (6.0 m/s), low NIR (no algae)
        result = evaluate_composite_lookalike(
            sigma0_clean_db=-7.5,
            sigma0_slick_db=-15.0,
            incidence_angle_deg=34.0,
            wind_speed_mps=6.0,
            red_b4=0.04,
            nir_b8=0.02,
            swir1_b11=0.01,
        )
        self.assertFalse(result.is_rejected)
        self.assertEqual(result.primary_risk_factor, "none")
        self.assertEqual(result.lookalike_risk, 0.0)
        self.assertGreaterEqual(result.detection_confidence, 70.0)
        self.assertEqual(result.dr_db, 7.5)
        self.assertGreater(result.bragg_wavelength_m, 0.04)

    def test_composite_lookalike_calm_water_rejected(self):
        """Test composite evaluation rejecting calm water lookalike."""
        # Low damping (2.0 dB), calm wind (1.0 m/s)
        result = evaluate_composite_lookalike(
            sigma0_clean_db=-10.0,
            sigma0_slick_db=-12.0,
            incidence_angle_deg=35.0,
            wind_speed_mps=1.0,
        )
        self.assertTrue(result.is_rejected)
        self.assertGreater(result.lookalike_risk, 0.5)
        self.assertLess(result.detection_confidence, 40.0)

    def test_composite_lookalike_algal_bloom_rejected(self):
        """Test composite evaluation rejecting biogenic algal bloom."""
        # Good damping but strong algal vegetation contrast
        result = evaluate_composite_lookalike(
            sigma0_clean_db=-7.0,
            sigma0_slick_db=-14.0,
            incidence_angle_deg=35.0,
            wind_speed_mps=7.0,
            red_b4=0.03,
            nir_b8=0.15,  # High NIR
            swir1_b11=0.02,
        )
        self.assertTrue(result.is_rejected)
        self.assertEqual(result.primary_risk_factor, "biogenic_algal_bloom")
        self.assertGreater(result.lookalike_risk, 0.6)


if __name__ == "__main__":
    unittest.main()
