"""AEGIS-Marine: Backward Lagrangian Hydrodynamic Hindcasting Runner (Sub-Module 3A).

Implements Tier 3 Lagrangian Particle Hindcasting:
1. Uniform seeding of N >= 10,000 numerical particles across detected slick polygon.
2. Backward in time integration: delta_t = -15 minutes (-900 seconds) from t_obs to t_obs - t_age.
3. Hydrodynamic advection via Runge-Kutta 2nd order (RK2) midpoint scheme driven by
   Total Drift Velocity Engine (Currents + Ekman Wind Drift + Stokes Wave Drift).
4. Horizontal turbulent diffusion via Monte Carlo random walk (PRD Section 10):
   Delta r_diff = sqrt(2 * K_h * |delta_t|) * N(0, 1)
5. Time-series trajectory snapshot persistence for geospatial replay and animation.

Adheres to:
- PRD Section 10 & Technical Specification formulas.
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
from shapely.geometry import MultiPolygon, Polygon, shape

from backend.services.tier3_hindcast.drift_physics import (
    DriftConfig,
    DriftPhysicsEngine,
)

logger = logging.getLogger("aegis.hindcast")

# Mean Earth radius in meters (WGS84 spherical approximation)
EARTH_RADIUS_M = 6371000.0
RAD_TO_DEG = 180.0 / math.pi
DEG_TO_RAD = math.pi / 180.0


@dataclass
class ParticleTrajectorySnapshot:
    """State summary of particle ensemble at a discrete simulation timestep."""

    timestamp: datetime
    step_index: int
    mean_lon: float
    mean_lat: float
    std_lon: float
    std_lat: float
    bounds: tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    n_particles: int
    subsample_coords: list[list[float]]  # List of [lon, lat] for lightweight map rendering


@dataclass
class HindcastConfig:
    """Configuration for Lagrangian backward advection simulation.

    PRD Section 10:
    - N >= 10,000 particles
    - delta_t = -15 minutes (-900 s)
    - Horizontal turbulent diffusivity K_h in [1.0, 10.0] m^2/s (nominal 2.0 m^2/s)
    """

    n_particles: int = 10000  # Particle count (N >= 10,000)
    time_step_minutes: float = -15.0  # Integration timestep (negative for reverse-time)
    horizontal_diffusivity_kh: float = 2.0  # Horizontal diffusion coefficient K_h (m^2/s)
    wind_drift_factor: float = 0.030  # c_w: 3.0%
    coriolis_deflection_deg: float = 12.0  # theta_w: 12.0°
    stokes_drift_factor: float = 0.012  # c_stokes: 1.2%
    subsample_size: int = 200  # Number of particles preserved per snapshot for web rendering
    random_seed: int | None = 42  # Seed for reproducible Monte Carlo diffusion


@dataclass
class HindcastResult:
    """Comprehensive backward Lagrangian hindcasting result."""

    case_id: str | None
    detection_time: datetime  # t_obs
    estimated_release_time: datetime  # t_release = t_obs - t_age
    duration_hours: float  # t_age
    n_particles: int
    time_step_minutes: float
    diffusivity_kh: float
    initial_polygon_geojson: dict[str, Any]
    snapshots: list[ParticleTrajectorySnapshot]
    final_ensemble_lons: np.ndarray  # Shape (N,)
    final_ensemble_lats: np.ndarray  # Shape (N,)
    origin_centroid: tuple[float, float]  # (lon, lat) of ensemble mean at release time
    origin_covariance_matrix: dict[
        str, float
    ]  # Spatial covariance [[var_lon, cov], [cov, var_lat]]
    confidence_pct: float  # Rule 1: [0.0 - 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4
    execution_time_sec: float = 0.0


def seed_particles_in_polygon(
    polygon_geom: Polygon | MultiPolygon | dict[str, Any],
    n_particles: int = 10000,
    random_seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Uniformly seeds N particles across the slick polygon using vectorized rejection sampling.

    Optimized for Shapely 2.x and NumPy: executes in < 50ms for 10,000 particles.
    """
    if isinstance(polygon_geom, dict):
        if polygon_geom.get("type") == "Feature":
            poly = shape(polygon_geom["geometry"])
        else:
            poly = shape(polygon_geom)
    else:
        poly = polygon_geom

    if not isinstance(poly, (Polygon, MultiPolygon)) or poly.is_empty:
        raise ValueError(f"Invalid polygon geometry provided: {type(poly)}")

    # If MultiPolygon, select the largest polygon by area
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)

    min_lon, min_lat, max_lon, max_lat = poly.bounds
    rng = np.random.default_rng(random_seed)

    accepted_lons: list[float] = []
    accepted_lats: list[float] = []

    # Rejection sampling in batches
    while len(accepted_lons) < n_particles:
        needed = n_particles - len(accepted_lons)
        batch_size = max(needed * 2, 2000)
        cand_lons = rng.uniform(min_lon, max_lon, batch_size)
        cand_lats = rng.uniform(min_lat, max_lat, batch_size)

        pts = shapely.points(cand_lons, cand_lats)
        mask = shapely.contains(poly, pts)

        accepted_lons.extend(cand_lons[mask][:needed])
        accepted_lats.extend(cand_lats[mask][:needed])

    return np.array(accepted_lons, dtype=np.float64), np.array(accepted_lats, dtype=np.float64)


