"""AEGIS-Marine: Probabilistic Spill Origin Density Estimation (Sub-Module 3A).

Implements Tier 3 Origin Estimation:
1. 2D Gaussian Kernel Density Estimation (KDE) over backward Lagrangian particle ensemble
   using scipy.stats.gaussian_kde with Scott's rule bandwidth.
2. Spatial centroid mu_p = [lat_bar, lon_bar] of maximum probability density.
3. 2x2 Spatial covariance matrix Sigma_p:
   [[var_lat, cov_lat_lon], [cov_lat_lon, var_lon]]
4. Generation of 1-sigma, 2-sigma, 3-sigma (39.35%, 86.47%, 98.89%) confidence error ellipse polygons as GeoJSON.
5. Release time window estimation and 3-sigma uncertainty contour area in km^2.

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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import numpy as np
import scipy.optimize as opt
import scipy.stats as stats
from shapely.geometry import Polygon, mapping

from backend.app.schemas.hindcast import OriginEstimateBase
from backend.services.tier3_hindcast.hindcast_runner import HindcastResult

logger = logging.getLogger("aegis.origin_estimator")

# Geodetic constants (WGS84 spherical approximation)
EARTH_RADIUS_M = 6371000.0
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
METERS_PER_DEGREE_LAT = 111139.0


@dataclass
class ConfidenceEllipse:
    """Confidence error ellipse bounding a specified theoretical probability mass."""

    sigma_level: int  # 1, 2, or 3
    probability_pct: float  # 39.35%, 86.47%, 98.89%
    semi_major_axis_m: float  # Semi-major axis length in meters
    semi_minor_axis_m: float  # Semi-minor axis length in meters
    orientation_deg: float  # Major axis orientation in degrees from East (-180 to +180)
    area_km2: float  # Area bounded by the ellipse in km^2
    polygon: Polygon  # Shapely Polygon geometry in EPSG:4326
    geojson: dict[str, Any]  # GeoJSON Polygon geometry dictionary


@dataclass
class OriginEstimateResult:
    """Probabilistic origin estimate derived from backward Lagrangian simulation.

    PRD Section 10:
    P(x, y, t_k) = (1/N) * sum(K_H(x - x_p(t_k))) -> centroid mu_p, covariance Sigma_p
    """

    case_id: str | None
    centroid: tuple[float, float]  # [lon, lat] coordinate
    centroid_lat_lon: tuple[float, float]  # [lat, lon] coordinate
    covariance_matrix: dict[str, float]  # Geodetic covariance: var_lat, var_lon, cov_lon_lat
    covariance_matrix_m2: dict[str, float]  # Metric covariance: var_x_m2, var_y_m2, cov_xy_m2
    time_window_start: datetime  # Earliest estimated release time
    time_window_end: datetime  # Latest estimated release time
    region_area_km2: float  # 3-sigma uncertainty contour area in km^2
    confidence_pct: float  # Rule 1: Mandatory confidence score in [0.0, 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4
    ellipses: dict[str, ConfidenceEllipse] = field(
        default_factory=dict
    )  # "1sigma", "2sigma", "3sigma"
    kde_bandwidth: float = 0.0  # Scott's factor bandwidth
    peak_density: float = 0.0  # Evaluated probability density at mode
    n_particles: int = 10000
    particle_trajectory_ref: str | None = None

    def to_geojson_feature(self) -> dict[str, Any]:
        """Serializes origin estimate to a standard GeoJSON Feature matching benchmark fixtures."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": list(self.centroid),
            },
            "properties": {
                "case_id": self.case_id,
                "origin_centroid": list(self.centroid),
                "covariance_matrix": self.covariance_matrix,
                "time_window_start": self.time_window_start.isoformat(),
                "time_window_end": self.time_window_end.isoformat(),
                "confidence_pct": self.confidence_pct,
                "region_area_km2": self.region_area_km2,
                "data_source": self.data_source,
                "ellipses": {
                    key: {
                        "sigma_level": ell.sigma_level,
                        "probability_pct": ell.probability_pct,
                        "area_km2": ell.area_km2,
                        "geometry": ell.geojson,
                    }
                    for key, ell in self.ellipses.items()
                },
            },
        }

    def to_pydantic_schema(self) -> OriginEstimateBase:
        """Converts to standard backend Pydantic OriginEstimateBase model."""
        return OriginEstimateBase(
            centroid={"type": "Point", "coordinates": self.centroid},
            covariance_matrix=self.covariance_matrix,
            time_window_start=self.time_window_start,
            time_window_end=self.time_window_end,
            confidence_pct=self.confidence_pct,
            region_area_km2=self.region_area_km2,
            particle_trajectory_ref=self.particle_trajectory_ref,
        )


