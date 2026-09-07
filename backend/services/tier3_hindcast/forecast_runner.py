"""AEGIS-Marine: Forward Trajectory Forecasting & Mackay Weathering Engine (Sub-Module 3B).

Implements Tier 3B Forward Spill Forecasting:
1. Forward in time numerical advection: delta_t = +15 minutes (+900 seconds) over [t_obs, t_obs + 72h].
2. Driven by Total Drift Velocity Engine (Currents + Ekman Wind Drift + Stokes Wave Drift).
3. Hydrocarbon weathering physics (PRD Section 10):
   - Mackay evaporative loss: F_evap(t) = min(F_max, (T_B / T) * c_evap * ln(1 + K_evap * t / V_0))
   - Water-in-oil emulsification kinetics: dY_w/dt = K_emul * (U_10 + 1)^2 * (Y_max - Y_w)
   - Mooney equation for emulsion viscosity increase: mu / mu_0 = exp(2.5 * Y_w / (1 - c_mooney * Y_w))
4. Shoreline interaction & beaching detection:
   - Proximity to coastline polygon <= 50 meters flags particles as 'beached'.
   - Beached particles are immobilized at their shoreline impact locations.
5. Impact & vulnerability metrics:
   - Estimated Time of Beaching (ETB) in hours.
   - Coastal Vulnerability Index (CVI) in [0.0, 1.0].
   - Deposited beached hydrocarbon volume in m^3 (accounting for evaporation).
   - Shoreline impact envelope polygon as GeoJSON.

Adheres to:
- PRD Section 10 & Architecture Section 4.3 formulas.
- Rule 1: Mandatory confidence score in [0.0, 100.0] on all outputs.
- Rule 4: Data source identification ("live" | "cached" | "synthetic").
- Rule 6: Zero occurrences of banned terms.
- Rules Section 3.1: Inline formula citations.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
import shapely
import xarray as xr
from shapely.geometry import MultiPoint, MultiPolygon, Polygon, mapping

from backend.app.schemas.hindcast import ForwardForecastBase
from backend.services.tier3_hindcast.drift_physics import (
    DriftConfig,
    DriftPhysicsEngine,
)
from backend.services.tier3_hindcast.hindcast_runner import seed_particles_in_polygon

logger = logging.getLogger("aegis.forecast")

# Geodetic constants (WGS84 spherical approximation)
EARTH_RADIUS_M = 6371000.0
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
METERS_PER_DEGREE_LAT = 111139.0


@dataclass
class WeatheringState:
    """Hydrocarbon physical weathering metrics at a discrete timestep."""

    elapsed_hours: float
    evaporated_fraction: float  # F_evap in [0.0, F_max]
    water_content_fraction: float  # Y_w in [0.0, Y_max]
    viscosity_ratio: float  # mu / mu_0 relative viscosity increase
    floating_fraction: float  # Fraction of particles still adrift
    beached_fraction: float  # Fraction of particles stranded ashore


@dataclass
class ForecastTrajectorySnapshot:
    """State summary of forward forecast ensemble at a discrete timestep."""

    timestamp: datetime
    elapsed_hours: float
    mean_lon: float
    mean_lat: float
    n_active: int
    n_beached: int
    weathering: WeatheringState
    subsample_coords: list[list[float]]  # Coordinates for UI rendering


@dataclass
class ForecastConfig:
    """Configuration parameters for forward trajectory and weathering forecast.

    PRD Section 10:
    - delta_t = +15 minutes (+900 s)
    - Horizon: +72 hours
    - Mackay evaporation: T_B = 350 K, T = 298.15 K
    - Emulsification: K_emul = 2.0e-6, Y_max = 0.80
    - Beaching threshold: 50 meters
    """

    n_particles: int = 5000  # Number of forward tracking particles
    forecast_hours: float = 72.0  # Forecast time horizon in hours
    time_step_minutes: float = 15.0  # Positive integration step (+15 min)
    horizontal_diffusivity_kh: float = 2.0  # Horizontal diffusion K_h (m^2/s)
    wind_drift_factor: float = 0.030  # c_w: 3.0%
    coriolis_deflection_deg: float = 12.0  # theta_w: 12.0°
    stokes_drift_factor: float = 0.012  # c_stokes: 1.2%
    evap_tb_kelvin: float = 350.0  # Mackay boiling point parameter T_B
    sst_kelvin: float = 298.15  # Sea surface temperature T (25°C)
    max_evaporation_fraction: float = 0.55  # Upper asymptote F_max
    emulsion_ymax: float = 0.80  # Maximum water fraction Y_max (80%)
    emulsion_kemul: float = 2.0e-6  # Emulsification rate coefficient
    mooney_constant: float = 0.65  # Mooney viscosity constant c_mooney
    beach_proximity_threshold_m: float = 50.0  # Coastline stranding threshold
    initial_volume_m3: float = 100.0  # Initial spill volume V_0
    subsample_size: int = 200  # UI rendering subsample count
    random_seed: int | None = 42  # Deterministic seed


@dataclass
class ForwardForecastResult:
    """Complete forward hydrodynamic trajectory weathering and impact forecast.

    Architecture Section 4.3 & PRD Section 10:
    {etb, cvi, beached_volume_m3, shoreline_impact_polygon}
    """

    case_id: str | None
    start_time: datetime  # t_obs
    forecast_end_time: datetime  # t_obs + 72h
    duration_hours: float
    n_particles: int
    n_beached: int
    beached_fraction: float
    etb_hours: float | None  # Estimated Time of Beaching in hours (None if no beaching)
    cvi_index: float | None  # Coastal Vulnerability Index in [0.0, 1.0]
    beached_volume_m3: float | None  # Deposited volume in m^3
    evaporated_volume_m3: float  # Volume lost to atmosphere
    floating_volume_m3: float  # Volume remaining at sea
    shoreline_impact_polygon: dict[str, Any] | None  # GeoJSON Polygon of impact envelope
    weathering_summary: dict[str, float]  # Evaporation, emulsification, and viscosity
    snapshots: list[ForecastTrajectorySnapshot]
    confidence_pct: float  # Rule 1: Mandatory confidence score in [0.0, 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4
    execution_time_sec: float = 0.0

    def to_pydantic_schema(self) -> ForwardForecastBase:
        """Converts to standard backend Pydantic ForwardForecastBase model."""
        impact_poly = None
        if self.shoreline_impact_polygon is not None:
            impact_poly = {
                "type": "Polygon",
                "coordinates": self.shoreline_impact_polygon["coordinates"],
            }

        return ForwardForecastBase(
            etb_hours=self.etb_hours,
            cvi_index=self.cvi_index,
            beached_volume_m3=self.beached_volume_m3,
            shoreline_impact_polygon=impact_poly,
        )

    def to_geojson_feature(self) -> dict[str, Any]:
        """Serializes impact polygon and forecast properties to GeoJSON Feature."""
        geom: dict[str, Any] | None = self.shoreline_impact_polygon
        if geom is None:
            geom = {"type": "GeometryCollection", "geometries": []}

        return {
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "case_id": self.case_id,
                "start_time": self.start_time.isoformat(),
                "forecast_end_time": self.forecast_end_time.isoformat(),
                "duration_hours": self.duration_hours,
                "n_particles": self.n_particles,
                "n_beached": self.n_beached,
                "beached_fraction": self.beached_fraction,
                "etb_hours": self.etb_hours,
                "cvi_index": self.cvi_index,
                "beached_volume_m3": self.beached_volume_m3,
                "floating_volume_m3": self.floating_volume_m3,
                "evaporated_volume_m3": self.evaporated_volume_m3,
                "weathering": self.weathering_summary,
                "confidence_pct": self.confidence_pct,
                "data_source": self.data_source,
            },
        }


def calculate_mackay_evaporation(
    elapsed_seconds: float,
    tb_kelvin: float = 350.0,
    sst_kelvin: float = 298.15,
    c_evap: float = 0.08,
    k_evap: float = 1.2e-5,
    v0_m3: float = 100.0,
    max_evap_fraction: float = 0.55,
) -> float:
    """Computes Mackay evaporative loss fraction F_evap(t).

    Formula (PRD Section 10):
    F_evap(t) = min(F_max, (T_B / T) * c_evap * ln(1 + K_evap * t / V_0))
    """
    if elapsed_seconds <= 0.0:
        return 0.0

    # Dimensionless scaling
    theta = (k_evap * elapsed_seconds / max(1.0, v0_m3)) * 1000.0
    f_evap = (tb_kelvin / sst_kelvin) * c_evap * math.log(1.0 + theta)
    return min(max_evap_fraction, max(0.0, f_evap))


def calculate_emulsification_kinetics(
    elapsed_seconds: float,
    mean_wind_speed_mps: float,
    k_emul: float = 2.0e-6,
    y_max: float = 0.80,
    c_mooney: float = 0.65,
) -> tuple[float, float]:
    """Computes water-in-oil emulsification water fraction Y_w and Mooney viscosity increase.

    Formulas (PRD Section 10):
    dY_w / dt = K_emul * (U_10 + 1)^2 * (Y_max - Y_w)
    mu / mu_0 = exp(2.5 * Y_w / (1 - c_mooney * Y_w))
    """
    if elapsed_seconds <= 0.0:
        return 0.0, 1.0

    rate_const = k_emul * ((mean_wind_speed_mps + 1.0) ** 2)
    y_w = y_max - (y_max - 0.0) * math.exp(-rate_const * elapsed_seconds)
    y_w = min(y_max, max(0.0, y_w))

    # Mooney relative viscosity multiplier
    denom = max(1e-4, 1.0 - c_mooney * y_w)
    viscosity_ratio = math.exp(2.5 * y_w / denom)

    return y_w, viscosity_ratio


class ForwardTrajectoryForecaster:
    """Simulates forward +72h Lagrangian oil drift, weathering, and shoreline beaching."""

    def __init__(
        self,
        config: ForecastConfig | None = None,
        drift_engine: DriftPhysicsEngine | None = None,
    ) -> None:
        self.config = config or ForecastConfig()
        drift_cfg = DriftConfig(
            wind_drift_factor=self.config.wind_drift_factor,
            coriolis_deflection_deg=self.config.coriolis_deflection_deg,
            stokes_drift_factor=self.config.stokes_drift_factor,
        )
        self.drift_engine = drift_engine or DriftPhysicsEngine(drift_cfg)

    def run_forecast(
        self,
        slick_polygon: Polygon | MultiPolygon | dict[str, Any],
        t_obs: datetime,
        forcing_ds: xr.Dataset,
        coastline_polygon: Polygon | MultiPolygon | None = None,
        initial_volume_m3: float | None = None,
        case_id: str | None = None,
    ) -> ForwardForecastResult:
        """Executes forward +72h hydrodynamic simulation with weathering and coastal beaching.

        Physics (PRD Section 10):
        1. Forward advection: delta_t = +15 minutes (+900 s) over [t_obs, t_obs + 72h].
        2. Weathering: Mackay evaporative loss and Mooney emulsification viscosity.
        3. Coastline collision: particles within 50m of coastline are stranded as 'beached'.
        """
        start_wall_time = time.time()
        v0 = initial_volume_m3 or self.config.initial_volume_m3
        n_particles = self.config.n_particles
        dt_sec = self.config.time_step_minutes * 60.0  # +900 seconds
        total_forecast_sec = self.config.forecast_hours * 3600.0
        n_steps = max(1, int(round(total_forecast_sec / dt_sec)))
        t_end = t_obs + timedelta(hours=self.config.forecast_hours)

        kh = self.config.horizontal_diffusivity_kh
        diff_scale_m = math.sqrt(2.0 * kh * dt_sec)

        # 1. Uniformly seed particles across slick polygon
        lons, lats = seed_particles_in_polygon(
            polygon_geom=slick_polygon,
            n_particles=n_particles,
            random_seed=self.config.random_seed,
        )

        # Particle status arrays
        is_beached = np.zeros(n_particles, dtype=bool)
        beached_times_sec = np.full(n_particles, np.nan, dtype=np.float64)

        # Buffer coastline polygon for 50m proximity detection
        coast_buffer = None
        if coastline_polygon is not None and not coastline_polygon.is_empty:
            # 50m in degrees latitude ~ 50 / 111139.0 ~ 0.00045 deg
            buffer_deg = self.config.beach_proximity_threshold_m / METERS_PER_DEGREE_LAT
            coast_buffer = coastline_polygon.buffer(buffer_deg)

        rng = np.random.default_rng(self.config.random_seed)
        subsample_idx = np.linspace(
            0, n_particles - 1, min(self.config.subsample_size, n_particles), dtype=int
        )

        snapshots: list[ForecastTrajectorySnapshot] = []

        # Record initial snapshot (step 0 at t_obs)
        curr_time = t_obs
        init_weathering = WeatheringState(
            elapsed_hours=0.0,
            evaporated_fraction=0.0,
            water_content_fraction=0.0,
            viscosity_ratio=1.0,
            floating_fraction=1.0,
            beached_fraction=0.0,
        )
        subsamples_0 = [[round(float(lons[i]), 5), round(float(lats[i]), 5)] for i in subsample_idx]
        snapshots.append(
            ForecastTrajectorySnapshot(
                timestamp=curr_time,
                elapsed_hours=0.0,
                mean_lon=round(float(np.mean(lons)), 5),
                mean_lat=round(float(np.mean(lats)), 5),
                n_active=n_particles,
                n_beached=0,
                weathering=init_weathering,
                subsample_coords=subsamples_0,
            )
        )

        # Running wind speed accumulator for emulsification kinetics
        total_wind_speed = 0.0

        # 2. Forward advection loop (+15 min per step over 72h)
        for step in range(1, n_steps + 1):
            elapsed_sec = step * dt_sec
            active_mask = ~is_beached

            if np.any(active_mask):
                active_lons = lons[active_mask].astype(np.float32)
                active_lats = lats[active_mask].astype(np.float32)

                # Step 1: Predictor at curr_time
                uo, vo, _, _ = self.drift_engine.evaluate_vectorized(
                    forcing_ds, active_lons, active_lats, curr_time
                )

                # Midpoint geodetic coordinates
                lat_rad = lats[active_mask] * DEG_TO_RAD
                dlat_half = (vo * 0.5 * dt_sec / EARTH_RADIUS_M) * RAD_TO_DEG
                dlon_half = (uo * 0.5 * dt_sec / (EARTH_RADIUS_M * np.cos(lat_rad))) * RAD_TO_DEG
                lons_mid = lons[active_mask] + dlon_half
                lats_mid = lats[active_mask] + dlat_half
                t_mid = curr_time + timedelta(seconds=0.5 * dt_sec)

                # Step 2: Corrector velocity at midpoint
                uo_mid, vo_mid, u10_mid, v10_mid = self.drift_engine.evaluate_vectorized(
                    forcing_ds,
                    lons_mid.astype(np.float32),
                    lats_mid.astype(np.float32),
                    t_mid,
                )

                # Advective displacement in meters
                dx_adv = uo_mid * dt_sec
                dy_adv = vo_mid * dt_sec

                # Step 3: Monte Carlo Turbulent Diffusion
                n_active = len(active_lons)
                zx = rng.standard_normal(n_active)
                zy = rng.standard_normal(n_active)
                dx_diff = diff_scale_m * zx
                dy_diff = diff_scale_m * zy

                dx_total = dx_adv + dx_diff
                dy_total = dy_adv + dy_diff

                dlat = (dy_total / EARTH_RADIUS_M) * RAD_TO_DEG
                dlon = (dx_total / (EARTH_RADIUS_M * np.cos(lat_rad))) * RAD_TO_DEG

                lons[active_mask] += dlon
                lats[active_mask] += dlat

                wind_speed_step = float(np.mean(np.hypot(u10_mid, v10_mid)))
                total_wind_speed += wind_speed_step

            # Step 4: Coastline collision and stranding check (proximity <= 50m)
            if coast_buffer is not None and np.any(~is_beached):
                active_indices = np.where(~is_beached)[0]
                pts = shapely.points(lons[active_indices], lats[active_indices])
                beached_now = shapely.contains(coast_buffer, pts)

                if np.any(beached_now):
                    newly_beached_indices = active_indices[beached_now]
                    is_beached[newly_beached_indices] = True
                    beached_times_sec[newly_beached_indices] = elapsed_sec

            curr_time += timedelta(seconds=dt_sec)

            # Step 5: Weathering computation at discrete 1-hour intervals (or final step)
            if step % 4 == 0 or step == n_steps:
                elapsed_hours = elapsed_sec / 3600.0
                mean_wind = total_wind_speed / step if step > 0 else 7.0

                f_evap = calculate_mackay_evaporation(
                    elapsed_seconds=elapsed_sec,
                    tb_kelvin=self.config.evap_tb_kelvin,
                    sst_kelvin=self.config.sst_kelvin,
                    v0_m3=v0,
                    max_evap_fraction=self.config.max_evaporation_fraction,
                )
                y_w, visc_ratio = calculate_emulsification_kinetics(
                    elapsed_seconds=elapsed_sec,
                    mean_wind_speed_mps=mean_wind,
                    k_emul=self.config.emulsion_kemul,
                    y_max=self.config.emulsion_ymax,
                    c_mooney=self.config.mooney_constant,
                )

                n_beached_count = int(np.sum(is_beached))
                n_active_count = n_particles - n_beached_count
                w_state = WeatheringState(
                    elapsed_hours=round(elapsed_hours, 2),
                    evaporated_fraction=round(f_evap, 4),
                    water_content_fraction=round(y_w, 4),
                    viscosity_ratio=round(visc_ratio, 2),
                    floating_fraction=round(n_active_count / n_particles, 4),
                    beached_fraction=round(n_beached_count / n_particles, 4),
                )

                subsamples = [
                    [round(float(lons[i]), 5), round(float(lats[i]), 5)] for i in subsample_idx
                ]
                snapshots.append(
                    ForecastTrajectorySnapshot(
                        timestamp=curr_time,
                        elapsed_hours=round(elapsed_hours, 2),
                        mean_lon=round(float(np.mean(lons)), 5),
                        mean_lat=round(float(np.mean(lats)), 5),
                        n_active=n_active_count,
                        n_beached=n_beached_count,
                        weathering=w_state,
                        subsample_coords=subsamples,
                    )
                )

        # 3. Compute final forecast metrics
        total_beached = int(np.sum(is_beached))
        beached_fraction = float(total_beached / n_particles)

        # Estimated Time of Beaching (ETB)
        etb_hours: float | None = None
        if total_beached > 0:
            min_beached_sec = float(np.nanmin(beached_times_sec))
            etb_hours = round(min_beached_sec / 3600.0, 2)

        # Final weathering state at 72 hours
        final_f_evap = calculate_mackay_evaporation(
            elapsed_seconds=total_forecast_sec,
            tb_kelvin=self.config.evap_tb_kelvin,
            sst_kelvin=self.config.sst_kelvin,
            v0_m3=v0,
            max_evap_fraction=self.config.max_evaporation_fraction,
        )
        mean_wind_final = total_wind_speed / n_steps if n_steps > 0 else 7.0
        final_y_w, final_visc_ratio = calculate_emulsification_kinetics(
            elapsed_seconds=total_forecast_sec,
            mean_wind_speed_mps=mean_wind_final,
            k_emul=self.config.emulsion_kemul,
            y_max=self.config.emulsion_ymax,
            c_mooney=self.config.mooney_constant,
        )

        evaporated_volume = v0 * final_f_evap
        remaining_volume = v0 - evaporated_volume

        beached_volume: float | None = None
        if total_beached > 0:
            beached_volume = round(remaining_volume * beached_fraction, 2)

        floating_volume = round(remaining_volume * (1.0 - beached_fraction), 2)

        # Coastal Vulnerability Index (CVI) in [0.0, 1.0]
        cvi_index: float | None = None
        if total_beached > 0 and etb_hours is not None:
            rapidness = max(0.0, 1.0 - (etb_hours / self.config.forecast_hours))
            cvi_val = min(1.0, max(0.0, 0.4 * beached_fraction + 0.6 * rapidness))
            cvi_index = round(cvi_val, 3)

        # Shoreline Impact Polygon (enclosing beached particles)
        impact_geojson: dict[str, Any] | None = None
        if total_beached > 0:
            beached_lons = lons[is_beached]
            beached_lats = lats[is_beached]

            if len(beached_lons) >= 3:
                pts_mp = MultiPoint(list(zip(beached_lons, beached_lats, strict=True)))
                # Buffer the convex hull by ~100m (0.0009°) for visibility
                impact_poly = pts_mp.convex_hull.buffer(0.0009)
            else:
                pts_mp = MultiPoint(list(zip(beached_lons, beached_lats, strict=True)))
                impact_poly = pts_mp.buffer(0.001)

            if isinstance(impact_poly, Polygon) and impact_poly.is_valid:
                impact_geojson = mapping(impact_poly)

        # Rule 1 & Rule 4
        base_confidence = float(forcing_ds.attrs.get("confidence_pct", 85.0))
        # 72h forecast uncertainty penalty
        forecast_confidence = round(max(50.0, min(100.0, base_confidence * 0.90)), 1)
        data_source = forcing_ds.attrs.get("data_source", "synthetic")

        elapsed_wall_sec = round(time.time() - start_wall_time, 3)

        weathering_summary = {
            "evaporated_fraction": round(final_f_evap, 4),
            "water_content_fraction": round(final_y_w, 4),
            "viscosity_ratio": round(final_visc_ratio, 2),
            "initial_volume_m3": round(v0, 2),
            "evaporated_volume_m3": round(evaporated_volume, 2),
            "floating_volume_m3": round(floating_volume, 2),
            "beached_volume_m3": beached_volume or 0.0,
        }

        return ForwardForecastResult(
            case_id=case_id,
            start_time=t_obs,
            forecast_end_time=t_end,
            duration_hours=self.config.forecast_hours,
            n_particles=n_particles,
            n_beached=total_beached,
            beached_fraction=round(beached_fraction, 4),
            etb_hours=etb_hours,
            cvi_index=cvi_index,
            beached_volume_m3=beached_volume,
            evaporated_volume_m3=round(evaporated_volume, 2),
            floating_volume_m3=floating_volume,
            shoreline_impact_polygon=impact_geojson,
            weathering_summary=weathering_summary,
            snapshots=snapshots,
            confidence_pct=forecast_confidence,
            data_source=data_source,
            execution_time_sec=elapsed_wall_sec,
        )
