"""Unit and integration tests for AIS Data Ingestion Adapter (TASK-023)."""

import csv
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from backend.app.models.entities import AISTrack
from backend.services.data_adapters.ais_adapter import (
    AISAdapter,
    AISPositionReport,
    AISQuery,
    AISStaticVoyageData,
    AISTrackRecord,
    bulk_load_ais_to_timescaledb,
    compute_ais_time_window,
    compute_origin_search_bbox,
    parse_nmea_aivdm_sentence,
    parse_structured_ais_record,
)


class TestAISAdapter(unittest.TestCase):
    """Comprehensive test suite for AIS data ingestion adapter."""

    def setUp(self) -> None:
        """Set up benchmark scenario timestamps and coordinates."""
        self.t_obs = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)
        self.t_age_hours = 12.0
        self.t_release = self.t_obs - timedelta(hours=self.t_age_hours)
        self.origin_centroid = (72.29, 18.865)
        self.covariance_matrix = {
            "var_lon": 0.000185,
            "var_lat": 0.000142,
            "cov_lon_lat": 0.000095,
        }

    def test_nmea_aivdm_position_report_decoding(self) -> None:
        """Verify decoding of standard NMEA !AIVDM Class A position report (Type 1)."""
        # Standard ITU-R AIVDM Type 1 message
        sentence = "!AIVDM,1,1,,B,15N400002?8?v80E2>h70?v00000,0*13"
        ref_time = datetime(2026, 9, 7, 12, 30, 0, tzinfo=UTC)
        report = parse_nmea_aivdm_sentence(sentence, reference_time=ref_time)

        self.assertIsInstance(report, AISPositionReport)
        self.assertGreater(report.mmsi, 0)
        self.assertEqual(report.timestamp, ref_time)
        self.assertGreaterEqual(report.lon, -180.0)
        self.assertLessEqual(report.lon, 180.0)
        self.assertGreaterEqual(report.lat, -90.0)
        self.assertLessEqual(report.lat, 90.0)
        self.assertEqual(report.data_source, "live")

    def test_nmea_aivdm_static_voyage_decoding(self) -> None:
        """Verify decoding of standard NMEA !AIVDM static voyage data (Type 5)."""
        sentence = (
            "!AIVDM,1,1,,A,55?439P00001UH8Agg0E<T@E=Dp0000000000000000000000000000000000000,0*26"
        )
        report = parse_nmea_aivdm_sentence(sentence)

        self.assertIsInstance(report, AISStaticVoyageData)
        self.assertGreater(report.mmsi, 0)
        self.assertIsNotNone(report.vessel_name)
        self.assertIn(
            report.vessel_type,
            ["Tanker", "Cargo", "Fishing", "Passenger", "Tug", "Offshore", "Other", "Unknown"],
        )
        self.assertEqual(report.data_source, "live")

    def test_structured_csv_record_parsing(self) -> None:
        """Verify parsing and UTC normalization of tabular MarineCadastre/AISHub rows."""
        sample_row = {
            "mmsi": "419000101",
            "vessel_name": "PACIFIC PEARL",
            "vessel_type": "Tanker",
            "timestamp": "2026-09-06T18:00:00+00:00",
            "lon": "72.290000",
            "lat": "18.865000",
            "sog": "5.8",
            "cog": "65.0",
            "heading": "64.0",
            "nav_status": "0",
            "data_source": "synthetic",
        }

        rec = parse_structured_ais_record(sample_row)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.mmsi, 419000101)
        self.assertEqual(rec.vessel_name, "PACIFIC PEARL")
        self.assertEqual(rec.vessel_type, "Tanker")
        self.assertAlmostEqual(rec.lon, 72.290000)
        self.assertAlmostEqual(rec.lat, 18.865000)
        self.assertAlmostEqual(rec.sog, 5.8)
        self.assertAlmostEqual(rec.cog, 65.0)
        self.assertAlmostEqual(rec.heading, 64.0)
        self.assertEqual(rec.nav_status, 0)
        self.assertEqual(rec.data_source, "synthetic")

    def test_spatial_temporal_bounding_calculation(self) -> None:
        """Verify spatial bounding box (mu_p +/- 3*Sigma_p) and temporal window calculations."""
        bbox = compute_origin_search_bbox(
            origin_centroid=self.origin_centroid,
            covariance_matrix=self.covariance_matrix,
            search_buffer_deg=0.1,
        )
        min_lon, min_lat, max_lon, max_lat = bbox

        # Verify origin centroid is strictly enclosed with safety margins
        self.assertLess(min_lon, self.origin_centroid[0])
        self.assertGreater(max_lon, self.origin_centroid[0])
        self.assertLess(min_lat, self.origin_centroid[1])
        self.assertGreater(max_lat, self.origin_centroid[1])

        # Verify temporal window: [t_obs - t_age - 3h, t_obs + 1h]
        time_start, time_end = compute_ais_time_window(
            t_obs=self.t_obs,
            t_age_hours=self.t_age_hours,
        )
        expected_start = self.t_obs - timedelta(hours=15.0)
        expected_end = self.t_obs + timedelta(hours=1.0)
        self.assertEqual(time_start, expected_start)
        self.assertEqual(time_end, expected_end)

    def test_ais_adapter_synthetic_fallback_and_filtering(self) -> None:
        """Verify resilient fallback to synthetic fixtures and spatiotemporal filtering."""
        adapter = AISAdapter()

        # Build query spanning origin area and 24h window
        bbox = compute_origin_search_bbox(
            origin_centroid=self.origin_centroid,
            covariance_matrix=self.covariance_matrix,
            search_buffer_deg=0.2,
        )
        time_start, time_end = compute_ais_time_window(
            t_obs=self.t_obs,
            t_age_hours=self.t_age_hours,
        )

        query = AISQuery(
            bbox=bbox,
            time_start=time_start,
            time_end=time_end,
            origin_centroid=self.origin_centroid,
            search_buffer_deg=0.2,
        )

        result = adapter.fetch_ais_tracks(query=query, force_synthetic=True)

        # 1. Provenance and Confidence (Rule 1 & Rule 4)
        self.assertEqual(result.data_source, "synthetic")
        self.assertGreaterEqual(result.confidence_pct, 0.0)
        self.assertLessEqual(result.confidence_pct, 100.0)

        # 2. Filtering Verification
        self.assertGreater(len(result.records), 0)
        for rec in result.records:
            self.assertGreaterEqual(rec.lon, bbox[0])
            self.assertGreaterEqual(rec.lat, bbox[1])
            self.assertLessEqual(rec.lon, bbox[2])
            self.assertLessEqual(rec.lat, bbox[3])
            self.assertGreaterEqual(rec.timestamp, time_start)
            self.assertLessEqual(rec.timestamp, time_end)

        # 3. Verify primary suspect vessel MMSI 419000101 (PACIFIC PEARL) is present
        self.assertIn(419000101, result.vessel_mmsis)
        vessel_a_records = [r for r in result.records if r.mmsi == 419000101]
        self.assertGreater(len(vessel_a_records), 0)

        # Verify static metadata was populated
        self.assertIn(419000101, result.static_data)
        self.assertEqual(result.static_data[419000101].vessel_name, "PACIFIC PEARL")
        self.assertEqual(result.static_data[419000101].vessel_type, "Tanker")

    def test_timescaledb_bulk_persistence_and_deduplication(self) -> None:
        """Verify bulk loading into TimescaleDB with deduplication on (mmsi, timestamp)."""
        mock_db = MagicMock(spec=Session)
        stored_entities = []

        def mock_add_all(objs):
            stored_entities.extend(objs)

        mock_db.add_all.side_effect = mock_add_all

        # Create two identical timestamp records and one distinct record
        t_now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)
        test_records = [
            AISTrackRecord(
                mmsi=419000101,
                timestamp=t_now,
                lon=72.29,
                lat=18.865,
                sog=14.0,
                cog=65.0,
                heading=65.0,
                nav_status=0,
                vessel_name="PACIFIC PEARL",
                vessel_type="Tanker",
                data_source="synthetic",
            ),
            # Duplicate key: should be skipped
            AISTrackRecord(
                mmsi=419000101,
                timestamp=t_now,
                lon=72.29,
                lat=18.865,
                sog=14.0,
                cog=65.0,
                heading=65.0,
                nav_status=0,
                vessel_name="PACIFIC PEARL",
                vessel_type="Tanker",
                data_source="synthetic",
            ),
            # Distinct timestamp
            AISTrackRecord(
                mmsi=419000101,
                timestamp=t_now + timedelta(minutes=15),
                lon=72.31,
                lat=18.88,
                sog=14.0,
                cog=65.0,
                heading=65.0,
                nav_status=0,
                vessel_name="PACIFIC PEARL",
                vessel_type="Tanker",
                data_source="synthetic",
            ),
        ]

        count = bulk_load_ais_to_timescaledb(test_records, mock_db)
        self.assertEqual(count, 2)
        self.assertEqual(len(stored_entities), 2)
        for entity in stored_entities:
            self.assertIsInstance(entity, AISTrack)
            self.assertEqual(entity.mmsi, 419000101)

    def test_local_cache_inspection(self) -> None:
        """Verify adapter detects and prefers cached AIS data when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_cache = Path(tmpdir)
            sample_cache_csv = temp_cache / "cached_ais_20260907.csv"

            # Write single cached record
            t_cache = datetime(2026, 9, 7, 0, 0, 0, tzinfo=UTC)
            with open(sample_cache_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "mmsi",
                        "vessel_name",
                        "vessel_type",
                        "timestamp",
                        "lon",
                        "lat",
                        "sog",
                        "cog",
                        "heading",
                        "nav_status",
                        "data_source",
                    ]
                )
                writer.writerow(
                    [
                        "419999999",
                        "COASTAL PATROL",
                        "Other",
                        t_cache.isoformat(),
                        "72.25",
                        "18.85",
                        "12.0",
                        "90.0",
                        "90.0",
                        "0",
                        "cached",
                    ]
                )

            adapter = AISAdapter(cache_dir=temp_cache)
            query = AISQuery(
                bbox=(72.0, 18.0, 73.0, 19.5),
                time_start=t_cache - timedelta(hours=1),
                time_end=t_cache + timedelta(hours=1),
            )

            result = adapter.fetch_ais_tracks(query=query)
            self.assertEqual(result.data_source, "cached")
            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].mmsi, 419999999)
            self.assertEqual(result.records[0].vessel_name, "COASTAL PATROL")


if __name__ == "__main__":
    unittest.main()
