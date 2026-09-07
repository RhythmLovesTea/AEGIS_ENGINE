"""Unit tests verifying TASK-008 Synthetic Data Generator and Fixtures."""

import csv
import json
import unittest
from pathlib import Path

from backend.services.data_adapters.synthetic_generator import (
    DATA_DIR,
    build_synthetic_fixtures,
    generate_slick_polygon,
)


class TestSyntheticDataGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = build_synthetic_fixtures()

    def test_manifest_structure(self) -> None:
        """Verify manifest contains scenario metadata and file pointers."""
        self.assertEqual(self.manifest["data_source"], "synthetic")
        self.assertIn("scenario", self.manifest)
        self.assertEqual(self.manifest["scenario"]["expected_top1_mmsi"], 419000101)
        self.assertEqual(self.manifest["scenario"]["expected_dark_ship_mmsi"], 419000104)

        for key, filename in self.manifest["files"].items():
            file_path = DATA_DIR / filename
            self.assertTrue(file_path.exists(), f"Fixture file '{filename}' for '{key}' missing")

    def test_slick_detection_geojson_compliance(self) -> None:
        """Verify slick detection GeoJSON carries confidence and data_source=synthetic."""
        detection_file = DATA_DIR / "synthetic_slick_detection.geojson"
        data = json.loads(detection_file.read_text(encoding="utf-8"))

        self.assertEqual(data["type"], "Feature")
        self.assertEqual(data["geometry"]["type"], "Polygon")
        props = data["properties"]
        self.assertEqual(props["data_source"], "synthetic")
        self.assertIn("confidence", props)  # Rule 1
        self.assertGreaterEqual(props["confidence"], 0.0)
        self.assertLessEqual(props["confidence"], 100.0)

    def test_slick_characterization_fields(self) -> None:
        """Verify characterization contains spreading age and age confidence."""
        char_file = DATA_DIR / "synthetic_slick_characterization.json"
        data = json.loads(char_file.read_text(encoding="utf-8"))

        self.assertEqual(data["data_source"], "synthetic")
        self.assertEqual(data["t_age_hours"], 12.0)
        self.assertIn("age_confidence", data)  # Rule 1
        self.assertEqual(data["principal_axis_deg"], 65.0)

    def test_origin_estimate_covariance(self) -> None:
        """Verify origin estimate carries covariance matrix and confidence."""
        origin_file = DATA_DIR / "synthetic_origin_estimate.geojson"
        data = json.loads(origin_file.read_text(encoding="utf-8"))

        props = data["properties"]
        self.assertEqual(props["data_source"], "synthetic")
        self.assertIn("covariance_matrix", props)
        self.assertIn("confidence_pct", props)  # Rule 1

    def test_ais_trajectories_5_vessels(self) -> None:
        """Verify AIS fixture contains all 5 benchmark vessels and characteristic behaviors."""
        csv_file = DATA_DIR / "synthetic_ais_tracks.csv"
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        mmsis = {int(r["mmsi"]) for r in rows}
        self.assertEqual(mmsis, {419000101, 419000102, 419000103, 419000104, 419000105})

        # Check Vessel A has reports in dumping band (4.0 - 8.0 kts)
        vessel_a_sogs = [float(r["sog"]) for r in rows if int(r["mmsi"]) == 419000101]
        dumping_reports = [s for s in vessel_a_sogs if 4.0 <= s <= 8.0]
        self.assertGreater(len(dumping_reports), 0, "Vessel A must exhibit bilge/ballast dumping speed")

        # Check all rows carry data_source: synthetic (rules.md Section 4)
        for r in rows:
            self.assertEqual(r["data_source"], "synthetic")

    def test_polygon_generator_closed_ring(self) -> None:
        """Verify generate_slick_polygon generates closed polygon rings."""
        poly = generate_slick_polygon()
        self.assertEqual(poly[0], poly[-1], "First and last polygon coordinate must match to form closed ring")
        self.assertGreaterEqual(len(poly), 30)


if __name__ == "__main__":
    unittest.main()
