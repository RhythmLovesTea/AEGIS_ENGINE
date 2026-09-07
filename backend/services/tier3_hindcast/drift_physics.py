"""AEGIS-Marine: Total Drift Velocity Engine (Currents + Wind Drift + Stokes Drift).

Implements Tier 3 Hydrodynamic Forcing Composition:
1. Three-component drift velocity vector composition (PRD Section 10):
   u_drift = u_current + c_w * R(theta_w) * u_wind + u_stokes
2. Wind drift factor: c_w in [0.025, 0.035] (nominal 0.030, 3.0%).
3. Coriolis deflection rotation matrix R(theta_w):
   - Northern Hemisphere (lat > 0): theta_w in [+10°, +15°] (clockwise / right of wind).
   - Southern Hemisphere (lat < 0): theta_w in [-10°, -15°] (counter-clockwise / left of wind).
   - Equatorial zone (lat ~ 0): decays smoothly to 0°.
4. Stokes wave drift: u_stokes ≈ 0.012 * u_wind when wave spectra are not directly provided.
5. Continuous spatial-temporal point evaluation, vectorized particle ensemble evaluation (N >= 10,000),
   and 3D/4D grid field computation over xarray datasets.

Adheres to:
- PRD Section 10 & Technical Specification formulas.
- Rule 1: Mandatory confidence score in [0.0, 100.0] on all outputs.
- Rule 4: Data source identification ("live" | "cached" | "synthetic").
- Rule 6: Zero occurrences of banned terms.
- Rules Section 3.1: Inline formula citations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import numpy as np
import xarray as xr

from backend.services.data_adapters.metocean_adapter import (
    MetoceanVelocityPoint,
    calculate_current_bearing,
    sample_forcing,
    sample_forcing_vectorized,
    standardize_dataset_coords,
)


@dataclass
class DriftConfig:
    """Hydrodynamic drift physical parameters and configuration.

    Cites PRD Section 10:
    - Wind drag factor c_w in [0.025, 0.035] (nominal 0.030).
    - Coriolis deflection theta_w in [10°, 15°] (nominal 12°).
    - Stokes wave drift factor c_stokes ≈ 0.012.
    """

    wind_drift_factor: float = 0.030  # c_w: 3.0% nominal wind drag
    coriolis_deflection_deg: float = 12.0  # theta_w: nominal deflection magnitude
    stokes_drift_factor: float = 0.012  # c_stokes: 1.2% empirical wind-to-Stokes ratio
    equator_decay_lat_deg: float = 2.0  # Latitude transition width near equator


@dataclass
class DriftVectorComponent:
    """Individual velocity vector component (current, wind-drift, or Stokes wave drift)."""

    u: float  # Zonal component (m/s, East positive)
    v: float  # Meridional component (m/s, North positive)
    speed_mps: float  # Magnitude (m/s)
    bearing_deg: float  # Direction towards which vector points (0-360 deg)


@dataclass
class DriftUncertaintyInterval:
    """Bounded physical uncertainty interval for total drift velocity."""

    speed_min_mps: float  # Evaluated at c_w_min (0.025)
    speed_max_mps: float  # Evaluated at c_w_max (0.035)
    bearing_min_deg: float  # Minimum bearing angle
    bearing_max_deg: float  # Maximum bearing angle
    confidence_pct: float  # Rule 1: [0.0 - 100.0]


@dataclass
class DriftVelocityResult:
    """Comprehensive total drift velocity result with decomposed physical components.

    PRD Section 10:
    u_drift = u_current + c_w * R(theta_w) * u_wind + u_stokes
    """

    u_drift: float  # Total zonal drift velocity (m/s)
    v_drift: float  # Total meridional drift velocity (m/s)
    drift_speed_mps: float  # Total drift speed magnitude (m/s)
    drift_bearing_deg: float  # Direction towards which slick drifts (0-360 deg)
    current: DriftVectorComponent  # Ambient ocean current component
    wind_drift: DriftVectorComponent  # Wind-driven Ekman drift component with Coriolis deflection
    stokes_drift: DriftVectorComponent  # Wave-induced Stokes drift component
    wind_drift_factor: float  # Applied c_w
    coriolis_deflection_deg: float  # Applied deflection angle theta_w
    stokes_drift_factor: float  # Applied c_stokes
    lon: float  # Longitude (degrees East)
    lat: float  # Latitude (degrees North)
    timestamp: datetime  # Timestamp in UTC
    confidence_pct: float  # Rule 1: Mandatory confidence score in [0.0, 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4
    uncertainty: DriftUncertaintyInterval | None = None


def get_coriolis_deflection_angle(
    lat: float,
    nominal_deg: float = 12.0,
    equator_transition_deg: float = 2.0,
) -> float:
    """Calculates Coriolis deflection angle theta_w based on latitude.

    Convention (PRD Section 10 & Architecture Section 4.3):
    - Northern Hemisphere (lat > 0): theta_w > 0 (clockwise / to the right of wind).
    - Southern Hemisphere (lat < 0): theta_w < 0 (counter-clockwise / to the left of wind).
    - Equator (lat ~ 0): smoothly decays to 0 via hyperbolic tangent taper.
    """
    if equator_transition_deg <= 0.0:
        if lat > 0:
            return nominal_deg
        elif lat < 0:
            return -nominal_deg
        return 0.0

    # Smooth physical taper across the equatorial doldrums
    taper = math.tanh(lat / equator_transition_deg)
    return round(nominal_deg * taper, 4)


def apply_coriolis_rotation(
    u: float,
    v: float,
    deflection_deg: float,
) -> tuple[float, float]:
    """Rotates a 2D vector by deflection_deg.

    Convention:
    - Positive angle: Clockwise rotation (right of vector, Northern Hemisphere).
    - Negative angle: Counter-clockwise rotation (left of vector, Southern Hemisphere).

    Formula:
    [u'] = [ cos(theta)   sin(theta) ] [u]
    [v'] = [-sin(theta)   cos(theta) ] [v]
    """
    theta_rad = math.radians(deflection_deg)
    cos_th = math.cos(theta_rad)
    sin_th = math.sin(theta_rad)

    u_rot = u * cos_th + v * sin_th
    v_rot = -u * sin_th + v * cos_th
    return u_rot, v_rot


def calculate_drift_vector(
    u_curr: float,
    v_curr: float,
    u_wind: float,
    v_wind: float,
    lat: float,
    u_stokes: float | None = None,
    v_stokes: float | None = None,
    config: DriftConfig | None = None,
) -> tuple[float, float, DriftVectorComponent, DriftVectorComponent, DriftVectorComponent, float]:
    """Computes total drift velocity components from current, wind, and Stokes waves.

    Formula (PRD Section 10):
    u_drift = u_current + c_w * R(theta_w) * u_wind + u_stokes
    """
    cfg = config or DriftConfig()

    # 1. Ambient current component
    curr_speed = math.hypot(u_curr, v_curr)
    curr_bearing = calculate_current_bearing(u_curr, v_curr)
    curr_comp = DriftVectorComponent(
        u=round(u_curr, 4),
        v=round(v_curr, 4),
        speed_mps=round(curr_speed, 4),
        bearing_deg=round(curr_bearing, 2),
    )

    # 2. Wind drift component with Coriolis deflection
    theta_w = get_coriolis_deflection_angle(
        lat=lat,
        nominal_deg=cfg.coriolis_deflection_deg,
        equator_transition_deg=cfg.equator_decay_lat_deg,
    )
    u_wind_rot, v_wind_rot = apply_coriolis_rotation(u_wind, v_wind, theta_w)
    u_wind_drift = cfg.wind_drift_factor * u_wind_rot
    v_wind_drift = cfg.wind_drift_factor * v_wind_rot
    wind_drift_speed = math.hypot(u_wind_drift, v_wind_drift)
    wind_drift_bearing = calculate_current_bearing(u_wind_drift, v_wind_drift)
    wind_comp = DriftVectorComponent(
        u=round(u_wind_drift, 4),
        v=round(v_wind_drift, 4),
        speed_mps=round(wind_drift_speed, 4),
        bearing_deg=round(wind_drift_bearing, 2),
    )

    # 3. Stokes wave drift component
    if u_stokes is None or v_stokes is None:
        # PRD Section 10 & TODO line 343: Kenyon/Rascle empirical Stokes drift from 10m wind
        u_st = cfg.stokes_drift_factor * u_wind
        v_st = cfg.stokes_drift_factor * v_wind
    else:
        u_st = u_stokes
        v_st = v_stokes

    stokes_speed = math.hypot(u_st, v_st)
    stokes_bearing = calculate_current_bearing(u_st, v_st)
    stokes_comp = DriftVectorComponent(
        u=round(u_st, 4),
        v=round(v_st, 4),
        speed_mps=round(stokes_speed, 4),
        bearing_deg=round(stokes_bearing, 2),
    )

    # 4. Total hydrodynamic drift composition
    u_drift = u_curr + u_wind_drift + u_st
    v_drift = v_curr + v_wind_drift + v_st

    return u_drift, v_drift, curr_comp, wind_comp, stokes_comp, theta_w


class DriftPhysicsEngine:
    """Orchestrates total drift velocity composition and interpolation over forcing grids."""

    def __init__(self, config: DriftConfig | None = None) -> None:
        self.config = config or DriftConfig()

    def evaluate_vectors(
        self,
        u_curr: float,
        v_curr: float,
        u_wind: float,
        v_wind: float,
        lat: float,
        lon: float = 0.0,
        timestamp: datetime | None = None,
        u_stokes: float | None = None,
        v_stokes: float | None = None,
        confidence_pct: float = 85.0,
        data_source: Literal["live", "cached", "synthetic"] = "synthetic",
        include_uncertainty: bool = True,
    ) -> DriftVelocityResult:
        """Evaluates drift velocity from explicit numerical current and wind vectors."""
        u_drift, v_drift, curr_c, wind_c, stokes_c, theta_w = calculate_drift_vector(
            u_curr=u_curr,
            v_curr=v_curr,
            u_wind=u_wind,
            v_wind=v_wind,
            lat=lat,
            u_stokes=u_stokes,
            v_stokes=v_stokes,
            config=self.config,
        )

        drift_speed = math.hypot(u_drift, v_drift)
        drift_bearing = calculate_current_bearing(u_drift, v_drift)
        ts = timestamp or datetime.now(UTC)

        uncertainty_interval: DriftUncertaintyInterval | None = None
        if include_uncertainty:
            # Physical uncertainty over c_w in [0.025, 0.035] (PRD Section 10)
            cfg_min = DriftConfig(
                wind_drift_factor=0.025,
                coriolis_deflection_deg=self.config.coriolis_deflection_deg,
                stokes_drift_factor=self.config.stokes_drift_factor,
            )
            cfg_max = DriftConfig(
                wind_drift_factor=0.035,
                coriolis_deflection_deg=self.config.coriolis_deflection_deg,
                stokes_drift_factor=self.config.stokes_drift_factor,
            )

            u_min, v_min, _, _, _, _ = calculate_drift_vector(
                u_curr, v_curr, u_wind, v_wind, lat, u_stokes, v_stokes, cfg_min
            )
            u_max, v_max, _, _, _, _ = calculate_drift_vector(
                u_curr, v_curr, u_wind, v_wind, lat, u_stokes, v_stokes, cfg_max
            )

            speed_min = math.hypot(u_min, v_min)
            speed_max = math.hypot(u_max, v_max)
            bear_min = calculate_current_bearing(u_min, v_min)
            bear_max = calculate_current_bearing(u_max, v_max)

            uncertainty_interval = DriftUncertaintyInterval(
                speed_min_mps=round(min(speed_min, speed_max), 4),
                speed_max_mps=round(max(speed_min, speed_max), 4),
                bearing_min_deg=round(min(bear_min, bear_max), 2),
                bearing_max_deg=round(max(bear_min, bear_max), 2),
                confidence_pct=round(confidence_pct, 1),
            )

        return DriftVelocityResult(
            u_drift=round(u_drift, 4),
            v_drift=round(v_drift, 4),
            drift_speed_mps=round(drift_speed, 4),
            drift_bearing_deg=round(drift_bearing, 2),
            current=curr_c,
            wind_drift=wind_c,
            stokes_drift=stokes_c,
            wind_drift_factor=self.config.wind_drift_factor,
            coriolis_deflection_deg=theta_w,
            stokes_drift_factor=self.config.stokes_drift_factor,
            lon=round(lon, 5),
            lat=round(lat, 5),
            timestamp=ts,
            confidence_pct=round(confidence_pct, 1),
            data_source=data_source,
            uncertainty=uncertainty_interval,
        )

    def evaluate_point(
        self,
        ds: xr.Dataset,
        lon: float,
        lat: float,
        timestamp: datetime,
    ) -> DriftVelocityResult:
        """Interpolates forcing fields from xarray Dataset and computes total drift velocity."""
        sample: MetoceanVelocityPoint = sample_forcing(ds, lon, lat, timestamp)

        return self.evaluate_vectors(
            u_curr=sample.u_curr,
            v_curr=sample.v_curr,
            u_wind=sample.u10,
            v_wind=sample.v10,
            lat=lat,
            lon=lon,
            timestamp=sample.timestamp,
            confidence_pct=sample.confidence_pct,
            data_source=sample.data_source,
            include_uncertainty=True,
        )

    def evaluate_vectorized(
        self,
        ds: xr.Dataset,
        lons: np.ndarray,
        lats: np.ndarray,
        timestamp: datetime,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Vectorized drift velocity evaluation for large particle ensembles (N >= 10,000).

        Returns:
            Tuple of (u_drift, v_drift, drift_speed, drift_bearing) numpy arrays of shape (N,).
        """
        uo, vo, u10, v10 = sample_forcing_vectorized(ds, lons, lats, timestamp)

        # Vectorized Coriolis deflection angle based on particle latitudes
        taper = np.tanh(lats / self.config.equator_decay_lat_deg)
        theta_w_deg = self.config.coriolis_deflection_deg * taper
        theta_rad = np.radians(theta_w_deg)

        cos_th = np.cos(theta_rad).astype(np.float32)
        sin_th = np.sin(theta_rad).astype(np.float32)

        # Rotate wind vectors clockwise (right) in Northern Hemisphere
        u_wind_rot = u10 * cos_th + v10 * sin_th
        v_wind_rot = -u10 * sin_th + v10 * cos_th

        # Scale by wind drag factor c_w
        cw = np.float32(self.config.wind_drift_factor)
        u_wind_drift = cw * u_wind_rot
        v_wind_drift = cw * v_wind_rot

        # Stokes wave drift
        c_st = np.float32(self.config.stokes_drift_factor)
        u_stokes = c_st * u10
        v_stokes = c_st * v10

        # Total drift velocity
        u_drift = uo + u_wind_drift + u_stokes
        v_drift = vo + v_wind_drift + v_stokes

        drift_speed = np.hypot(u_drift, v_drift)
        drift_bearing = (np.degrees(np.arctan2(u_drift, v_drift)) + 360.0) % 360.0

        return u_drift, v_drift, drift_speed, drift_bearing

    def compute_drift_field(self, ds: xr.Dataset) -> xr.Dataset:
        """Computes the full 3D/4D drift velocity vector field over an entire met-ocean dataset grid."""
        ds = standardize_dataset_coords(ds)

        uo = ds["uo"].values
        vo = ds["vo"].values
        u10 = ds["u10"].values
        v10 = ds["v10"].values

        lats = ds["lat"].values
        # Broadcast latitude along (time, lat, lon)
        lats_3d = lats[None, :, None]

        taper = np.tanh(lats_3d / self.config.equator_decay_lat_deg)
        theta_w_deg = self.config.coriolis_deflection_deg * taper
        theta_rad = np.radians(theta_w_deg)

        cos_th = np.cos(theta_rad).astype(np.float32)
        sin_th = np.sin(theta_rad).astype(np.float32)

        u_wind_rot = u10 * cos_th + v10 * sin_th
        v_wind_rot = -u10 * sin_th + v10 * cos_th

        cw = np.float32(self.config.wind_drift_factor)
        c_st = np.float32(self.config.stokes_drift_factor)

        u_wind_drift = cw * u_wind_rot
        v_wind_drift = cw * v_wind_rot
        u_stokes = c_st * u10
        v_stokes = c_st * v10

        u_drift = uo + u_wind_drift + u_stokes
        v_drift = vo + v_wind_drift + v_stokes

        drift_speed = np.hypot(u_drift, v_drift)
        drift_bearing = (np.degrees(np.arctan2(u_drift, v_drift)) + 360.0) % 360.0

        # Construct new Dataset preserving coords and adding drift variables
        ds_drift = ds.copy()
        ds_drift["u_drift"] = (
            ("time", "lat", "lon"),
            u_drift.astype(np.float32),
            {
                "long_name": "Total surface drift velocity eastward component",
                "units": "m s-1",
            },
        )
        ds_drift["v_drift"] = (
            ("time", "lat", "lon"),
            v_drift.astype(np.float32),
            {
                "long_name": "Total surface drift velocity northward component",
                "units": "m s-1",
            },
        )
        ds_drift["drift_speed"] = (
            ("time", "lat", "lon"),
            drift_speed.astype(np.float32),
            {"long_name": "Total surface drift velocity magnitude", "units": "m s-1"},
        )
        ds_drift["drift_bearing"] = (
            ("time", "lat", "lon"),
            drift_bearing.astype(np.float32),
            {"long_name": "Total surface drift bearing towards", "units": "degrees"},
        )

        ds_drift.attrs["wind_drift_factor"] = self.config.wind_drift_factor
        ds_drift.attrs["coriolis_deflection_nominal_deg"] = self.config.coriolis_deflection_deg
        ds_drift.attrs["stokes_drift_factor"] = self.config.stokes_drift_factor

        return ds_drift
