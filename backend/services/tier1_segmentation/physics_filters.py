"""AEGIS-Marine: Radar Backscatter Polarimetry & Lookalike Rejection Physics.

Implements physical diagnostic algorithms for spaceborne oil spill discrimination:
1. Bragg resonance capillary-gravity wave scattering condition (PRD Section 10, Spec 4.1.1).
2. Radar damping ratio (DR) and co-polarization difference (PD) (Spec 4.1.2, 4.1.3).
3. Wind-speed operational window and calm-water lookalike rejection (Spec 4.1.5).
4. Multispectral optical biogenic discrimination (NDVI & FAI) (Spec 4.2.2, 4.2.3).
5. Composite lookalike risk scoring and detection confidence calculation (Rule 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# Sentinel-1 C-band radar wavelength (meters)
SENTINEL1_C_BAND_WAVELENGTH_M: float = 0.055465  # ~5.55 cm

# Minimum damping ratio threshold for mineral hydrocarbons (dB)
MIN_DAMPING_RATIO_DB_THRESHOLD: float = 4.5

# Operational wind speed limits for reliable SAR contrast (m/s)
MIN_OPERATIONAL_WIND_SPEED_MPS: float = 3.0
MAX_OPERATIONAL_WIND_SPEED_MPS: float = 14.0
OPTIMAL_MAX_WIND_SPEED_MPS: float = 12.0


@dataclass(frozen=True)
class DampingAnalysisResult:
    """Output of radar backscatter damping ratio analysis."""

    dr_db: float
    dr_linear: float
    is_damped: bool
    damping_confidence: float  # [0.0 - 100.0]


@dataclass(frozen=True)
class LookalikeDiagnosticResult:
    """Composite lookalike risk assessment and diagnostic breakdown."""

    lookalike_risk: float  # [0.0 - 1.0]
    detection_confidence: float  # [0.0 - 100.0] (Rule 1)
    is_rejected: bool
    primary_risk_factor: str
    dr_db: float
    bragg_wavelength_m: float
    ndvi: Optional[float] = None
    fai: Optional[float] = None


def compute_bragg_wavelength(
    incidence_angle_deg: float,
    radar_wavelength_m: float = SENTINEL1_C_BAND_WAVELENGTH_M,
) -> float:
    """Compute ocean surface Bragg resonance wavelength.

    Reference: PRD Section 10 & Technical Specification Section 4.1.1
    Formula: lambda_B = lambda_r / (2 * sin(theta_i))

    Args:
        incidence_angle_deg: Radar incidence angle in degrees [15.0 - 60.0].
        radar_wavelength_m: Radar carrier wavelength in meters (default Sentinel-1 C-band).

    Returns:
        Resonant ocean wave wavelength lambda_B in meters.
    """
    if incidence_angle_deg <= 0.0 or incidence_angle_deg >= 90.0:
        raise ValueError(f"Incidence angle must be between 0 and 90 degrees, got {incidence_angle_deg}")

    theta_rad = math.radians(incidence_angle_deg)
    sin_theta = math.sin(theta_rad)
    return radar_wavelength_m / (2.0 * sin_theta)


def compute_damping_ratio(
    sigma0_clean_db: float,
    sigma0_slick_db: float,
    threshold_db: float = MIN_DAMPING_RATIO_DB_THRESHOLD,
) -> DampingAnalysisResult:
    """Compute radar backscatter damping ratio between clean sea and oil slick.

    Reference: Technical Specification Section 4.1.3
    Formula: DR_linear = sigma0_clean / sigma0_slick
             DR_db = sigma0_clean_db - sigma0_slick_db

    Args:
        sigma0_clean_db: Background ocean clutter backscatter in dB.
        sigma0_slick_db: Depressed slick backscatter in dB.
        threshold_db: Minimum damping required for mineral oil classification (nominal 4.5 dB).

    Returns:
        DampingAnalysisResult with linear DR, dB DR, and confidence score.
    """
    dr_db = sigma0_clean_db - sigma0_slick_db
    dr_linear = math.pow(10.0, dr_db / 10.0)
    is_damped = dr_db >= threshold_db

    # Confidence scaling: 4.5 dB -> 60%, 10 dB -> 95%
    if dr_db <= 0.0:
        damping_conf = 0.0
    elif dr_db < threshold_db:
        damping_conf = (dr_db / threshold_db) * 50.0
    else:
        # Bounded between 60% and 98%
        excess = min(1.0, (dr_db - threshold_db) / 6.0)
        damping_conf = 60.0 + excess * 38.0

    return DampingAnalysisResult(
        dr_db=round(dr_db, 2),
        dr_linear=round(dr_linear, 2),
        is_damped=is_damped,
        damping_confidence=round(damping_conf, 1),
    )


def compute_copolarization_difference(
    sigma0_vv_linear: float,
    sigma0_hh_linear: float,
) -> float:
    """Compute Co-Polarization Difference (PD) for dual-pol SAR scenes.

    Reference: Technical Specification Section 4.1.2
    Formula: PD = sigma0_vv - sigma0_hh
    """
    return sigma0_vv_linear - sigma0_hh_linear


def evaluate_wind_lookalike_risk(wind_speed_mps: float) -> Tuple[float, str]:
    """Evaluate lookalike risk due to environmental wind conditions.

    Reference: Technical Specification Section 4.1.5
    - U10 < 3.0 m/s: Low-wind calm water / mirror surface generates dark lookalike patches.
    - U10 > 14.0 m/s: Severe wave breaking disperses oil into the column.
    - 3.0 <= U10 <= 12.0 m/s: Optimal detection window.

    Returns:
        Tuple of (risk_score [0.0 - 1.0], descriptive_reason).
    """
    if wind_speed_mps < MIN_OPERATIONAL_WIND_SPEED_MPS:
        # Low wind calm sea: risk scales linearly from 1.0 (at 0 m/s) to 0.0 (at 3 m/s)
        risk = max(0.0, min(1.0, 1.0 - (wind_speed_mps / MIN_OPERATIONAL_WIND_SPEED_MPS)))
        return risk, "low_wind_calm_water_lookalike"

    if wind_speed_mps > MAX_OPERATIONAL_WIND_SPEED_MPS:
        # High wind dispersion: risk scales up above 14 m/s
        excess = min(1.0, (wind_speed_mps - MAX_OPERATIONAL_WIND_SPEED_MPS) / 6.0)
        return excess, "high_wind_dispersion"

    if wind_speed_mps > OPTIMAL_MAX_WIND_SPEED_MPS:
        # Moderate degradation between 12 and 14 m/s
        risk = (wind_speed_mps - OPTIMAL_MAX_WIND_SPEED_MPS) / 2.0 * 0.35
        return risk, "moderate_wind_damping_loss"

    return 0.0, "optimal_wind_conditions"


def evaluate_biogenic_vegetation_index(
    red_reflectance_b4: float,
    nir_reflectance_b8: float,
    swir1_reflectance_b11: Optional[float] = None,
) -> Tuple[float, Optional[float], bool]:
    """Calculate NDVI and FAI to reject biogenic surfactants and algal blooms.

    Reference: Technical Specification Section 4.2.2 & 4.2.3
    Formula: NDVI = (NIR - RED) / (NIR + RED + epsilon)
             FAI = NIR - (RED + (SWIR1 - RED) * (lambda_NIR - lambda_RED) / (lambda_SWIR1 - lambda_RED))

    Args:
        red_reflectance_b4: Sentinel-2 Band 4 (665 nm) surface reflectance.
        nir_reflectance_b8: Sentinel-2 Band 8 (842 nm) surface reflectance.
        swir1_reflectance_b11: Sentinel-2 Band 11 (1610 nm) surface reflectance (optional).

    Returns:
        Tuple of (ndvi, fai, is_biogenic_lookalike).
    """
    denom = nir_reflectance_b8 + red_reflectance_b4 + 1e-6
    ndvi = (nir_reflectance_b8 - red_reflectance_b4) / denom

    fai = None
    if swir1_reflectance_b11 is not None:
        # Sentinel-2 wavelengths: RED=665nm, NIR=842nm, SWIR1=1610nm
        # Baseline slope fraction: (842 - 665) / (1610 - 665) = 177 / 945 ~= 0.1873
        slope_frac = (842.0 - 665.0) / (1610.0 - 665.0)
        baseline = red_reflectance_b4 + (swir1_reflectance_b11 - red_reflectance_b4) * slope_frac
        fai = nir_reflectance_b8 - baseline

    # Biogenic threshold: Algal blooms exhibit positive vegetation contrast (NDVI > 0.15 or FAI > 0.05)
    is_biogenic = (ndvi > 0.15) or (fai is not None and fai > 0.05)

    return round(ndvi, 3), round(fai, 4) if fai is not None else None, is_biogenic


def evaluate_composite_lookalike(
    sigma0_clean_db: float,
    sigma0_slick_db: float,
    incidence_angle_deg: float = 35.0,
    wind_speed_mps: float = 6.5,
    red_b4: Optional[float] = None,
    nir_b8: Optional[float] = None,
    swir1_b11: Optional[float] = None,
) -> LookalikeDiagnosticResult:
    """Compute overall lookalike risk and detection confidence.

    Enforces Rule 1 (explicit paired confidence) and PRD Section 17.
    """
    # 1. Bragg condition
    lambda_b = compute_bragg_wavelength(incidence_angle_deg)

    # 2. Damping ratio
    damping_res = compute_damping_ratio(sigma0_clean_db, sigma0_slick_db)

    # 3. Wind risk
    wind_risk, wind_reason = evaluate_wind_lookalike_risk(wind_speed_mps)

    # 4. Biogenic optical check (if optical bands present)
    is_biogenic = False
    ndvi_val = None
    fai_val = None
    if red_b4 is not None and nir_b8 is not None:
        ndvi_val, fai_val, is_biogenic = evaluate_biogenic_vegetation_index(red_b4, nir_b8, swir1_b11)

    # 5. Composite lookalike risk
    risk_factors = []
    composite_risk = 0.0

    if not damping_res.is_damped:
        damping_deficit = max(0.0, (MIN_DAMPING_RATIO_DB_THRESHOLD - damping_res.dr_db) / MIN_DAMPING_RATIO_DB_THRESHOLD)
        composite_risk += 0.50 * damping_deficit
        risk_factors.append("insufficient_damping")

    if wind_risk > 0.0:
        composite_risk += 0.40 * wind_risk
        risk_factors.append(wind_reason)

    if is_biogenic:
        composite_risk += 0.70
        risk_factors.append("biogenic_algal_bloom")

    composite_risk = min(1.0, max(0.0, composite_risk))
    primary_factor = risk_factors[0] if risk_factors else "none"

    # Detection confidence: decreases as lookalike risk increases
    detection_conf = max(0.0, min(100.0, damping_res.damping_confidence * (1.0 - composite_risk * 0.85)))

    # Reject if composite risk is high (>= 0.50), biogenic detected, or wind below operational 3 m/s limit
    is_rejected = (composite_risk >= 0.50) or is_biogenic or (wind_speed_mps < MIN_OPERATIONAL_WIND_SPEED_MPS)

    return LookalikeDiagnosticResult(
        lookalike_risk=round(composite_risk, 3),
        detection_confidence=round(detection_conf, 1),
        is_rejected=is_rejected,
        primary_risk_factor=primary_factor,
        dr_db=damping_res.dr_db,
        bragg_wavelength_m=round(lambda_b, 4),
        ndvi=ndvi_val,
        fai=fai_val,
    )
