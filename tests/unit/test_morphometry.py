"""Unit tests for slick morphometry, skeletonization, and principal axis extraction (TASK-013)."""

import math
import unittest
from typing import Tuple

import numpy as np
import pyproj
import shapely.affinity
import shapely.geometry
import shapely.ops

from backend.services.tier2_morphometry.morphometry import (
    MorphometryResult,
    analyze_slick_morphometry,
    compute_principal_axis_orientation,
    get_utm_epsg,
    project_to_utm,
)


def create_test_ellipse_wgs84(
    center_lon: float,
    center_lat: float,
    semi_major_m: float,
    semi_minor_m: float,
    rotation_deg: float,
) -> shapely.geometry.Polygon:
    """Helper to construct a geodetically accurate metric ellipse projected into WGS84."""
    zone_epsg = get_utm_epsg(center_lon, center_lat)
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{zone_epsg}", always_xy=True)
    to_wgs84 = pyproj.Transformer.from_crs(f"EPSG:{zone_epsg}", "EPSG:4326", always_xy=True)

    utm_center = to_utm.transform(center_lon, center_lat)

    # Construct metric circle and scale/rotate in metric space
    circle = shapely.geometry.Point(utm_center).buffer(semi_minor_m)
    scale_factor = semi_major_m / semi_minor_m
    ellipse_metric = shapely.affinity.scale(circle, xfact=scale_factor, yfact=1.0)
    rotated_metric = shapely.affinity.rotate(ellipse_metric, rotation_deg, origin=utm_center)

    # Project back to WGS84
    return shapely.ops.transform(to_wgs84.transform, rotated_metric)


class TestMorphometry(unittest.TestCase):
    """Test suite for Tier 2 slick morphometry algorithms."""

    def test_utm_zone_determination(self) -> None:
        """Test UTM EPSG zone calculation across northern and southern hemispheres."""
        # Bombay High (72.0 E, 19.0 N) -> Zone 43N (EPSG:32643)
        self.assertEqual(get_utm_epsg(72.0, 19.0), 32643)
        # Rio de Janeiro (-43.2 W, -22.9 S) -> Zone 23S (EPSG:32723)
        self.assertEqual(get_utm_epsg(-43.2, -22.9), 32723)
        # London / North Sea (0.5 E, 51.5 N) -> Zone 31N (EPSG:32631)
        self.assertEqual(get_utm_epsg(0.5, 51.5), 32631)

    def test_principal_axis_ellipse_45_deg(self) -> None:
        """Verify theta_slick = 45 deg +- 0.5 deg on known geometric ellipse oriented at 45 deg."""
        ellipse_wgs84 = create_test_ellipse_wgs84(
            center_lon=72.0,
            center_lat=19.0,
            semi_major_m=1500.0,
            semi_minor_m=500.0,
            rotation_deg=45.0,
        )

        result: MorphometryResult = analyze_slick_morphometry(ellipse_wgs84)

        diff = abs(result.principal_axis_deg - 45.0)
        self.assertLessEqual(diff, 0.5, f"Expected 45 +- 0.5 deg, got {result.principal_axis_deg}")
        self.assertEqual(result.utm_epsg, 32643)

    def test_principal_axis_orthogonal_orientations(self) -> None:
        """Verify orientation angles for horizontal (0 deg) and vertical (90 deg) axes."""
        # Horizontal ellipse (0 deg) on central meridian of UTM Zone 43 (75.0 E)
        h_ellipse = create_test_ellipse_wgs84(75.0, 19.0, 2000.0, 400.0, rotation_deg=0.0)
        res_h = analyze_slick_morphometry(h_ellipse)
        self.assertAlmostEqual(res_h.principal_axis_deg, 0.0, delta=0.5)

        # Vertical ellipse (90 deg) on central meridian of UTM Zone 43 (75.0 E)
        v_ellipse = create_test_ellipse_wgs84(75.0, 19.0, 2000.0, 400.0, rotation_deg=90.0)
        res_v = analyze_slick_morphometry(v_ellipse)
        self.assertAlmostEqual(res_v.principal_axis_deg, 90.0, delta=0.5)

    def test_circularity_and_eccentricity(self) -> None:
        """Verify hydraulic circularity C = 4*pi*A / P^2 and eccentricity bounds."""
        # 1. Near-circular polygon
        circle_wgs84 = create_test_ellipse_wgs84(72.0, 19.0, 1000.0, 1000.0, rotation_deg=0.0)
        res_circle = analyze_slick_morphometry(circle_wgs84)
        # Circularity should be close to 1.0 (>= 0.90 for buffered polygon discretization)
        self.assertGreaterEqual(res_circle.circularity, 0.90)
        self.assertLessEqual(res_circle.circularity, 1.0)
        # Eccentricity should be near 0.0 (<= 0.20 for discrete polygon vertices)
        self.assertLessEqual(res_circle.eccentricity, 0.20)

        # 2. Elongated slick (aspect ratio 4:1)
        elong_wgs84 = create_test_ellipse_wgs84(72.0, 19.0, 2000.0, 500.0, rotation_deg=30.0)
        res_elong = analyze_slick_morphometry(elong_wgs84)
        self.assertLess(res_elong.circularity, 0.70)
        self.assertGreater(res_elong.eccentricity, 0.90)

    def test_medial_axis_skeletonization(self) -> None:
        """Verify medial skeleton extraction produces positive length and valid LineString."""
        elong_wgs84 = create_test_ellipse_wgs84(72.0, 19.0, 2500.0, 500.0, rotation_deg=60.0)
        result = analyze_slick_morphometry(elong_wgs84)

        self.assertGreater(result.skeleton_length_m, 1000.0)
        self.assertEqual(result.skeleton_geojson["type"], "LineString")
        coords = result.skeleton_geojson["coordinates"]
        self.assertGreaterEqual(len(coords), 2)

        # Ensure skeleton coordinates are near center
        lon_avg = float(np.mean([c[0] for c in coords]))
        lat_avg = float(np.mean([c[1] for c in coords]))
        self.assertAlmostEqual(lon_avg, 72.0, places=2)
        self.assertAlmostEqual(lat_avg, 19.0, places=2)

    def test_rule_1_confidence_compliance(self) -> None:
        """Enforce Rule 1: Paired confidence score must be present and bounded [0, 100]."""
        test_slick = create_test_ellipse_wgs84(72.0, 19.0, 1500.0, 400.0, rotation_deg=25.0)
        result = analyze_slick_morphometry(test_slick)

        self.assertTrue(hasattr(result, "confidence"))
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 100.0)
        self.assertGreater(result.confidence, 70.0)

    def test_geojson_dict_input_handling(self) -> None:
        """Verify analyze_slick_morphometry accepts raw GeoJSON geometry dictionary."""
        test_slick = create_test_ellipse_wgs84(72.0, 19.0, 1000.0, 300.0, rotation_deg=45.0)
        geojson_dict = shapely.geometry.mapping(test_slick)

        result_dict = analyze_slick_morphometry(geojson_dict)
        result_geom = analyze_slick_morphometry(test_slick)

        self.assertEqual(result_dict.area_m2, result_geom.area_m2)
        self.assertEqual(result_dict.principal_axis_deg, result_geom.principal_axis_deg)
        self.assertEqual(result_dict.utm_epsg, result_geom.utm_epsg)

    def test_empty_geometry_raises_value_error(self) -> None:
        """Verify empty geometry raises ValueError."""
        empty_poly = shapely.geometry.Polygon()
        with self.assertRaises(ValueError):
            analyze_slick_morphometry(empty_poly)


if __name__ == "__main__":
    unittest.main()
