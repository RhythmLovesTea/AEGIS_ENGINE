"""Unit tests for Fay mechanical spreading laws and spill age inversion (TASK-014)."""

import math
import unittest

from backend.services.tier2_morphometry.spreading_aging import (
    DEFAULT_NET_SPREADING_TENSION_N_M,
    DEFAULT_OIL_DENSITY_KG_M3,
    DEFAULT_SEAWATER_DENSITY_KG_M3,
    DEFAULT_SEAWATER_VISCOSITY_M2_S,
    FAY_K2_GRAVITY_VISCOUS,
    FAY_K3_SURFACE_TENSION,
    OilSpillPhysicsConstants,
    SpillAgeResult,
    compute_effective_radius,
    compute_gravity_viscous_radius,
    compute_regime_transition_time,
    compute_surface_tension_radius,
    estimate_spill_age,
    invert_fay_gravity_viscous_age,
    invert_fay_surface_tension_age,
)


class TestSpreadingAging(unittest.TestCase):
    """Test suite for Fay spreading aging inversion algorithms."""

    def setUp(self) -> None:
        self.constants = OilSpillPhysicsConstants()

    def test_effective_radius_calculation(self) -> None:
        """Test effective radius calculation from known circle area."""
        # A = pi * r^2 -> for r = 100.0 m, A = 10000 * pi
        area = math.pi * (100.0**2)
        r_eff = compute_effective_radius(area)
        self.assertAlmostEqual(r_eff, 100.0, places=4)

        # Invalid zero or negative area raises ValueError
        with self.assertRaises(ValueError):
            compute_effective_radius(0.0)
        with self.assertRaises(ValueError):
            compute_effective_radius(-500.0)

    def test_hand_computed_benchmark_surface_tension_inversion(self) -> None:
        """Compare code output with analytical hand-computed benchmark values.

        Benchmark scenario:
            A_s = 1.0 km^2 = 1,000,000 m^2
            k_3 = 2.30
            rho_w = 1025.0 kg/m^3
            nu_w = 1.05e-6 m^2/s
            sigma_net = 0.03 N/m

        Analytical Derivation:
            factor1 = (1,000,000 / (pi * 2.30^2))^(2/3) ~= 1535.5465
            factor2 = ((1025^2 * 1.05e-6) / 0.03^2)^(1/3) ~= 10.7020
            t_sec = 1535.5465 * 10.7020 = 16,433.41 s
            t_hours = 16,433.41 / 3600 = 4.5648 h ~= 4.56 h
        """
        area_m2 = 1.0e6
        expected_t_sec = 16433.41
        expected_t_hours = 4.56

        t_sec = invert_fay_surface_tension_age(area_m2, self.constants)
        self.assertAlmostEqual(t_sec, expected_t_sec, delta=1.0)

        result: SpillAgeResult = estimate_spill_age(area_m2, constants=self.constants)
        self.assertAlmostEqual(result.t_age_hours, expected_t_hours, delta=0.02)
        self.assertAlmostEqual(result.effective_radius_m, 564.19, delta=0.1)

    def test_forward_inverse_surface_tension_consistency(self) -> None:
        """Verify mathematical roundtrip: r_st(t_inv(A)) == r_eff(A)."""
        area_m2 = 725100.0  # Measured from benchmark synthetic tile
        r_eff = compute_effective_radius(area_m2)

        t_sec = invert_fay_surface_tension_age(area_m2, self.constants)
        r_forward = compute_surface_tension_radius(t_sec, self.constants)

        self.assertAlmostEqual(r_forward, r_eff, places=3)

    def test_gravity_viscous_forward_and_inverse_consistency(self) -> None:
        """Verify forward and inverse relations in Fay's Gravity-Viscous regime (Regime 2)."""
        volume_m3 = 50.0
        area_m2 = 40000.0
        r_eff = compute_effective_radius(area_m2)

        t_gv_sec = invert_fay_gravity_viscous_age(area_m2, volume_m3, self.constants)
        self.assertGreater(t_gv_sec, 0.0)

        r_forward = compute_gravity_viscous_radius(t_gv_sec, volume_m3, self.constants)
        self.assertAlmostEqual(r_forward, r_eff, places=3)

    def test_regime_transition_time(self) -> None:
        """Test calculation of transition time between Gravity-Viscous and Surface Tension."""
        volume_m3 = 100.0
        t_crit_sec = compute_regime_transition_time(volume_m3, self.constants)
        t_crit_hours = t_crit_sec / 3600.0

        # For 100 m^3 oil spill, transition is typically between 0.5 and 2.5 hours
        self.assertGreater(t_crit_hours, 0.5)
        self.assertLess(t_crit_hours, 2.5)

    def test_uncertainty_bounds(self) -> None:
        """Verify uncertainty interval satisfies t_min < t_nominal < t_max."""
        area_m2 = 500000.0
        result = estimate_spill_age(area_m2)

        self.assertLess(result.t_age_min_hours, result.t_age_hours)
        self.assertGreater(result.t_age_max_hours, result.t_age_hours)

    def test_rule_1_confidence_and_decay_past_72h(self) -> None:
        """Enforce Rule 1 paired confidence and architecture-mandated confidence decay past 72h."""
        # 1. Fresh spill (< 24h) -> High confidence (>= 85%)
        fresh_spill = estimate_spill_age(area_m2=200000.0)  # ~1.8h
        self.assertGreaterEqual(fresh_spill.confidence, 85.0)
        self.assertLessEqual(fresh_spill.confidence, 100.0)

        # 2. Weathered spill (> 72h) -> Decayed confidence (< 65%)
        # Large area: 100 km^2 -> t_age > 100 hours
        weathered_spill = estimate_spill_age(area_m2=1.0e8)
        self.assertGreater(weathered_spill.t_age_hours, 72.0)
        self.assertLess(weathered_spill.confidence, 65.0)
        self.assertGreaterEqual(weathered_spill.confidence, 10.0)


if __name__ == "__main__":
    unittest.main()