class LagrangianHindcastRunner:
    """Executes backward Lagrangian numerical particle tracking driven by met-ocean forcing."""

    def __init__(
        self,
        config: HindcastConfig | None = None,
        drift_engine: DriftPhysicsEngine | None = None,
    ) -> None:
        self.config = config or HindcastConfig()
        drift_cfg = DriftConfig(
            wind_drift_factor=self.config.wind_drift_factor,
            coriolis_deflection_deg=self.config.coriolis_deflection_deg,
            stokes_drift_factor=self.config.stokes_drift_factor,
        )
        self.drift_engine = drift_engine or DriftPhysicsEngine(drift_cfg)

    def run_hindcast(
        self,
        slick_polygon: Polygon | MultiPolygon | dict[str, Any],
        t_obs: datetime,
        t_age_hours: float,
        forcing_ds: xr.Dataset,
        case_id: str | None = None,
    ) -> HindcastResult:
        """Advects N >= 10,000 particles backward in time from t_obs to (t_obs - t_age).

        Physics (PRD Section 10):
        1. RK2 Midpoint backward advection: delta_t = -15 min.
        2. Horizontal turbulent diffusion: delta_r_diff = sqrt(2 * K_h * |delta_t|) * N(0, 1).
        """
        start_wall_time = time.time()
        n_particles = self.config.n_particles
        dt_sec = self.config.time_step_minutes * 60.0  # -900 seconds
        abs_dt = abs(dt_sec)
        kh = self.config.horizontal_diffusivity_kh
        diff_scale_m = math.sqrt(2.0 * kh * abs_dt)

        # 1. Uniformly seed particles across slick polygon
        lons, lats = seed_particles_in_polygon(
            polygon_geom=slick_polygon,
            n_particles=n_particles,
            random_seed=self.config.random_seed,
        )

        total_duration_sec = t_age_hours * 3600.0
        n_steps = max(1, int(round(total_duration_sec / abs_dt)))
        t_release = t_obs - timedelta(hours=t_age_hours)

        rng = np.random.default_rng(self.config.random_seed)
        subsample_idx = np.linspace(
            0, n_particles - 1, min(self.config.subsample_size, n_particles), dtype=int
        )

        snapshots: list[ParticleTrajectorySnapshot] = []

        # Helper to record snapshot
        def create_snapshot(
            step: int, ts: datetime, p_lons: np.ndarray, p_lats: np.ndarray
        ) -> ParticleTrajectorySnapshot:
            m_lon = float(np.mean(p_lons))
            m_lat = float(np.mean(p_lats))
            s_lon = float(np.std(p_lons))
            s_lat = float(np.std(p_lats))
            bounds = (
                float(np.min(p_lons)),
                float(np.min(p_lats)),
                float(np.max(p_lons)),
                float(np.max(p_lats)),
            )
            subsamples = [
                [round(float(p_lons[i]), 5), round(float(p_lats[i]), 5)] for i in subsample_idx
            ]
            return ParticleTrajectorySnapshot(
                timestamp=ts,
                step_index=step,
                mean_lon=round(m_lon, 5),
                mean_lat=round(m_lat, 5),
                std_lon=round(s_lon, 5),
                std_lat=round(s_lat, 5),
                bounds=bounds,
                n_particles=len(p_lons),
                subsample_coords=subsamples,
            )

        # Record initial detection snapshot (step 0 at t_obs)
        curr_time = t_obs
        snapshots.append(create_snapshot(0, curr_time, lons, lats))

        # 2. Backward advection loop
        for step in range(1, n_steps + 1):
            # Step 1: Predictor at curr_time
            uo, vo, _, _ = self.drift_engine.evaluate_vectorized(
                forcing_ds,
                lons.astype(np.float32),
                lats.astype(np.float32),
                curr_time,
            )

            # Midpoint geodetic coordinates
            lat_rad = lats * DEG_TO_RAD
            dlat_half = (vo * 0.5 * dt_sec / EARTH_RADIUS_M) * RAD_TO_DEG
            dlon_half = (uo * 0.5 * dt_sec / (EARTH_RADIUS_M * np.cos(lat_rad))) * RAD_TO_DEG
            lons_mid = lons + dlon_half
            lats_mid = lats + dlat_half
            t_mid = curr_time + timedelta(seconds=0.5 * dt_sec)

            # Step 2: Corrector velocity at midpoint
            uo_mid, vo_mid, _, _ = self.drift_engine.evaluate_vectorized(
                forcing_ds,
                lons_mid.astype(np.float32),
                lats_mid.astype(np.float32),
                t_mid,
            )

            # Advective displacement in meters
            dx_adv = uo_mid * dt_sec
            dy_adv = vo_mid * dt_sec

            # Step 3: Monte Carlo Turbulent Diffusion (PRD Section 10)
            zx = rng.standard_normal(n_particles)
            zy = rng.standard_normal(n_particles)
            dx_diff = diff_scale_m * zx
            dy_diff = diff_scale_m * zy

            dx_total = dx_adv + dx_diff
            dy_total = dy_adv + dy_diff

            # Step 4: Geodetic position update
            dlat = (dy_total / EARTH_RADIUS_M) * RAD_TO_DEG
            dlon = (dx_total / (EARTH_RADIUS_M * np.cos(lat_rad))) * RAD_TO_DEG

            lons += dlon
            lats += dlat
            curr_time += timedelta(seconds=dt_sec)

            # Record periodic snapshots
            snapshots.append(create_snapshot(step, curr_time, lons, lats))

        # 3. Origin Statistics Computation at Release Time
        origin_lon = float(np.mean(lons))
        origin_lat = float(np.mean(lats))
        var_lon = float(np.var(lons))
        var_lat = float(np.var(lats))
        cov_lon_lat = float(np.cov(lons, lats)[0, 1])

        cov_matrix = {
            "var_lon": round(var_lon, 8),
            "var_lat": round(var_lat, 8),
            "cov_lon_lat": round(cov_lon_lat, 8),
        }

        # Data source and confidence computation
        data_source = forcing_ds.attrs.get("data_source", "synthetic")
        # Confidence decays gradually for very long hindcast horizons (> 48h) per PRD
        base_confidence = float(forcing_ds.attrs.get("confidence_pct", 85.0))
        if t_age_hours > 48.0:
            decay_factor = max(0.5, 1.0 - 0.01 * (t_age_hours - 48.0))
            hindcast_confidence = round(base_confidence * decay_factor, 1)
        else:
            hindcast_confidence = round(base_confidence, 1)

        # Polygon GeoJSON serialization
        if isinstance(slick_polygon, dict):
            poly_geojson = slick_polygon
        else:
            poly_geojson = shapely.geometry.mapping(slick_polygon)

        elapsed_sec = round(time.time() - start_wall_time, 3)

        return HindcastResult(
            case_id=case_id,
            detection_time=t_obs,
            estimated_release_time=t_release,
            duration_hours=t_age_hours,
            n_particles=n_particles,
            time_step_minutes=self.config.time_step_minutes,
            diffusivity_kh=kh,
            initial_polygon_geojson=poly_geojson,
            snapshots=snapshots,
            final_ensemble_lons=lons,
            final_ensemble_lats=lats,
            origin_centroid=(round(origin_lon, 5), round(origin_lat, 5)),
            origin_covariance_matrix=cov_matrix,
            confidence_pct=min(100.0, max(0.0, hindcast_confidence)),
            data_source=data_source,
            execution_time_sec=elapsed_sec,
        )

    def to_geojson_trajectory(self, result: HindcastResult) -> dict[str, Any]:
        """Formats hindcast results into a GeoJSON FeatureCollection for frontend map rendering."""
        features: list[dict[str, Any]] = []

        # 1. Detection polygon feature
        features.append(
            {
                "type": "Feature",
                "geometry": result.initial_polygon_geojson,
                "properties": {
                    "role": "slick_detection_polygon",
                    "timestamp": result.detection_time.isoformat(),
                },
            }
        )

        # 2. Trajectory centroid track (LineString)
        coords = [[s.mean_lon, s.mean_lat] for s in result.snapshots]
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "role": "ensemble_centroid_trajectory",
                    "time_start": result.detection_time.isoformat(),
                    "time_end": result.estimated_release_time.isoformat(),
                    "duration_hours": result.duration_hours,
                },
            }
        )

        # 3. Origin centroid Point
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": list(result.origin_centroid),
                },
                "properties": {
                    "role": "estimated_origin_centroid",
                    "timestamp": result.estimated_release_time.isoformat(),
                    "confidence_pct": result.confidence_pct,
                    "data_source": result.data_source,
                },
            }
        )

        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "case_id": result.case_id,
                "n_particles": result.n_particles,
                "duration_hours": result.duration_hours,
                "time_step_minutes": result.time_step_minutes,
                "confidence_pct": result.confidence_pct,
                "data_source": result.data_source,
            },
        }