def generate_confidence_ellipse(
    centroid_lon: float,
    centroid_lat: float,
    cov_matrix_geodetic: np.ndarray,
    sigma_level: int = 3,
    n_points: int = 64,
) -> ConfidenceEllipse:
    """Generates a parametric confidence error ellipse polygon for a 2D Gaussian distribution.

    Mathematical Basis:
    Level curves of (x - mu)^T Sigma^-1 (x - mu) = s^2 for s in {1, 2, 3}.
    - s = 1 (1-sigma): 1 - exp(-0.5) ≈ 39.35% theoretical probability mass.
    - s = 2 (2-sigma): 1 - exp(-2.0) ≈ 86.47% theoretical probability mass.
    - s = 3 (3-sigma): 1 - exp(-4.5) ≈ 98.89% theoretical probability mass.
    """
    prob_map = {1: 39.35, 2: 86.47, 3: 98.89}
    prob_pct = prob_map.get(sigma_level, 98.89)

    # Metric scale factors at centroid latitude
    cos_lat = math.cos(centroid_lat * DEG_TO_RAD)
    m_per_deg_lon = METERS_PER_DEGREE_LAT * cos_lat
    m_per_deg_lat = METERS_PER_DEGREE_LAT

    # Metric covariance matrix [[var_x, cov_xy], [cov_xy, var_y]]
    cov_m = np.zeros((2, 2), dtype=np.float64)
    cov_m[0, 0] = cov_matrix_geodetic[0, 0] * (m_per_deg_lon**2)
    cov_m[1, 1] = cov_matrix_geodetic[1, 1] * (m_per_deg_lat**2)
    cov_m[0, 1] = cov_m[1, 0] = cov_matrix_geodetic[0, 1] * (m_per_deg_lon * m_per_deg_lat)

    # Spectral decomposition of metric covariance
    eigvals_m, eigvecs_m = np.linalg.eigh(cov_m)
    order = np.argsort(eigvals_m)[::-1]
    eigvals_m = np.maximum(eigvals_m[order], 1e-6)
    eigvecs_m = eigvecs_m[:, order]

    semi_major_m = float(sigma_level * math.sqrt(eigvals_m[0]))
    semi_minor_m = float(sigma_level * math.sqrt(eigvals_m[1]))
    area_km2 = float((math.pi * semi_major_m * semi_minor_m) / 1e6)

    # Orientation of major axis in degrees
    orientation_deg = float(math.degrees(math.atan2(eigvecs_m[1, 0], eigvecs_m[0, 0])))

    # Spectral decomposition of geodetic covariance for EPSG:4326 polygon coordinates
    eigvals_geo, eigvecs_geo = np.linalg.eigh(cov_matrix_geodetic)
    order_geo = np.argsort(eigvals_geo)[::-1]
    eigvals_geo = np.maximum(eigvals_geo[order_geo], 1e-12)
    eigvecs_geo = eigvecs_geo[:, order_geo]

    # Generate ellipse boundary points
    phi = np.linspace(0, 2 * math.pi, n_points)
    circle_pts = np.vstack([np.cos(phi), np.sin(phi)])  # Shape (2, n_points)
    scaled_pts = sigma_level * np.sqrt(eigvals_geo[:, None]) * circle_pts
    mu = np.array([centroid_lon, centroid_lat], dtype=np.float64)
    ellipse_coords = (mu[:, None] + eigvecs_geo @ scaled_pts).T  # Shape (n_points, 2)

    poly = Polygon(ellipse_coords)
    if not poly.is_valid:
        poly = poly.buffer(0)

    return ConfidenceEllipse(
        sigma_level=sigma_level,
        probability_pct=prob_pct,
        semi_major_axis_m=round(semi_major_m, 2),
        semi_minor_axis_m=round(semi_minor_m, 2),
        orientation_deg=round(orientation_deg, 2),
        area_km2=round(area_km2, 4),
        polygon=poly,
        geojson=mapping(poly),
    )


