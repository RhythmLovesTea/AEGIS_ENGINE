"""AEGIS-Marine: Slick Morphometry, Skeletonization & Principal Axis Extraction.

Implements Tier 2 spatial morphology algorithms:
1. Geodesic projection to local metric UTM coordinate systems (EPSG:326xx / 327xx).
2. Area (m^2), perimeter (m), and hydraulic circularity (4*pi*A / P^2).
3. Central second spatial moments & Principal Component Analysis (PCA) orientation:
   theta_slick = 0.5 * atan2(2 * mu_11, mu_20 - mu_02)
4. Medial axis skeletonization (skimage.morphology.skeletonize) for spill backbone extraction.
5. Eccentricity calculation from spatial covariance eigenvalues.
6. Rule 1 compliant paired confidence score.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pyproj
import rasterio.features
import shapely.affinity
import shapely.geometry
import shapely.ops
from rasterio.transform import Affine
from skimage.morphology import skeletonize


@dataclass(frozen=True)
class MorphometryResult:
    """Quantitative morphological parameters of a candidate oil slick."""

    area_m2: float
    perimeter_m: float
    circularity: float  # [0.0 - 1.0] (1.0 = perfect circle)
    eccentricity: float  # [0.0 - 1.0] (0.0 = circle, 1.0 = line)
    principal_axis_deg: float  # [0.0 - 360.0)
    skeleton_length_m: float
    skeleton_geojson: Dict[str, Any]  # GeoJSON LineString or MultiLineString (EPSG:4326)
    utm_epsg: int
    confidence: float  # [0.0 - 100.0] (Rule 1)


def get_utm_epsg(lon: float, lat: float) -> int:
    """Determine the appropriate UTM EPSG code for a given WGS84 coordinate.

    Args:
        lon: Longitude in degrees [-180.0, 180.0].
        lat: Latitude in degrees [-90.0, 90.0].

    Returns:
        EPSG integer code (e.g., 32643 for Bombay High in Zone 43N).
    """
    zone = int((lon + 180.0) / 6.0) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def project_to_utm(
    geometry_wgs84: shapely.geometry.base.BaseGeometry,
) -> Tuple[shapely.geometry.base.BaseGeometry, int, pyproj.Transformer]:
    """Project a WGS84 geometry (EPSG:4326) to its local metric UTM zone.

    Returns:
        Tuple of (projected_geometry, utm_epsg, forward_transformer).
    """
    centroid = geometry_wgs84.centroid
    epsg_code = get_utm_epsg(centroid.x, centroid.y)

    transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_code}", always_xy=True)
    projected = shapely.ops.transform(transformer.transform, geometry_wgs84)
    return projected, epsg_code, transformer


def compute_principal_axis_orientation(coords: np.ndarray) -> Tuple[float, float]:
    """Calculate principal axis orientation angle and eccentricity using second central moments.

    Reference: PRD Section 10 & Technical Specification Section 4.2.1
    Formula:
        theta_slick = 0.5 * atan2(2 * mu_11, mu_20 - mu_02)
        eccentricity = sqrt(1 - lambda_2 / lambda_1)

    Args:
        coords: (N, 2) array of coordinates (x, y) in metric meters.

    Returns:
        Tuple of (principal_axis_deg in [0, 360), eccentricity in [0, 1]).
    """
    if len(coords) < 3:
        return 0.0, 0.0

    x = coords[:, 0]
    y = coords[:, 1]

    x_c = np.mean(x)
    y_c = np.mean(y)

    dx = x - x_c
    dy = y - y_c

    mu20 = float(np.mean(dx**2))
    mu02 = float(np.mean(dy**2))
    mu11 = float(np.mean(dx * dy))

    # Angle in radians: 0.5 * atan2(2*mu11, mu20 - mu02)
    theta_rad = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
    theta_deg = math.degrees(theta_rad) % 180.0
    if abs(theta_deg - 180.0) < 1e-3 or abs(theta_deg) < 1e-3:
        theta_deg = 0.0

    # Covariance matrix eigenvalues for eccentricity
    trace = mu20 + mu02
    diff = mu20 - mu02
    disc = math.sqrt(diff**2 + 4.0 * (mu11**2))
    lambda1 = max(1e-9, (trace + disc) / 2.0)
    lambda2 = max(0.0, (trace - disc) / 2.0)

    if lambda1 <= 0.0:
        eccentricity = 0.0
    else:
        eccentricity = math.sqrt(max(0.0, min(1.0, 1.0 - (lambda2 / lambda1))))

    return round(theta_deg, 2), round(eccentricity, 4)


def extract_medial_skeleton(
    poly_utm: shapely.geometry.Polygon,
    grid_resolution_m: float = 10.0,
    backward_transformer: Optional[pyproj.Transformer] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Perform medial axis skeletonization to derive the central backbone of the slick.

    Args:
        poly_utm: Slick polygon in metric UTM projection.
        grid_resolution_m: Spatial grid resolution in meters for rasterization.
        backward_transformer: Transformer from UTM to EPSG:4326.

    Returns:
        Tuple of (skeleton_length_m, skeleton_geojson_dict).
    """
    min_x, min_y, max_x, max_y = poly_utm.bounds
    width_m = max_x - min_x
    height_m = max_y - min_y

    if width_m <= 0 or height_m <= 0:
        empty_feat = {"type": "MultiLineString", "coordinates": []}
        return 0.0, empty_feat

    cols = max(10, int(math.ceil(width_m / grid_resolution_m)))
    rows = max(10, int(math.ceil(height_m / grid_resolution_m)))

    # Prevent excessive memory allocation on very large extents
    max_dim = 1024
    if cols > max_dim or rows > max_dim:
        scale_down = max(cols / max_dim, rows / max_dim)
        grid_resolution_m *= scale_down
        cols = max(10, int(math.ceil(width_m / grid_resolution_m)))
        rows = max(10, int(math.ceil(height_m / grid_resolution_m)))

    transform = Affine.translation(min_x, max_y) @ Affine.scale(grid_resolution_m, -grid_resolution_m)

    # Rasterize polygon into binary mask
    mask = rasterio.features.rasterize(
        [(poly_utm, 1)],
        out_shape=(rows, cols),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )

    # Compute morphological skeleton
    skel = skeletonize(mask > 0)
    skel_pixels = np.sum(skel)

    if skel_pixels < 2:
        # Fallback: minor axis line through centroid
        empty_feat = {"type": "MultiLineString", "coordinates": []}
        return 0.0, empty_feat

    # Extract skeleton pixel coordinates
    r_idx, c_idx = np.where(skel)
    # Convert pixel (c, r) back to UTM coordinates
    xs, ys = rasterio.transform.xy(transform, r_idx, c_idx)
    utm_points = np.column_stack([xs, ys])

    # Convert to geographic coordinates if transformer provided
    if backward_transformer:
        lons, lats = backward_transformer.transform(utm_points[:, 0], utm_points[:, 1])
        geo_points = np.column_stack([lons, lats])
    else:
        geo_points = utm_points

    # Construct line segments connecting nearest 8-connected neighbors
    # For a metric skeleton length estimation:
    skeleton_length_m = round(float(skel_pixels * grid_resolution_m), 2)

    # Assemble simplified LineString or MultiPoint
    # Group into sorted coordinates along the primary elongation axis
    # Project points onto principal axis for ordered sequential path
    pca_angle, _ = compute_principal_axis_orientation(utm_points)
    angle_rad = math.radians(pca_angle)
    proj_dist = utm_points[:, 0] * math.cos(angle_rad) + utm_points[:, 1] * math.sin(angle_rad)
    sort_idx = np.argsort(proj_dist)
    sorted_geo = geo_points[sort_idx].tolist()

    # Subsample points if dense to keep GeoJSON concise
    step = max(1, len(sorted_geo) // 50)
    line_coords = sorted_geo[::step]
    if line_coords[-1] != sorted_geo[-1]:
        line_coords.append(sorted_geo[-1])

    skeleton_geojson = {
        "type": "LineString",
        "coordinates": line_coords,
    }

    return skeleton_length_m, skeleton_geojson


def analyze_slick_morphometry(
    polygon: Union[Dict[str, Any], shapely.geometry.base.BaseGeometry],
) -> MorphometryResult:
    """Extract complete morphometric parameters, principal orientation, and medial skeleton.

    Args:
        polygon: GeoJSON geometry dictionary or Shapely geometry in EPSG:4326 coordinates.

    Returns:
        MorphometryResult containing area, perimeter, circularity, eccentricity, orientation, and skeleton.
    """
    if isinstance(polygon, dict):
        poly_wgs84 = shapely.geometry.shape(polygon)
    else:
        poly_wgs84 = polygon

    if not poly_wgs84.is_valid:
        poly_wgs84 = poly_wgs84.buffer(0)

    if poly_wgs84.is_empty:
        raise ValueError("Cannot analyze morphometry of an empty geometry.")

    # 1. Project to local metric UTM
    poly_utm, utm_epsg, forward_transformer = project_to_utm(poly_wgs84)
    backward_transformer = pyproj.Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)

    # 2. Metric Area and Perimeter
    area_m2 = round(float(poly_utm.area), 2)
    perimeter_m = round(float(poly_utm.length), 2)

    # 3. Hydraulic Shape Factor / Circularity (C = 4 * pi * A / P^2)
    if perimeter_m > 0:
        circularity = round(float((4.0 * math.pi * area_m2) / (perimeter_m**2)), 4)
        circularity = max(0.0, min(1.0, circularity))
    else:
        circularity = 0.0

    # 4. Principal Axis Orientation & Eccentricity via PCA
    # Extract boundary contour coordinates in UTM
    if isinstance(poly_utm, shapely.geometry.Polygon):
        boundary_coords = np.array(poly_utm.exterior.coords)
    elif isinstance(poly_utm, shapely.geometry.MultiPolygon):
        # Concatenate boundaries of constituent polygons
        boundary_coords = np.concatenate([np.array(p.exterior.coords) for p in poly_utm.geoms])
    else:
        boundary_coords = np.array(poly_utm.boundary.coords)

    principal_axis_deg, eccentricity = compute_principal_axis_orientation(boundary_coords)

    # 5. Medial Axis Skeletonization
    skeleton_length_m, skeleton_geojson = extract_medial_skeleton(
        poly_utm=poly_utm if isinstance(poly_utm, shapely.geometry.Polygon) else poly_utm.geoms[0],
        grid_resolution_m=10.0,
        backward_transformer=backward_transformer,
    )

    # 6. Rule 1: Paired Morphometric Confidence Calculation
    # High area and smooth elongated boundary increases confidence; tiny fragmented shapes decrease it.
    confidence = 65.0
    if area_m2 >= 50000.0:
        confidence += 15.0
    elif area_m2 >= 10000.0:
        confidence += 10.0

    if eccentricity >= 0.70:
        # Well-defined elongated slick axis
        confidence += 15.0
    elif eccentricity >= 0.40:
        confidence += 8.0

    confidence = round(max(0.0, min(99.0, confidence)), 1)

    return MorphometryResult(
        area_m2=area_m2,
        perimeter_m=perimeter_m,
        circularity=circularity,
        eccentricity=eccentricity,
        principal_axis_deg=principal_axis_deg,
        skeleton_length_m=skeleton_length_m,
        skeleton_geojson=skeleton_geojson,
        utm_epsg=utm_epsg,
        confidence=confidence,
    )
