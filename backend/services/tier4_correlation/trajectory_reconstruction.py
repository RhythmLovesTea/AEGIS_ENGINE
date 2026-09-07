"""AEGIS-Marine: Vessel Kinematic Trajectory Reconstruction (Cubic-Spline Interpolation).

Implements Tier 4 AIS Trajectory Reconstruction (PRD Section 11 & Architecture Section 4.4):
1. Groups discrete AIS reports by vessel MMSI.
2. Validates temporal monotonicity and discards duplicate timestamps.
3. Projects coordinates to local metric UTM zone (EPSG:326xx / 327xx) to eliminate latitude distortion.
4. Fits cubic spline interpolation (scipy.interpolate.CubicSpline) to reconstruct continuous
   positions, velocity vectors, and heading angles at uniform 1-minute intervals (dt = 60 s).
5. Computes Closest Point of Approach (CPA) between vessel continuous trajectory and estimated
   origin density centroid mu_p (timestamp t_CPA, distance d_CPA, speed sog_CPA, course cog_CPA).

Adheres to:
- PRD Section 11 (FR-12, C9) & Architecture Section 4.4.
- Rule 1: Mandatory paired confidence score in [0.0, 100.0].
- Rule 4: Data source identification ('live' | 'cached' | 'synthetic').
- Rule 6: Strictly zero occurrences of banned terms.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import numpy as np
import pyproj
import scipy.interpolate as interp
import scipy.optimize as opt

from backend.services.data_adapters.ais_adapter import AISTrackRecord

logger = logging.getLogger("aegis.trajectory_reconstruction")

# Conversion constants
MPS_TO_KNOTS = 1.9438444924
KNOTS_TO_MPS = 0.5144444444


def get_utm_epsg(lon: float, lat: float) -> int:
    """Calculates the standard UTM EPSG code for a WGS84 coordinate.

    Args:
        lon: Longitude in degrees [-180.0, 180.0].
        lat: Latitude in degrees [-90.0, 90.0].

    Returns:
        EPSG integer code (e.g. 32643 for Zone 43N).
    """
    zone = int((lon + 180.0) / 6.0) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


@dataclass
class InterpolatedTrackPoint:
    """Continuous vessel trajectory state at a uniform interpolated timestep."""

    timestamp: datetime
    lon: float
    lat: float
    x_utm: float
    y_utm: float
    sog_kts: (
        float  # Speed over ground in knots (reported transponder SOG if available, else derived)
    )
    cog_deg: float  # Course over ground in degrees (0-360 deg)
    distance_to_origin_m: float  # Euclidean distance to origin centroid (meters)
    derived_sog_kts: float | None = None  # Speed derived from spatial spline derivatives (knots)


@dataclass
class ClosestPointOfApproach:
    """Closest Point of Approach (CPA) between reconstructed vessel trajectory and origin centroid mu_p."""

    timestamp: datetime  # t_CPA
    distance_m: float  # d_CPA in meters
    distance_km: float  # d_CPA in kilometers
    lon: float  # Vessel longitude at CPA
    lat: float  # Vessel latitude at CPA
    sog_kts: float  # Vessel speed at CPA in knots
    cog_deg: float  # Vessel course heading at CPA in degrees
    time_delta_to_release_hours: float | None = None  # |t_CPA - t_release| (hours)
    derived_sog_kts: float | None = None  # Kinematic displacement speed in knots


@dataclass
class ReconstructedTrajectory:
    """Continuous kinematic trajectory reconstruction for a single vessel candidate."""

    mmsi: int
    vessel_name: str
    vessel_type: str
    imo: int | None
    n_discrete_reports: int
    n_interpolated_points: int
    start_time: datetime
    end_time: datetime
    duration_hours: float
    discrete_points: list[AISTrackRecord]
    interpolated_points: list[InterpolatedTrackPoint]
    cpa: ClosestPointOfApproach
    utm_epsg: int
    confidence_pct: float  # Rule 1: [0.0, 100.0]
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"  # Rule 4

    def to_geojson_feature(self) -> dict[str, Any]:
        """Serializes continuous trajectory into a GeoJSON Feature LineString."""
        coords = [[p.lon, p.lat] for p in self.interpolated_points]
        timestamps = [p.timestamp.isoformat() for p in self.interpolated_points]
        sogs = [round(p.sog_kts, 1) for p in self.interpolated_points]
        cogs = [round(p.cog_deg, 1) for p in self.interpolated_points]

        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "mmsi": self.mmsi,
                "vessel_name": self.vessel_name,
                "vessel_type": self.vessel_type,
                "imo": self.imo,
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "duration_hours": round(self.duration_hours, 2),
                "n_discrete_reports": self.n_discrete_reports,
                "n_interpolated_points": self.n_interpolated_points,
                "timestamps": timestamps,
                "sog_series": sogs,
                "cog_series": cogs,
                "cpa": {
                    "timestamp": self.cpa.timestamp.isoformat(),
                    "distance_km": round(self.cpa.distance_km, 3),
                    "distance_m": round(self.cpa.distance_m, 1),
                    "lon": round(self.cpa.lon, 6),
                    "lat": round(self.cpa.lat, 6),
                    "sog_kts": round(self.cpa.sog_kts, 1),
                    "cog_deg": round(self.cpa.cog_deg, 1),
                    "time_delta_to_release_hours": (
                        round(self.cpa.time_delta_to_release_hours, 2)
                        if self.cpa.time_delta_to_release_hours is not None
                        else None
                    ),
                },
                "confidence_pct": self.confidence_pct,
                "data_source": self.data_source,
            },
        }


class TrajectoryReconstructor:
    """Reconstructs continuous vessel trajectories from discrete AIS reports using cubic splines."""

    def __init__(self, step_seconds: float = 60.0) -> None:
        """Initialize reconstructor with desired uniform interpolation interval.

        Args:
            step_seconds: Resampling interval in seconds (default 60.0 s = 1 minute).
        """
        self.step_seconds = step_seconds

    def reconstruct_vessel_trajectory(
        self,
        records: list[AISTrackRecord],
        origin_centroid: tuple[float, float],
        t_release: datetime | None = None,
    ) -> ReconstructedTrajectory:
        """Reconstructs continuous trajectory and evaluates CPA for a single vessel.

        Args:
            records: Discrete AIS track reports for one MMSI.
            origin_centroid: (lon, lat) tuple of estimated spill origin.
            t_release: Optional estimated release time for computing temporal offset.

        Returns:
            ReconstructedTrajectory containing continuous 1-minute points and CPA.
        """
        if not records:
            raise ValueError("Cannot reconstruct trajectory from empty records list.")

        # 1. Sort and deduplicate timestamps
        sorted_records = sorted(records, key=lambda r: r.timestamp)
        deduped_records: list[AISTrackRecord] = []
        seen_timestamps: set[datetime] = set()

        for r in sorted_records:
            ts = r.timestamp
            if ts not in seen_timestamps:
                seen_timestamps.add(ts)
                deduped_records.append(r)

        primary = deduped_records[0]
        mmsi = primary.mmsi
        vessel_name = primary.vessel_name
        vessel_type = primary.vessel_type
        imo = primary.imo
        data_source = primary.data_source

        t0 = deduped_records[0].timestamp
        t_final = deduped_records[-1].timestamp
        duration_sec = (t_final - t0).total_seconds()
        duration_hours = duration_sec / 3600.0

        # 2. Project to local metric UTM zone
        mean_lon = float(np.mean([r.lon for r in deduped_records]))
        mean_lat = float(np.mean([r.lat for r in deduped_records]))
        utm_epsg = get_utm_epsg(mean_lon, mean_lat)

        fwd_transformer = pyproj.Transformer.from_crs(
            "EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True
        )
        inv_transformer = pyproj.Transformer.from_crs(
            f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True
        )

        origin_x, origin_y = fwd_transformer.transform(origin_centroid[0], origin_centroid[1])

        # Convert discrete reports to UTM coordinates and time offsets
        t_offsets = np.array(
            [(r.timestamp - t0).total_seconds() for r in deduped_records], dtype=np.float64
        )
        geo_lons = np.array([r.lon for r in deduped_records], dtype=np.float64)
        geo_lats = np.array([r.lat for r in deduped_records], dtype=np.float64)
        xs_utm, ys_utm = fwd_transformer.transform(geo_lons, geo_lats)

        # 3. Fit Interpolation Scheme
        n_points = len(deduped_records)

        # Check for reported transponder SOG values to enable dual-speed reporting
        valid_sog_offsets = []
        valid_sogs = []
        for r in deduped_records:
            if r.sog is not None:
                valid_sog_offsets.append((r.timestamp - t0).total_seconds())
                valid_sogs.append(float(r.sog))

        sog_interp_fn = None
        if len(valid_sog_offsets) >= 2:
            sog_interp_fn = interp.interp1d(
                valid_sog_offsets, valid_sogs, kind="linear", fill_value="extrapolate"
            )
        elif len(valid_sog_offsets) == 1:
            single_val = valid_sogs[0]

            def _const_sog(_t: float, val: float = single_val) -> float:
                return val

            sog_interp_fn = _const_sog

        # Define uniform 1-minute query times
        if duration_sec <= 0:
            query_times = np.array([0.0])
        else:
            query_times = np.arange(0.0, duration_sec + 0.5 * self.step_seconds, self.step_seconds)
            if query_times[-1] < duration_sec:
                query_times = np.append(query_times, duration_sec)

        interpolated_points: list[InterpolatedTrackPoint] = []

        if n_points == 1:
            # Single discrete point fallback
            lon_pt, lat_pt = float(geo_lons[0]), float(geo_lats[0])
            x_pt, y_pt = float(xs_utm[0]), float(ys_utm[0])
            sog_pt = float(primary.sog) if primary.sog is not None else 0.0
            cog_pt = float(primary.cog) if primary.cog is not None else 0.0
            d_origin = math.hypot(x_pt - origin_x, y_pt - origin_y)

            interpolated_points.append(
                InterpolatedTrackPoint(
                    timestamp=t0,
                    lon=round(lon_pt, 6),
                    lat=round(lat_pt, 6),
                    x_utm=round(x_pt, 1),
                    y_utm=round(y_pt, 1),
                    sog_kts=round(sog_pt, 1),
                    cog_deg=round(cog_pt, 1),
                    distance_to_origin_m=round(d_origin, 1),
                    derived_sog_kts=0.0,
                )
            )

            cpa_ts = t0
            cpa_dist_m = d_origin
            cpa_lon = lon_pt
            cpa_lat = lat_pt
            cpa_sog = sog_pt
            cpa_derived_sog = 0.0
            cpa_cog = cog_pt

        elif n_points == 2:
            # Linear interpolation for 2 points
            interp_x = interp.interp1d(t_offsets, xs_utm, kind="linear")
            interp_y = interp.interp1d(t_offsets, ys_utm, kind="linear")

            vx_mps = (xs_utm[1] - xs_utm[0]) / max(1.0, duration_sec)
            vy_mps = (ys_utm[1] - ys_utm[0]) / max(1.0, duration_sec)
            derived_sog_calc = math.hypot(vx_mps, vy_mps) * MPS_TO_KNOTS
            cog_calc = (math.degrees(math.atan2(vx_mps, vy_mps)) + 360.0) % 360.0

            interp_xs = interp_x(query_times)
            interp_ys = interp_y(query_times)
            interp_lons, interp_lats = inv_transformer.transform(interp_xs, interp_ys)

            for i, t_val in enumerate(query_times):
                pt_time = t0 + timedelta(seconds=float(t_val))
                px, py = float(interp_xs[i]), float(interp_ys[i])
                d_m = math.hypot(px - origin_x, py - origin_y)
                sog_val = (
                    float(sog_interp_fn(t_val)) if sog_interp_fn is not None else derived_sog_calc
                )
                interpolated_points.append(
                    InterpolatedTrackPoint(
                        timestamp=pt_time,
                        lon=round(float(interp_lons[i]), 6),
                        lat=round(float(interp_lats[i]), 6),
                        x_utm=round(px, 1),
                        y_utm=round(py, 1),
                        sog_kts=round(sog_val, 1),
                        cog_deg=round(cog_calc, 1),
                        distance_to_origin_m=round(d_m, 1),
                        derived_sog_kts=round(derived_sog_calc, 1),
                    )
                )

            # Minimum distance along segment
            dists = np.hypot(interp_xs - origin_x, interp_ys - origin_y)
            min_idx = int(np.argmin(dists))
            cpa_t_val = float(query_times[min_idx])
            cpa_ts = t0 + timedelta(seconds=cpa_t_val)
            cpa_dist_m = float(dists[min_idx])
            cpa_lon = float(interp_lons[min_idx])
            cpa_lat = float(interp_lats[min_idx])
            cpa_derived_sog = derived_sog_calc
            cpa_sog = (
                float(sog_interp_fn(cpa_t_val)) if sog_interp_fn is not None else derived_sog_calc
            )
            cpa_cog = cog_calc

        else:
            # Full Cubic Spline Interpolation (N >= 3)
            cs_x = interp.CubicSpline(t_offsets, xs_utm, bc_type="natural")
            cs_y = interp.CubicSpline(t_offsets, ys_utm, bc_type="natural")

            interp_xs = cs_x(query_times)
            interp_ys = cs_y(query_times)
            interp_dx = cs_x(query_times, 1)  # vx in m/s
            interp_dy = cs_y(query_times, 1)  # vy in m/s

            interp_lons, interp_lats = inv_transformer.transform(interp_xs, interp_ys)

            for i, t_val in enumerate(query_times):
                pt_time = t0 + timedelta(seconds=float(t_val))
                px, py = float(interp_xs[i]), float(interp_ys[i])
                vx, vy = float(interp_dx[i]), float(interp_dy[i])
                derived_sog_i = math.hypot(vx, vy) * MPS_TO_KNOTS
                cog_i = (math.degrees(math.atan2(vx, vy)) + 360.0) % 360.0
                d_m = math.hypot(px - origin_x, py - origin_y)
                sog_i = float(sog_interp_fn(t_val)) if sog_interp_fn is not None else derived_sog_i

                interpolated_points.append(
                    InterpolatedTrackPoint(
                        timestamp=pt_time,
                        lon=round(float(interp_lons[i]), 6),
                        lat=round(float(interp_lats[i]), 6),
                        x_utm=round(px, 1),
                        y_utm=round(py, 1),
                        sog_kts=round(sog_i, 1),
                        cog_deg=round(cog_i, 1),
                        distance_to_origin_m=round(d_m, 1),
                        derived_sog_kts=round(derived_sog_i, 1),
                    )
                )

            # Continuous exact CPA optimization
            def dist_sq_func(t_sec: float) -> float:
                cx = float(cs_x(t_sec))
                cy = float(cs_y(t_sec))
                return (cx - origin_x) ** 2 + (cy - origin_y) ** 2

            # Find discrete minimum index as bracket seed
            dists = np.hypot(interp_xs - origin_x, interp_ys - origin_y)
            seed_idx = int(np.argmin(dists))
            seed_t = float(query_times[seed_idx])

            # Local bounded minimization
            bracket_a = max(0.0, seed_t - self.step_seconds)
            bracket_b = min(duration_sec, seed_t + self.step_seconds)
            res = opt.minimize_scalar(
                dist_sq_func,
                bounds=(bracket_a, bracket_b),
                method="bounded",
            )
            cpa_t_sec = float(res.x) if res.success else seed_t

            cpa_ts = t0 + timedelta(seconds=cpa_t_sec)
            cpa_dist_m = math.sqrt(dist_sq_func(cpa_t_sec))
            cpa_x = float(cs_x(cpa_t_sec))
            cpa_y = float(cs_y(cpa_t_sec))
            cpa_vx = float(cs_x(cpa_t_sec, 1))
            cpa_vy = float(cs_y(cpa_t_sec, 1))
            cpa_lon_f, cpa_lat_f = inv_transformer.transform(cpa_x, cpa_y)
            cpa_lon = float(cpa_lon_f)
            cpa_lat = float(cpa_lat_f)
            cpa_derived_sog = math.hypot(cpa_vx, cpa_vy) * MPS_TO_KNOTS
            cpa_sog = (
                float(sog_interp_fn(cpa_t_sec)) if sog_interp_fn is not None else cpa_derived_sog
            )
            cpa_cog = (math.degrees(math.atan2(cpa_vx, cpa_vy)) + 360.0) % 360.0

        # 4. Temporal delta to release time
        time_delta_hours = None
        if t_release is not None:
            rel_utc = t_release if t_release.tzinfo is not None else t_release.replace(tzinfo=UTC)
            time_delta_hours = abs((cpa_ts - rel_utc).total_seconds()) / 3600.0

        cpa_obj = ClosestPointOfApproach(
            timestamp=cpa_ts,
            distance_m=round(cpa_dist_m, 1),
            distance_km=round(cpa_dist_m / 1000.0, 3),
            lon=round(cpa_lon, 6),
            lat=round(cpa_lat, 6),
            sog_kts=round(cpa_sog, 1),
            cog_deg=round(cpa_cog, 1),
            time_delta_to_release_hours=time_delta_hours,
            derived_sog_kts=round(cpa_derived_sog, 1),
        )

        # 5. Rule 1 Confidence Calculation
        # Quality penalizes large max gaps between discrete reports
        intervals = np.diff(t_offsets) if len(t_offsets) > 1 else np.array([0.0])
        max_gap_min = float(np.max(intervals) / 60.0) if len(intervals) > 0 else 0.0
        gap_penalty = min(25.0, max(0.0, (max_gap_min - 30.0) * 0.3))
        report_bonus = min(10.0, len(deduped_records) * 0.5)
        trajectory_confidence = max(50.0, min(98.0, 85.0 + report_bonus - gap_penalty))

        return ReconstructedTrajectory(
            mmsi=mmsi,
            vessel_name=vessel_name,
            vessel_type=vessel_type,
            imo=imo,
            n_discrete_reports=len(deduped_records),
            n_interpolated_points=len(interpolated_points),
            start_time=t0,
            end_time=t_final,
            duration_hours=round(duration_hours, 2),
            discrete_points=deduped_records,
            interpolated_points=interpolated_points,
            cpa=cpa_obj,
            utm_epsg=utm_epsg,
            confidence_pct=round(trajectory_confidence, 1),
            data_source=data_source,
        )

    def reconstruct_all(
        self,
        records: list[AISTrackRecord],
        origin_centroid: tuple[float, float],
        t_release: datetime | None = None,
    ) -> dict[int, ReconstructedTrajectory]:
        """Groups records by MMSI and reconstructs trajectories for all vessels.

        Args:
            records: Collection of discrete AIS records for multiple vessels.
            origin_centroid: (lon, lat) tuple of estimated spill origin.
            t_release: Optional estimated release time.

        Returns:
            Dictionary mapping MMSI -> ReconstructedTrajectory.
        """
        grouped: dict[int, list[AISTrackRecord]] = {}
        for r in records:
            if r.mmsi not in grouped:
                grouped[r.mmsi] = []
            grouped[r.mmsi].append(r)

        results: dict[int, ReconstructedTrajectory] = {}
        for v_mmsi, v_records in grouped.items():
            try:
                traj = self.reconstruct_vessel_trajectory(
                    records=v_records,
                    origin_centroid=origin_centroid,
                    t_release=t_release,
                )
                results[v_mmsi] = traj
            except Exception as exc:
                logger.warning("Could not reconstruct trajectory for MMSI %d: %s", v_mmsi, exc)
                continue

        return results
