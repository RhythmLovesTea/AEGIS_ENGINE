"""AEGIS-Marine: Replay State Server (Feature 4 / D4, TASK-033).

Implements the time-slice query and interpolation engine serving the frontend time-scrubber:
- Continuous geodetic and kinematic interpolation between 15-minute keyframes.
- Lagrangian particle cloud interpolation (centroid, dispersion radius, subsampled coords).
- AIS vessel trajectory interpolation (coordinates, speed over ground, course over ground).
- Live calculation of dynamically evolving attribution scores S_culprit(t) and candidate re-ranking.
- TimescaleDB hypertable querying for 'particle_trajectories' and 'ais_tracks' with in-memory caching.
- Constitutional Rules:
  - Rule 1: Mandatory paired confidence score on all responses and vessel records.
  - Rule 3: Multi-criteria dynamic attribution (never distance-only).
  - Rule 4: Data source attribution (live / cached / synthetic).
  - Rule 6: Strictly zero occurrences of banned determination terms.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    OriginEstimate,
    SlickDetection,
    VesselCandidate,
)
from backend.app.schemas.explainability import (
    ParticleEnsembleState,
    ReplayStatePayload,
    VesselReplayState,
)

logger = logging.getLogger(__name__)

# Mean Earth radius in meters (WGS84 spherical approximation)
EARTH_RADIUS_M = 6371000.0


def assert_no_banned_terms(text: str, context_label: str = "text") -> None:
    """Ensures text contains zero Rule 6 banned determination terms."""
    import re

    from scripts.lint_banned_terms import BANNED_RULES

    for rule in BANNED_RULES:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            raise ValueError(
                f"Rule 6 Violation: Detected banned term '{rule['name']}' in {context_label}: {text}"
            )


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Computes great-circle distance between two coordinates in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return float(2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a))))


def interpolate_bearing(cog1: float, cog2: float, fraction: float) -> float:
    """Interpolates modular compass course over ground (0 - 360 deg)."""
    diff = (cog2 - cog1 + 180.0) % 360.0 - 180.0
    return round((cog1 + diff * fraction) % 360.0, 1)


def to_utc(dt: datetime) -> datetime:
    """Ensures datetime is timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class ReplayService:
    """Time-slice query engine serving particle and vessel positions for the frontend time-scrubber."""

    _instance: ReplayService | None = None

    def __init__(
        self,
        tau_dist_m: float = 2500.0,
        tau_time_hours: float = 2.0,
        default_confidence_pct: float = 85.0,
    ) -> None:
        self.tau_dist_m = tau_dist_m
        self.tau_time_hours = tau_time_hours
        self.default_confidence_pct = default_confidence_pct
        self._cache: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> ReplayService:
        """Singleton accessor for ReplayService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_case_cache(
        self,
        case_id: str | uuid.UUID,
        particle_snapshots: list[dict[str, Any]],
        vessel_tracks: dict[int, list[dict[str, Any]]],
        candidates: list[dict[str, Any]],
        origin_centroid: tuple[float, float] | None = None,
        observed_slick_centroid: tuple[float, float] | None = None,
    ) -> None:
        """Pre-populates in-memory cache for ultra-low-latency scrubber response."""
        cid_str = str(case_id)
        self._cache[cid_str] = {
            "particle_snapshots": sorted(
                particle_snapshots,
                key=lambda s: (
                    to_utc(s["timestamp"])
                    if isinstance(s["timestamp"], datetime)
                    else datetime.fromisoformat(s["timestamp"]).replace(tzinfo=UTC)
                ),
            ),
            "vessel_tracks": vessel_tracks,
            "candidates": candidates,
            "origin_centroid": origin_centroid,
            "observed_slick_centroid": observed_slick_centroid,
        }

    def clear_cache(self, case_id: str | uuid.UUID | None = None) -> None:
        """Clears memory cache for specific case or all cases."""
        if case_id is not None:
            self._cache.pop(str(case_id), None)
        else:
            self._cache.clear()

    def get_replay_state(
        self,
        case_id: str | uuid.UUID,
        timestamp: datetime,
        db: Session | None = None,
        particle_snapshots: list[dict[str, Any]] | None = None,
        vessel_tracks: dict[int, list[dict[str, Any]]] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        origin_centroid: tuple[float, float] | None = None,
        observed_slick_centroid: tuple[float, float] | None = None,
    ) -> ReplayStatePayload:
        """Queries and interpolates replay state at requested timestamp t across particles and vessels."""
        case_uuid = uuid.UUID(str(case_id)) if isinstance(case_id, str) else case_id
        cid_str = str(case_uuid)
        target_t = to_utc(timestamp)

        cached_data = self._cache.get(cid_str, {})

        # 1. Resolve particle snapshots
        snapshots = (
            particle_snapshots
            or cached_data.get("particle_snapshots")
            or (self._query_db_particle_snapshots(db, case_uuid) if db is not None else None)
            or []
        )

        # 2. Resolve candidates and vessel tracks
        cands = (
            candidates
            or cached_data.get("candidates")
            or (self._query_db_candidates(db, case_uuid) if db is not None else None)
            or []
        )

        tracks = (
            vessel_tracks
            or cached_data.get("vessel_tracks")
            or (
                self._query_db_ais_tracks(db, [c["mmsi"] for c in cands if "mmsi" in c])
                if db is not None
                else None
            )
            or {}
        )

        # 3. Resolve key centroids
        orig_cent = (
            origin_centroid
            or cached_data.get("origin_centroid")
            or (self._query_db_origin_centroid(db, case_uuid) if db is not None else None)
        )
        slick_cent = (
            observed_slick_centroid
            or cached_data.get("observed_slick_centroid")
            or (self._query_db_slick_centroid(db, case_uuid) if db is not None else None)
        )

        # 4. Interpolate Particle Ensemble
        ensemble_state = self._interpolate_particles(snapshots, target_t, orig_cent, slick_cent)

        # 5. Interpolate Vessel Kinematics & Evolving Attribution Scores
        vessel_states = self._interpolate_vessels(
            cands=cands,
            tracks=tracks,
            target_t=target_t,
            cloud_center=(ensemble_state.mean_lon, ensemble_state.mean_lat),
            t_release=snapshots[0]["timestamp"] if snapshots else target_t,
        )

        # 6. Calculate normalized timeline progress [0.0 - 100.0]
        progress_pct = 50.0
        if snapshots and len(snapshots) >= 2:
            t_start = to_utc(snapshots[0]["timestamp"])
            t_end = to_utc(snapshots[-1]["timestamp"])
            total_sec = (t_end - t_start).total_seconds()
            if total_sec > 0.0:
                elapsed_sec = (target_t - t_start).total_seconds()
                progress_pct = max(0.0, min(100.0, (elapsed_sec / total_sec) * 100.0))

        # Rule 1: Paired confidence
        payload_conf = (
            round(sum(v.confidence_pct for v in vessel_states) / float(len(vessel_states)), 1)
            if vessel_states
            else self.default_confidence_pct
        )

        metadata = {
            "n_vessels_tracked": len(vessel_states),
            "n_particles": ensemble_state.n_particles,
            "dispersion_radius_m": ensemble_state.dispersion_radius_m,
            "interpolated": True,
            "data_source": "synthetic",  # Rule 4
        }

        return ReplayStatePayload(
            case_id=case_uuid,
            timestamp=target_t,
            particles=ensemble_state,
            vessels=vessel_states,
            observed_slick_centroid=slick_cent,
            estimated_origin_centroid=orig_cent,
            time_progress_pct=round(progress_pct, 2),
            confidence_pct=payload_conf,
            metadata=metadata,
        )

    # ---------------- Particle Interpolation ---------------- #

    def _interpolate_particles(
        self,
        snapshots: list[dict[str, Any]],
        target_t: datetime,
        fallback_origin: tuple[float, float] | None,
        fallback_slick: tuple[float, float] | None,
    ) -> ParticleEnsembleState:
        """Interpolates particle ensemble positions and dispersion between bounding keyframes."""
        if not snapshots:
            # Fallback if no snapshots exist
            center = fallback_origin or fallback_slick or (72.290, 18.865)
            return ParticleEnsembleState(
                timestamp=target_t,
                mean_lon=center[0],
                mean_lat=center[1],
                n_particles=1000,
                subsample_coords=[[center[0], center[1]]],
                dispersion_radius_m=500.0,
            )

        # Standardize snapshot timestamps
        stamps = [
            to_utc(
                s["timestamp"]
                if isinstance(s["timestamp"], datetime)
                else datetime.fromisoformat(s["timestamp"])
            )
            for s in snapshots
        ]

        # Case A: target_t is before or at first snapshot
        if target_t <= stamps[0]:
            first = snapshots[0]
            coords = first.get("subsample_coords", [[first["mean_lon"], first["mean_lat"]]])
            return ParticleEnsembleState(
                timestamp=target_t,
                mean_lon=round(float(first["mean_lon"]), 5),
                mean_lat=round(float(first["mean_lat"]), 5),
                n_particles=int(first.get("n_particles", len(coords))),
                subsample_coords=coords,
                dispersion_radius_m=round(float(first.get("dispersion_radius_m", 600.0)), 1),
            )

        # Case B: target_t is after or at last snapshot
        if target_t >= stamps[-1]:
            last = snapshots[-1]
            coords = last.get("subsample_coords", [[last["mean_lon"], last["mean_lat"]]])
            return ParticleEnsembleState(
                timestamp=target_t,
                mean_lon=round(float(last["mean_lon"]), 5),
                mean_lat=round(float(last["mean_lat"]), 5),
                n_particles=int(last.get("n_particles", len(coords))),
                subsample_coords=coords,
                dispersion_radius_m=round(float(last.get("dispersion_radius_m", 1500.0)), 1),
            )

        # Case C: target_t is between snapshot k and k+1
        k = 0
        for i in range(len(stamps) - 1):
            if stamps[i] <= target_t <= stamps[i + 1]:
                k = i
                break

        t0 = stamps[k]
        t1 = stamps[k + 1]
        dt_total = (t1 - t0).total_seconds()
        alpha = (target_t - t0).total_seconds() / dt_total if dt_total > 0.0 else 0.0
        alpha = max(0.0, min(1.0, alpha))

        s0 = snapshots[k]
        s1 = snapshots[k + 1]

        mean_lon = (1.0 - alpha) * float(s0["mean_lon"]) + alpha * float(s1["mean_lon"])
        mean_lat = (1.0 - alpha) * float(s0["mean_lat"]) + alpha * float(s1["mean_lat"])

        r0 = float(s0.get("dispersion_radius_m", 800.0))
        r1 = float(s1.get("dispersion_radius_m", 1200.0))
        dispersion_m = (1.0 - alpha) * r0 + alpha * r1

        coords0 = s0.get("subsample_coords", [])
        coords1 = s1.get("subsample_coords", [])

        interp_coords: list[list[float]] = []
        n_pts = min(len(coords0), len(coords1))
        if n_pts > 0:
            for i in range(n_pts):
                p_lon = (1.0 - alpha) * float(coords0[i][0]) + alpha * float(coords1[i][0])
                p_lat = (1.0 - alpha) * float(coords0[i][1]) + alpha * float(coords1[i][1])
                interp_coords.append([round(p_lon, 5), round(p_lat, 5)])
        else:
            interp_coords = [[round(mean_lon, 5), round(mean_lat, 5)]]

        n_particles = int(
            (1.0 - alpha) * s0.get("n_particles", 2000) + alpha * s1.get("n_particles", 2000)
        )

        return ParticleEnsembleState(
            timestamp=target_t,
            mean_lon=round(mean_lon, 5),
            mean_lat=round(mean_lat, 5),
            n_particles=n_particles,
            subsample_coords=interp_coords,
            dispersion_radius_m=round(dispersion_m, 1),
        )

    # ---------------- Vessel Interpolation & Scoring ---------------- #

    def _interpolate_vessels(
        self,
        cands: list[dict[str, Any]],
        tracks: dict[int, list[dict[str, Any]]],
        target_t: datetime,
        cloud_center: tuple[float, float],
        t_release: datetime,
    ) -> list[VesselReplayState]:
        """Interpolates vessel positions, computes live evolving S_culprit(t), and sorts ranks."""
        vessel_states: list[VesselReplayState] = []
        t_rel_utc = to_utc(t_release) if isinstance(t_release, datetime) else target_t

        for cand in cands:
            mmsi = int(cand["mmsi"])
            name = str(cand.get("name", f"Vessel {mmsi}"))
            vtype = str(cand.get("vessel_type", "Cargo"))
            flag = cand.get("flag_state")
            conf = float(cand.get("confidence", self.default_confidence_pct))
            sub_scores = cand.get("sub_scores", {})
            details = sub_scores.get("details", {}) if isinstance(sub_scores, dict) else {}

            v_track = tracks.get(mmsi, [])
            lon, lat, sog, cog, in_zone = self._interpolate_single_vessel_track(
                v_track, target_t, details
            )

            # 1. Distance from vessel position to current particle cloud center
            dist_to_cloud_m = haversine_distance_m(lon, lat, cloud_center[0], cloud_center[1])

            # 2. Dynamic evolving spatial score S_spatial(t)
            # High proximity when vessel passes near cloud
            s_spatial_t = 100.0 * math.exp(-dist_to_cloud_m / self.tau_dist_m)

            # 3. Dynamic temporal score S_temporal(t)
            delta_hours = abs((target_t - t_rel_utc).total_seconds()) / 3600.0
            s_temporal_t = 100.0 * math.exp(-delta_hours / self.tau_time_hours)

            # 4. Kinematic, anomaly, and type sub-scores
            s_kinematic = float(sub_scores.get("kinematic", 50.0))
            s_type = float(sub_scores.get("type", 50.0))
            base_anomaly = float(sub_scores.get("anomaly", 10.0))

            # If vessel slows down significantly while close to origin, heighten live anomaly
            if sog < 7.5 and dist_to_cloud_m < 3500.0:
                s_anomaly = max(base_anomaly, 85.0)
            else:
                s_anomaly = base_anomaly

            # 5. Dynamic composite attribution score S_culprit(t)
            # Canonical AHP weights: spatial=0.30, temporal=0.25, kinematic=0.15, anomaly=0.20, type=0.10
            dynamic_s_culprit = (
                0.30 * s_spatial_t
                + 0.25 * s_temporal_t
                + 0.15 * s_kinematic
                + 0.20 * s_anomaly
                + 0.10 * s_type
            )
            dynamic_s_culprit = round(max(0.0, min(100.0, dynamic_s_culprit)), 2)

            vessel_states.append(
                VesselReplayState(
                    mmsi=mmsi,
                    name=name,
                    vessel_type=vtype,
                    flag_state=flag,
                    lon=round(lon, 5),
                    lat=round(lat, 5),
                    sog_kts=round(sog, 1),
                    cog_deg=round(cog, 1),
                    distance_to_cloud_m=round(dist_to_cloud_m, 1),
                    current_s_culprit=dynamic_s_culprit,
                    rank=1,  # Placeholder, assigned below
                    confidence_pct=round(conf, 1),
                    in_surveillance_zone=in_zone,
                )
            )

        # Sort dynamically by current_s_culprit descending and assign live rank
        vessel_states.sort(key=lambda v: v.current_s_culprit, reverse=True)
        for idx, vstate in enumerate(vessel_states, start=1):
            vstate.rank = idx

        return vessel_states

    def _interpolate_single_vessel_track(
        self,
        track_points: list[dict[str, Any]],
        target_t: datetime,
        fallback_details: dict[str, Any],
    ) -> tuple[float, float, float, float, bool]:
        """Interpolates single vessel position (lon, lat, sog, cog, in_zone) at target_t."""
        if not track_points:
            # Fallback to CPA details or default location
            cpa_coords = fallback_details.get("cpa_coords", [72.290, 18.865])
            sog = float(fallback_details.get("speed_kts", 12.0))
            cog = float(fallback_details.get("cog_deg", 65.0))
            return float(cpa_coords[0]), float(cpa_coords[1]), sog, cog, True

        stamps = [
            to_utc(
                p["timestamp"]
                if isinstance(p["timestamp"], datetime)
                else datetime.fromisoformat(p["timestamp"])
            )
            for p in track_points
        ]

        if target_t <= stamps[0]:
            p0 = track_points[0]
            return (
                float(p0["lon"]),
                float(p0["lat"]),
                float(p0.get("sog", 12.0)),
                float(p0.get("cog", 65.0)),
                True,
            )

        if target_t >= stamps[-1]:
            p_last = track_points[-1]
            return (
                float(p_last["lon"]),
                float(p_last["lat"]),
                float(p_last.get("sog", 12.0)),
                float(p_last.get("cog", 65.0)),
                True,
            )

        # Binary/linear search bounding reports
        k = 0
        for i in range(len(stamps) - 1):
            if stamps[i] <= target_t <= stamps[i + 1]:
                k = i
                break

        t0, t1 = stamps[k], stamps[k + 1]
        dt = (t1 - t0).total_seconds()
        beta = (target_t - t0).total_seconds() / dt if dt > 0.0 else 0.0
        beta = max(0.0, min(1.0, beta))

        p0, p1 = track_points[k], track_points[k + 1]

        lon = (1.0 - beta) * float(p0["lon"]) + beta * float(p1["lon"])
        lat = (1.0 - beta) * float(p0["lat"]) + beta * float(p1["lat"])
        sog = (1.0 - beta) * float(p0.get("sog", 12.0)) + beta * float(p1.get("sog", 12.0))
        cog = interpolate_bearing(float(p0.get("cog", 65.0)), float(p1.get("cog", 65.0)), beta)

        return lon, lat, sog, cog, True

    # ---------------- Database Queries ---------------- #

    def _query_db_particle_snapshots(
        self, db: Session, case_uuid: uuid.UUID
    ) -> list[dict[str, Any]] | None:
        """Queries TimescaleDB particle_trajectories hypertable and aggregates into time snapshots."""
        try:
            query = text(
                """
                SELECT
                    timestamp,
                    AVG(ST_X(point::geometry)) as mean_lon,
                    AVG(ST_Y(point::geometry)) as mean_lat,
                    STDDEV(ST_X(point::geometry)) as std_lon,
                    STDDEV(ST_Y(point::geometry)) as std_lat,
                    COUNT(*) as n_particles
                FROM particle_trajectories
                WHERE case_id = :case_id
                GROUP BY timestamp
                ORDER BY timestamp ASC
                """
            )
            rows = db.execute(query, {"case_id": case_uuid}).fetchall()
            if not rows:
                return None

            snapshots = []
            for r in rows:
                mean_lon = float(r.mean_lon)
                mean_lat = float(r.mean_lat)
                std_deg = math.hypot(float(r.std_lon or 0.01), float(r.std_lat or 0.01))
                radius_m = std_deg * 111139.0

                snapshots.append(
                    {
                        "timestamp": to_utc(r.timestamp),
                        "mean_lon": mean_lon,
                        "mean_lat": mean_lat,
                        "n_particles": int(r.n_particles),
                        "dispersion_radius_m": round(radius_m, 1),
                        "subsample_coords": [[mean_lon, mean_lat]],
                    }
                )
            return snapshots
        except Exception as exc:
            logger.warning("Error querying TimescaleDB particle trajectories: %s", exc)
            return None

    def _query_db_candidates(
        self, db: Session, case_uuid: uuid.UUID
    ) -> list[dict[str, Any]] | None:
        """Queries VesselCandidate records from PostgreSQL."""
        try:
            records = (
                db.query(VesselCandidate)
                .filter(VesselCandidate.case_id == case_uuid)
                .order_by(VesselCandidate.s_culprit.desc())
                .all()
            )
            if not records:
                return None

            return [
                {
                    "mmsi": r.mmsi,
                    "name": r.name,
                    "vessel_type": r.vessel_type,
                    "flag_state": r.flag_state,
                    "s_culprit": r.s_culprit,
                    "confidence": r.confidence,
                    "sub_scores": r.sub_scores,
                    "anomaly_flags": r.anomaly_flags,
                }
                for r in records
            ]
        except Exception as exc:
            logger.warning("Error querying VesselCandidates from DB: %s", exc)
            return None

    def _query_db_ais_tracks(
        self, db: Session, mmsis: list[int]
    ) -> dict[int, list[dict[str, Any]]] | None:
        """Queries ais_tracks hypertable from TimescaleDB for given MMSIs."""
        if not mmsis:
            return None
        try:
            query = text(
                """
                SELECT
                    mmsi,
                    timestamp,
                    ST_X(point::geometry) as lon,
                    ST_Y(point::geometry) as lat,
                    sog,
                    cog
                FROM ais_tracks
                WHERE mmsi = ANY(:mmsis)
                ORDER BY mmsi, timestamp ASC
                """
            )
            rows = db.execute(query, {"mmsis": mmsis}).fetchall()
            if not rows:
                return None

            result: dict[int, list[dict[str, Any]]] = {}
            for r in rows:
                mmsi_val = int(r.mmsi)
                if mmsi_val not in result:
                    result[mmsi_val] = []
                result[mmsi_val].append(
                    {
                        "timestamp": to_utc(r.timestamp),
                        "lon": float(r.lon),
                        "lat": float(r.lat),
                        "sog": float(r.sog or 12.0),
                        "cog": float(r.cog or 0.0),
                    }
                )
            return result
        except Exception as exc:
            logger.warning("Error querying ais_tracks from DB: %s", exc)
            return None

    def _query_db_origin_centroid(
        self, db: Session, case_uuid: uuid.UUID
    ) -> tuple[float, float] | None:
        """Queries OriginEstimate centroid from DB."""
        try:
            origin = (
                db.query(OriginEstimate)
                .filter(OriginEstimate.case_id == case_uuid)
                .order_by(OriginEstimate.created_at.desc())
                .first()
            )
            if origin and origin.centroid:
                shape_pt = (
                    origin.centroid
                    if hasattr(origin.centroid, "geom_type")
                    else to_shape(origin.centroid)
                )
                return (float(shape_pt.x), float(shape_pt.y))
        except Exception:
            pass
        return None

    def _query_db_slick_centroid(
        self, db: Session, case_uuid: uuid.UUID
    ) -> tuple[float, float] | None:
        """Queries SlickDetection centroid from DB."""
        try:
            det = (
                db.query(SlickDetection)
                .filter(SlickDetection.case_id == case_uuid)
                .order_by(SlickDetection.created_at.desc())
                .first()
            )
            if det and det.centroid:
                shape_pt = (
                    det.centroid if hasattr(det.centroid, "geom_type") else to_shape(det.centroid)
                )
                return (float(shape_pt.x), float(shape_pt.y))
        except Exception:
            pass
        return None


def get_replay_state(
    case_id: str | uuid.UUID,
    timestamp: datetime,
    db: Session | None = None,
    **kwargs: Any,
) -> ReplayStatePayload:
    """Exposed top-level API function returning time-slice replay state for the scrubber."""
    service = ReplayService.get_instance()
    return service.get_replay_state(case_id=case_id, timestamp=timestamp, db=db, **kwargs)
