"""AEGIS-Marine: Mechanical Spreading Aging Inversion (Fay's Equations).

Implements physical inversion of Fay's three-regime mechanical spreading laws:
1. Gravity-viscous regime:
   r(t) = k2 * ((delta_rho * g * V^2) / nu^(1/2))^(1/6) * t^(1/4)
2. Viscous-surface tension regime:
   r(t) = k3 * (sigma^2 / (rho^2 * nu))^(1/4) * t^(3/4)
3. Direct analytical age inversion:
   t_age = (A_s / (pi * k3^2))^(2/3) * ((rho_w^2 * nu_w) / sigma_net^2)^(1/3)
4. Confidence interval [t_age_min, t_age_max] based on oil property uncertainty bounds.
5. Aging confidence score with exponential decay for t_age > 72h (evaporation/weathering).

References:
- PRD Section 10 & Section 234: Core Mathematical & Physical Basis
- Technical Specification Section 4.2.1: Fay Spreading Model
- AEGIS-Marine_Architecture.md Section 4.2: Tier 2 Service
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# Physical constants for standard marine conditions (seawater + mineral oil)
DEFAULT_SEAWATER_DENSITY_KG_M3: float = 1025.0       # rho_w (kg/m^3)
DEFAULT_OIL_DENSITY_KG_M3: float = 880.0             # rho_o (kg/m^3)
DEFAULT_SEAWATER_VISCOSITY_M2_S: float = 1.05e-6     # nu_w (kinematic viscosity, m^2/s)
DEFAULT_NET_SPREADING_TENSION_N_M: float = 0.030     # sigma_net (interfacial spreading coefficient, N/m)
GRAVITATIONAL_ACCELERATION_M_S2: float = 9.81        # g (m/s^2)

# Fay empirical regime constants (Fay 1971)
FAY_K2_GRAVITY_VISCOUS: float = 1.45                 # k_2
FAY_K3_SURFACE_TENSION: float = 2.30                 # k_3


@dataclass(frozen=True)
class OilSpillPhysicsConstants:
    """Environmental and fluid property parameters for Fay spreading."""

    rho_w: float = DEFAULT_SEAWATER_DENSITY_KG_M3
    rho_o: float = DEFAULT_OIL_DENSITY_KG_M3
    nu_w: float = DEFAULT_SEAWATER_VISCOSITY_M2_S
    sigma_net: float = DEFAULT_NET_SPREADING_TENSION_N_M
    g: float = GRAVITATIONAL_ACCELERATION_M_S2
    k2: float = FAY_K2_GRAVITY_VISCOUS
    k3: float = FAY_K3_SURFACE_TENSION

    @property
    def delta_rho(self) -> float:
        """Fractional density difference: (rho_w - rho_o) / rho_w."""
        return (self.rho_w - self.rho_o) / self.rho_w


@dataclass(frozen=True)
class SpillAgeResult:
    """Physical aging inversion output with uncertainty interval (Rule 1)."""

    t_age_hours: float
    t_age_min_hours: float
    t_age_max_hours: float
    effective_radius_m: float
    regime: str  # "viscous_surface_tension", "gravity_viscous", "transitional"
    regime_transition_hours: float
    confidence: float  # [0.0 - 100.0] (Rule 1 paired confidence)


def compute_effective_radius(area_m2: float) -> float:
    """Compute effective radius from slick surface area.

    Formula: r_eff = sqrt(A / pi)
    """
    if area_m2 <= 0.0:
        raise ValueError(f"Area must be positive, got {area_m2}")
    return math.sqrt(area_m2 / math.pi)


def compute_gravity_viscous_radius(
    t_sec: float,
    volume_m3: float,
    constants: OilSpillPhysicsConstants = OilSpillPhysicsConstants(),
) -> float:
    """Calculate slick radius in Fay's Gravity-Viscous regime (Regime 2).

    Formula:
        r_gv(t) = k2 * ((delta_rho * g * V^2) / nu^(1/2))^(1/6) * t^(1/4)
    """
    if t_sec <= 0.0 or volume_m3 <= 0.0:
        return 0.0
    group = (constants.delta_rho * constants.g * (volume_m3**2)) / math.sqrt(constants.nu_w)
    return constants.k2 * (group ** (1.0 / 6.0)) * (t_sec**0.25)


def compute_surface_tension_radius(
    t_sec: float,
    constants: OilSpillPhysicsConstants = OilSpillPhysicsConstants(),
) -> float:
    """Calculate slick radius in Fay's Viscous-Surface Tension regime (Regime 3).

    Formula:
        r_st(t) = k3 * (sigma^2 / (rho^2 * nu))^(1/4) * t^(3/4)
    """
    if t_sec <= 0.0:
        return 0.0
    group = (constants.sigma_net**2) / ((constants.rho_w**2) * constants.nu_w)
    return constants.k3 * (group**0.25) * (t_sec**0.75)


def compute_regime_transition_time(
    volume_m3: float,
    constants: OilSpillPhysicsConstants = OilSpillPhysicsConstants(),
) -> float:
    """Calculate transition time (seconds) from Gravity-Viscous to Viscous-Surface Tension regime.

    Formula derived from equating r_gv(t_crit) = r_st(t_crit):
        t_crit = (k2 / k3)^2 * ((delta_rho * g * V^2 / nu^(1/2))^(1/3)) / ((sigma^2 / (rho^2 * nu))^(1/2))
    """
    if volume_m3 <= 0.0:
        return 0.0
    gv_term = ((constants.delta_rho * constants.g * (volume_m3**2)) / math.sqrt(constants.nu_w)) ** (1.0 / 3.0)
    st_term = math.sqrt((constants.sigma_net**2) / ((constants.rho_w**2) * constants.nu_w))
    ratio_k = (constants.k2 / constants.k3) ** 2
    return ratio_k * (gv_term / st_term)


def invert_fay_surface_tension_age(
    area_m2: float,
    constants: OilSpillPhysicsConstants = OilSpillPhysicsConstants(),
) -> float:
    """Invert Fay's Viscous-Surface Tension spreading law to calculate spill age in seconds.

    Reference: PRD Section 10 & Technical Specification Section 4.2.1
    Formula:
        t_age = (A_s / (pi * k3^2))^(2/3) * ((rho_w^2 * nu_w) / sigma_net^2)^(1/3)
    """
    if area_m2 <= 0.0:
        raise ValueError(f"Area must be positive, got {area_m2}")

    area_factor = (area_m2 / (math.pi * (constants.k3**2))) ** (2.0 / 3.0)
    fluid_factor = (((constants.rho_w**2) * constants.nu_w) / (constants.sigma_net**2)) ** (1.0 / 3.0)
    return area_factor * fluid_factor


def invert_fay_gravity_viscous_age(
    area_m2: float,
    volume_m3: float,
    constants: OilSpillPhysicsConstants = OilSpillPhysicsConstants(),
) -> float:
    """Invert Fay's Gravity-Viscous spreading law to calculate spill age in seconds.

    Formula:
        t_age = (r_eff / k2)^4 / ((delta_rho * g * V^2) / nu^(1/2))^(2/3)
    """
    if area_m2 <= 0.0 or volume_m3 <= 0.0:
        raise ValueError("Area and volume must both be positive")

    r_eff = compute_effective_radius(area_m2)
    group = (constants.delta_rho * constants.g * (volume_m3**2)) / math.sqrt(constants.nu_w)
    return ((r_eff / constants.k2) ** 4) / (group ** (2.0 / 3.0))


def estimate_spill_age(
    area_m2: float,
    estimated_volume_m3: Optional[float] = None,
    constants: Optional[OilSpillPhysicsConstants] = None,
) -> SpillAgeResult:
    """Estimate elapsed spill age with physical uncertainty bounds and Rule 1 confidence.

    Args:
        area_m2: Segmented slick area in square meters.
        estimated_volume_m3: Optional estimated spill volume (m^3) for regime discrimination.
        constants: Optional custom fluid/environmental constants.

    Returns:
        SpillAgeResult containing nominal t_age (hours), confidence bounds, and Rule 1 score.
    """
    cfg = constants or OilSpillPhysicsConstants()
    r_eff = compute_effective_radius(area_m2)

    # 1. Nominal Age Inversion via Viscous-Surface Tension (Primary Spaceborne SAR Regime)
    t_st_sec = invert_fay_surface_tension_age(area_m2, cfg)
    t_st_hours = t_st_sec / 3600.0

    # 2. Regime Check & Transition Time
    regime = "viscous_surface_tension"
    t_crit_hours = 1.0  # Default nominal transition (~1 hour)

    if estimated_volume_m3 is not None and estimated_volume_m3 > 0.0:
        t_crit_sec = compute_regime_transition_time(estimated_volume_m3, cfg)
        t_crit_hours = t_crit_sec / 3600.0

        if t_st_sec < t_crit_sec:
            # Slick is young and still in the gravity-viscous expansion phase
            try:
                t_gv_sec = invert_fay_gravity_viscous_age(area_m2, estimated_volume_m3, cfg)
                t_age_hours = t_gv_sec / 3600.0
                regime = "gravity_viscous"
            except Exception:
                t_age_hours = t_st_hours
        else:
            t_age_hours = t_st_hours
    else:
        t_age_hours = t_st_hours

    # 3. Uncertainty Interval Bounds [t_min, t_max]
    # Bound parameters:
    # sigma_net varies from 0.018 to 0.038 N/m
    # k3 varies from 1.90 to 2.50
    cfg_fast = OilSpillPhysicsConstants(
        rho_w=cfg.rho_w,
        rho_o=cfg.rho_o,
        nu_w=cfg.nu_w * 0.85,
        sigma_net=0.038,
        k3=2.50,
    )
    cfg_slow = OilSpillPhysicsConstants(
        rho_w=cfg.rho_w,
        rho_o=cfg.rho_o,
        nu_w=cfg.nu_w * 1.25,
        sigma_net=0.018,
        k3=1.90,
    )

    t_min_sec = invert_fay_surface_tension_age(area_m2, cfg_fast)
    t_max_sec = invert_fay_surface_tension_age(area_m2, cfg_slow)

    t_min_hours = max(0.1, t_min_sec / 3600.0)
    t_max_hours = max(t_min_hours * 1.2, t_max_sec / 3600.0)

    # 4. Confidence Score Calculation (Rule 1 & Architecture §4.2)
    # Architecture: "applies confidence decay for t_age > 72h (evaporation/emulsification degrade reliability)"
    if t_age_hours <= 12.0:
        base_conf = 92.0
    elif t_age_hours <= 24.0:
        base_conf = 88.0
    elif t_age_hours <= 48.0:
        base_conf = 78.0
    elif t_age_hours <= 72.0:
        base_conf = 68.0
    else:
        # Exponential confidence decay past 72 hours
        excess_hours = t_age_hours - 72.0
        decay = math.exp(-excess_hours / 48.0)
        base_conf = max(15.0, 68.0 * decay)

    # Small size penalty (< 5000 m^2 has higher edge ambiguity)
    if area_m2 < 5000.0:
        base_conf -= 10.0

    final_confidence = round(max(5.0, min(98.0, base_conf)), 1)

    return SpillAgeResult(
        t_age_hours=round(t_age_hours, 2),
        t_age_min_hours=round(t_min_hours, 2),
        t_age_max_hours=round(t_max_hours, 2),
        effective_radius_m=round(r_eff, 2),
        regime=regime,
        regime_transition_hours=round(t_crit_hours, 2),
        confidence=final_confidence,
    )
