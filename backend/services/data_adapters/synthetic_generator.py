"""AEGIS-Marine: Synthetic Data Generator and Benchmark Fixture Builder.

Generates physically consistent synthetic datasets for:
1. Spaceborne SAR slick detection polygons and characterizations.
2. CMEMS surface currents and ERA5 surface wind forcing fields.
3. AIS kinematic vessel trajectories (5 benchmark vessels, including Tanker
   loitering in discharge speed band and dark transponder gap).
4. Full metadata manifest with data_source="synthetic" per rules.md Section 4.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"


def generate_slick_polygon(
    center_lat: float = 18.962,
    center_lon: float = 72.435,
    length_km: float = 4.2,
    width_km: float = 0.8,
    angle_deg: float = 65.0,
    num_points: int = 64,
) -> List[List[float]]:
    """Generate realistic asymmetric elongated slick polygon with a tapering tail."""
    coords = []
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # 1 deg lat ~= 111 km, 1 deg lon ~= 111 * cos(lat) km
    km_per_lat = 111.0
    km_per_lon = 111.0 * math.cos(math.radians(center_lat))

    for i in range(num_points):
        theta = 2.0 * math.pi * (i / num_points)
        # Asymmetric tear-drop / elongated plume
        # x along length, y along width
        # Tapering tail towards negative x
        elongation = math.cos(theta)
        taper = 1.0 + 0.35 * elongation  # Thicker at head, thinner at tail
        x_km = (length_km / 2.0) * elongation
        y_km = (width_km / 2.0) * math.sin(theta) * taper

        # Rotate by angle_deg
        x_rot = x_km * cos_a - y_km * sin_a
        y_rot = x_km * sin_a + y_km * cos_a

        lat = center_lat + (y_rot / km_per_lat)
        lon = center_lon + (x_rot / km_per_lon)
        coords.append([round(lon, 6), round(lat, 6)])

    # Close the ring
    coords.append(coords[0])
    return coords


def build_synthetic_fixtures() -> Dict[str, Any]:
    """Build all synthetic test fixtures and write to data/synthetic/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Base incident timestamps
    t_obs = datetime(2026, 9, 7, 6, 0, 0, tzinfo=timezone.utc)
    t_age_hours = 12.0
    t_release = t_obs - timedelta(hours=t_age_hours)  # 2026-09-06 18:00:00 UTC

    # 2. Slick Detection GeoJSON
    polygon_coords = generate_slick_polygon(
        center_lat=18.962,
        center_lon=72.435,
        length_km=4.2,
        width_km=0.8,
        angle_deg=65.0,
    )
    slick_detection = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [polygon_coords],
        },
        "properties": {
            "case_id": "c0000000-0000-0000-0000-000000000001",
            "sensor": "Sentinel-1 SAR IW GRD",
            "detection_time": t_obs.isoformat(),
            "centroid": {"type": "Point", "coordinates": [72.435000, 18.962000]},
            "area_m2": 2420000.0,
            "confidence": 91.5,
            "lookalike_risk": 0.04,
            "damping_ratio_db": 8.6,
            "data_source": "synthetic",
        },
    }
    with open(DATA_DIR / "synthetic_slick_detection.geojson", "w", encoding="utf-8") as f:
        json.dump(slick_detection, f, indent=2)

    # 3. Slick Characterization
    slick_characterization = {
        "case_id": "c0000000-0000-0000-0000-000000000001",
        "perimeter_m": 14250.0,
        "principal_axis_deg": 65.0,
        "hydraulic_circularity": 0.15,
        "baoac_code": 3,
        "estimated_volume_m3": 185.0,
        "t_age_hours": t_age_hours,
        "age_confidence": 88.0,
        "t_age_interval_hours": [9.5, 14.8],
        "data_source": "synthetic",
    }
    with open(DATA_DIR / "synthetic_slick_characterization.json", "w", encoding="utf-8") as f:
        json.dump(slick_characterization, f, indent=2)

    # 4. Hydrodynamic Origin Estimate Ground Truth
    origin_estimate = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [72.290000, 18.865000],
        },
        "properties": {
            "case_id": "c0000000-0000-0000-0000-000000000001",
            "origin_centroid": [72.290000, 18.865000],
            "covariance_matrix": {
                "var_lon": 0.000185,
                "var_lat": 0.000142,
                "cov_lon_lat": 0.000095,
            },
            "time_window_start": (t_release - timedelta(hours=1, minutes=30)).isoformat(),
            "time_window_end": (t_release + timedelta(hours=1, minutes=30)).isoformat(),
            "confidence_pct": 89.2,
            "region_area_km2": 18.4,
            "data_source": "synthetic",
        },
    }
    with open(DATA_DIR / "synthetic_origin_estimate.geojson", "w", encoding="utf-8") as f:
        json.dump(origin_estimate, f, indent=2)

    # 5. Met-Ocean Surface Current & Wind Forcing
    metocean_forcing = {
        "model": "CMEMS_GLO12_AND_ERA5",
        "region_bbox": [72.10, 18.70, 72.60, 19.10],
        "time_span": [
            (t_obs - timedelta(hours=24)).isoformat(),
            (t_obs + timedelta(hours=72)).isoformat(),
        ],
        "surface_current": {
            "u_mps": 0.28,  # Zonal East velocity
            "v_mps": 0.12,  # Meridional North velocity
            "mean_speed_mps": 0.304,
            "mean_bearing_deg": 66.8,
        },
        "surface_wind_10m": {
            "u10_mps": 6.5,
            "v10_mps": 3.0,
            "speed_mps": 7.16,
            "direction_from_deg": 245.2,
        },
        "data_source": "synthetic",
    }
    with open(DATA_DIR / "synthetic_metocean_surface.json", "w", encoding="utf-8") as f:
        json.dump(metocean_forcing, f, indent=2)

    # 6. AIS Vessel Kinematic Tracks (5 Benchmark Vessels)
    # Time window: 24h leading to detection
    start_time = t_obs - timedelta(hours=20)
    ais_records: List[Dict[str, Any]] = []

    # Helper to generate interpolated leg
    def add_vessel_leg(
        mmsi: int,
        name: str,
        v_type: str,
        p_start: tuple[float, float],
        p_end: tuple[float, float],
        t_start: datetime,
        t_end: datetime,
        sog_val: float,
        cog_val: float,
        heading_val: float,
        gap: bool = False,
    ) -> None:
        duration_min = int((t_end - t_start).total_seconds() / 60)
        steps = max(2, duration_min // 15)  # 15-minute reports
        for s in range(steps + 1):
            cur_time = t_start + timedelta(minutes=s * 15)
            frac = s / steps
            cur_lon = p_start[0] + frac * (p_end[0] - p_start[0])
            cur_lat = p_start[1] + frac * (p_end[1] - p_start[1])

            # If gap simulated, skip middle reports
            if gap and (0.25 <= frac <= 0.75):
                continue

            ais_records.append(
                {
                    "mmsi": mmsi,
                    "vessel_name": name,
                    "vessel_type": v_type,
                    "timestamp": cur_time.isoformat(),
                    "lon": round(cur_lon, 6),
                    "lat": round(cur_lat, 6),
                    "sog": round(sog_val, 1),
                    "cog": round(cog_val, 1),
                    "heading": round(heading_val, 1),
                    "nav_status": 0,
                    "data_source": "synthetic",
                }
            )

    # Vessel A (Tanker, Candidate Suspect): Transits to origin, slows down to 5.8 kts at 18:00 UTC
    # Leg 1: Transit 14.5 kts
    add_vessel_leg(
        419000101, "PACIFIC PEARL", "Tanker",
        (72.18, 18.78), (72.27, 18.845),
        t_obs - timedelta(hours=16), t_release - timedelta(hours=1),
        14.5, 62.0, 62.0
    )
    # Leg 2: Dumping speed band 5.8 kts across origin centroid [72.290, 18.865]
    add_vessel_leg(
        419000101, "PACIFIC PEARL", "Tanker",
        (72.27, 18.845), (72.31, 18.885),
        t_release - timedelta(hours=1), t_release + timedelta(hours=1),
        5.8, 65.0, 64.0
    )
    # Leg 3: Speeds up to 14.0 kts moving east
    add_vessel_leg(
        419000101, "PACIFIC PEARL", "Tanker",
        (72.31, 18.885), (72.55, 19.04),
        t_release + timedelta(hours=1), t_obs,
        14.0, 63.0, 63.0
    )

    # Vessel B (Cargo, Innocent Transit): Transits north of origin at 17.2 kts
    add_vessel_leg(
        419000102, "MAERSK TAIPEI", "Cargo",
        (72.15, 18.98), (72.45, 19.05),
        t_obs - timedelta(hours=18), t_obs - timedelta(hours=6),
        17.2, 75.0, 75.0
    )

    # Vessel C (Fishing, Zig-Zag pattern): 25km south-east
    add_vessel_leg(
        419000103, "SAGAR JYOTI", "Fishing",
        (72.50, 18.65), (72.55, 18.70),
        t_obs - timedelta(hours=12), t_obs,
        3.5, 45.0, 45.0
    )

    # Vessel D (Dark Ship with 2.5h transponder gap at release time):
    add_vessel_leg(
        419000104, "SEA SHADOW", "Tanker",
        (72.20, 18.80), (72.35, 18.92),
        t_release - timedelta(hours=2), t_release + timedelta(hours=2),
        11.5, 55.0, 55.0,
        gap=True  # Disables reports around release window
    )

    # Vessel E (Offshore Supply Tender): Stationary near platform
    for h in range(10):
        t_cur = t_obs - timedelta(hours=h * 2)
        ais_records.append(
            {
                "mmsi": 419000105,
                "vessel_name": "OFFSHORE TENDER 3",
                "vessel_type": "Offshore",
                "timestamp": t_cur.isoformat(),
                "lon": 72.150000,
                "lat": 19.350000,
                "sog": 0.2,
                "cog": 180.0,
                "heading": 180.0,
                "nav_status": 5,
                "data_source": "synthetic",
            }
        )

    # Write AIS CSV
    ais_csv_path = DATA_DIR / "synthetic_ais_tracks.csv"
    with open(ais_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(ais_records[0].keys()))
        writer.writeheader()
        writer.writerows(ais_records)

    # Write AIS GeoJSON (FeatureCollection of Points)
    ais_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["lon"], r["lat"]],
                },
                "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")},
            }
            for r in ais_records
        ],
    }
    with open(DATA_DIR / "synthetic_ais_tracks.geojson", "w", encoding="utf-8") as f:
        json.dump(ais_geojson, f, indent=2)

    # 7. Manifest Catalog
    manifest = {
        "dataset_name": "AEGIS_SYNTHETIC_BOMBAY_HIGH_2026",
        "description": "Standard benchmark test dataset for end-to-end spill attribution pipeline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "synthetic",
        "scenario": {
            "region": "Arabian Sea / Bombay High Corridor",
            "center": [72.435, 18.962],
            "observation_time": t_obs.isoformat(),
            "spill_age_hours": t_age_hours,
            "estimated_release_time": t_release.isoformat(),
            "ground_truth_origin": [72.290, 18.865],
            "expected_top1_mmsi": 419000101,
            "expected_dark_ship_mmsi": 419000104,
        },
        "files": {
            "slick_detection": "synthetic_slick_detection.geojson",
            "slick_characterization": "synthetic_slick_characterization.json",
            "origin_estimate": "synthetic_origin_estimate.geojson",
            "metocean_forcing": "synthetic_metocean_surface.json",
            "ais_tracks_csv": "synthetic_ais_tracks.csv",
            "ais_tracks_geojson": "synthetic_ais_tracks.geojson",
        },
    }
    with open(DATA_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"✅ Generated synthetic dataset at {DATA_DIR} ({len(ais_records)} AIS reports)")
    return manifest


if __name__ == "__main__":
    build_synthetic_fixtures()