class OriginDensityEstimator:
    """Estimates origin density, centroid, covariance, and error ellipses from particle simulations."""

    def __init__(self, bandwidth_method: str = "scott") -> None:
        self.bandwidth_method = bandwidth_method

    def estimate_origin(
        self,
        hindcast_result: HindcastResult | None = None,
        lons: np.ndarray | None = None,
        lats: np.ndarray | None = None,
        t_obs: datetime | None = None,
        t_age_hours: float | None = None,
        time_window: tuple[datetime, datetime] | None = None,
        case_id: str | None = None,
        confidence_pct: float | None = None,
        data_source: Literal["live", "cached", "synthetic"] | None = None,
    ) -> OriginEstimateResult:
        """Derives probabilistic origin parameters using 2D Gaussian KDE and covariance analysis.

        Can be called directly with a HindcastResult or with standalone coordinate arrays.
        """
        # 1. Extract inputs
        if hindcast_result is not None:
            p_lons = hindcast_result.final_ensemble_lons
            p_lats = hindcast_result.final_ensemble_lats
            cid = case_id or hindcast_result.case_id
            conf = confidence_pct if confidence_pct is not None else hindcast_result.confidence_pct
            src = data_source or hindcast_result.data_source
            release_t = hindcast_result.estimated_release_time
            age_h = hindcast_result.duration_hours
        else:
            if lons is None or lats is None:
                raise ValueError(
                    "Must provide either hindcast_result or (lons, lats) coordinate arrays"
                )
            p_lons = np.asarray(lons, dtype=np.float64)
            p_lats = np.asarray(lats, dtype=np.float64)
            cid = case_id
            conf = confidence_pct if confidence_pct is not None else 85.0
            src = data_source or "synthetic"
            age_h = t_age_hours or 6.0
            det_t = t_obs or datetime.now(UTC)
            release_t = det_t - timedelta(hours=age_h)

        if len(p_lons) < 10:
            raise ValueError(f"Insufficient particles for origin density estimation: {len(p_lons)}")

        # 2. Compute 2D Gaussian KDE (PRD Section 10)
        sample_data = np.vstack([p_lons, p_lats])
        kde = stats.gaussian_kde(sample_data, bw_method=self.bandwidth_method)
        bw_factor = float(kde.factor)

        # 3. Mode Finding: Find point of maximum probability density
        # Initial search: evaluate on subsample of candidate particles
        rng = np.random.default_rng(42)
        n_candidates = min(len(p_lons), 500)
        cand_indices = rng.choice(len(p_lons), size=n_candidates, replace=False)
        cand_pts = sample_data[:, cand_indices]
        log_densities = kde.logpdf(cand_pts)
        best_cand = cand_pts[:, np.argmax(log_densities)]

        # Refine continuous mode using Nelder-Mead optimization on -logpdf
        try:
            opt_res = opt.minimize(
                lambda x: -float(kde.logpdf(x[:, None])[0]),
                best_cand,
                method="Nelder-Mead",
                options={"maxiter": 100, "xatol": 1e-5},
            )
            mode_lon, mode_lat = float(opt_res.x[0]), float(opt_res.x[1])
        except Exception as e:
            logger.debug(f"Mode refinement exception ({e}), using candidate peak")
            mode_lon, mode_lat = float(best_cand[0]), float(best_cand[1])

        peak_dens = float(kde.evaluate(np.array([[mode_lon], [mode_lat]]))[0])

        # 4. Spatial Covariance Matrix Sigma_p
        cov_matrix_geodetic = np.cov(p_lons, p_lats)
        var_lon = float(cov_matrix_geodetic[0, 0])
        var_lat = float(cov_matrix_geodetic[1, 1])
        cov_lon_lat = float(cov_matrix_geodetic[0, 1])

        # Metric covariance matrix
        cos_lat = math.cos(mode_lat * DEG_TO_RAD)
        m_per_deg_lon = METERS_PER_DEGREE_LAT * cos_lat
        m_per_deg_lat = METERS_PER_DEGREE_LAT

        var_x_m2 = var_lon * (m_per_deg_lon**2)
        var_y_m2 = var_lat * (m_per_deg_lat**2)
        cov_xy_m2 = cov_lon_lat * (m_per_deg_lon * m_per_deg_lat)

        cov_dict_geodetic = {
            "var_lat": round(var_lat, 8),
            "var_lon": round(var_lon, 8),
            "cov_lon_lat": round(cov_lon_lat, 8),
        }

        cov_dict_metric = {
            "var_x_m2": round(var_x_m2, 2),
            "var_y_m2": round(var_y_m2, 2),
            "cov_xy_m2": round(cov_xy_m2, 2),
        }

        # 5. Generate 1-sigma, 2-sigma, 3-sigma Error Ellipses
        ellipses: dict[str, ConfidenceEllipse] = {}
        for s in [1, 2, 3]:
            key = f"{s}sigma"
            ellipses[key] = generate_confidence_ellipse(
                centroid_lon=mode_lon,
                centroid_lat=mode_lat,
                cov_matrix_geodetic=cov_matrix_geodetic,
                sigma_level=s,
            )

        region_area_3sigma_km2 = ellipses["3sigma"].area_km2

        # 6. Release Time Window Estimation
        if time_window is not None:
            t_win_start, t_win_end = time_window
        else:
            # Physical uncertainty interval (+/- 1.5h around estimated release time)
            delta_uncertainty_h = max(1.0, min(3.0, 0.25 * age_h))
            t_win_start = release_t - timedelta(hours=delta_uncertainty_h)
            t_win_end = release_t + timedelta(hours=delta_uncertainty_h)

        return OriginEstimateResult(
            case_id=cid,
            centroid=(round(mode_lon, 5), round(mode_lat, 5)),
            centroid_lat_lon=(round(mode_lat, 5), round(mode_lon, 5)),
            covariance_matrix=cov_dict_geodetic,
            covariance_matrix_m2=cov_dict_metric,
            time_window_start=t_win_start,
            time_window_end=t_win_end,
            region_area_km2=round(region_area_3sigma_km2, 2),
            confidence_pct=min(100.0, max(0.0, round(conf, 1))),
            data_source=src,
            ellipses=ellipses,
            kde_bandwidth=round(bw_factor, 4),
            peak_density=round(peak_dens, 4),
            n_particles=len(p_lons),
            particle_trajectory_ref=None,
        )
