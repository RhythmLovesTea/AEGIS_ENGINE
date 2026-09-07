"""AEGIS-Marine: Copernicus CDSE & Local SAR/EO Satellite Ingestion Adapter.

Implements Tier 1 Earth observation ingestion and preprocessing:
1. Copernicus Data Space Ecosystem (CDSE) OData catalog query.
2. Radiometric calibration from raw Digital Numbers (DN) to backscatter sigma0 (dB).
3. 5x5 Lee adaptive speckle noise filtering.
4. Swath tiling into 512x512 patches with 20% overlap.
5. Automatic fallback to synthetic fixtures when CDSE credentials or network are offline.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np

logger = logging.getLogger("aegis.copernicus")

# Default fallback directories
ROOT_DIR = Path(__file__).resolve().parents[3]
SYNTHETIC_DIR = ROOT_DIR / "data" / "synthetic"
SAR_DIR = ROOT_DIR / "data" / "sar"


@dataclass
class EOProductQuery:
    """Bounding box and temporal criteria for satellite scene queries."""

    bbox: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    start_time: datetime
    end_time: datetime
    satellite: Literal["Sentinel-1", "Sentinel-2", "auto"] = "auto"
    polarization: List[str] = field(default_factory=lambda: ["VV", "VH"])


@dataclass
class PreprocessedTile:
    """Preprocessed 512x512 tile ready for segmentation inference."""

    tile_id: str
    data: np.ndarray  # Shape (channels, height, width)
    bounds: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    row_offset: int
    col_offset: int
    data_source: Literal["live", "cached", "synthetic"] = "synthetic"
    sensor: str = "Sentinel-1 SAR IW GRD"


class CopernicusAdapter:
    """Ingests, calibrates, filters, and tiles spaceborne SAR/EO imagery."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.client_id = client_id or os.getenv("COPERNICUS_CDSE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("COPERNICUS_CDSE_CLIENT_SECRET")
        self.cache_dir = cache_dir or SAR_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def query_scenes(self, query: EOProductQuery) -> List[Dict[str, Any]]:
        """Query Copernicus CDSE OData API with automatic synthetic fallback."""
        if not self.client_id or not self.client_secret:
            logger.info("ℹ️ CDSE credentials not provided. Using cached/synthetic scene catalog.")
            return self._get_synthetic_catalog_entry(query)

        # Attempt query to CDSE
        try:
            import requests

            url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
            min_lon, min_lat, max_lon, max_lat = query.bbox
            polygon_wkt = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
            filter_str = (
                f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}') and "
                f"ContentDate/Start gt {query.start_time.isoformat()} and "
                f"ContentDate/Start lt {query.end_time.isoformat()}"
            )
            response = requests.get(
                url,
                params={"$filter": filter_str, "$top": 5},
                timeout=5.0,
            )
            if response.status_code == 200:
                results = response.json().get("value", [])
                if results:
                    return results
        except Exception as e:
            logger.warning(f"⚠️ CDSE OData query failed ({e}). Falling back to synthetic catalog.")

        return self._get_synthetic_catalog_entry(query)

    def _get_synthetic_catalog_entry(self, query: EOProductQuery) -> List[Dict[str, Any]]:
        """Returns standard synthetic benchmark scene catalog entry."""
        return [
            {
                "Id": "c0000000-0000-0000-0000-000000000001",
                "Name": "S1A_IW_GRDH_1SDV_20260907T060000_BOMBAY_HIGH",
                "ContentType": "application/octet-stream",
                "ContentDate": {
                    "Start": query.start_time.isoformat(),
                    "End": query.end_time.isoformat(),
                },
                "GeoFootprint": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [query.bbox[0], query.bbox[1]],
                            [query.bbox[2], query.bbox[1]],
                            [query.bbox[2], query.bbox[3]],
                            [query.bbox[0], query.bbox[3]],
                            [query.bbox[0], query.bbox[1]],
                        ]
                    ],
                },
                "data_source": "synthetic",
            }
        ]

    @staticmethod
    def calibrate_radiometric(
        dn_array: np.ndarray,
        calibration_constant: float = 300.0,
        epsilon: float = 1e-6,
    ) -> np.ndarray:
        """Calibrate raw SAR Digital Numbers (DN) to radar backscatter sigma0 in decibels (dB).

        Formula: sigma0_dB = 10 * log10( (DN^2) / (A_sigma^2) + epsilon )
        """
        dn_sq = np.square(dn_array.astype(np.float32))
        sigma0_linear = dn_sq / (calibration_constant**2) + epsilon
        sigma0_db = 10.0 * np.log10(sigma0_linear)
        # Bounded to standard marine backscatter range [-35 dB, 0 dB]
        return np.clip(sigma0_db, -35.0, 0.0)

    @staticmethod
    def apply_lee_filter(
        image: np.ndarray,
        window_size: int = 5,
        cu: float = 0.523,
    ) -> np.ndarray:
        """Apply 5x5 Lee adaptive speckle filter to SAR backscatter image.

        Computes local mean and local variance; weights between raw pixel and local mean.
        """
        from scipy.ndimage import uniform_filter

        # Uniform filter calculates local mean
        local_mean = uniform_filter(image, size=window_size)
        local_sqr_mean = uniform_filter(image**2, size=window_size)
        local_var = np.maximum(0.0, local_sqr_mean - local_mean**2)

        # Theoretical noise variance for multi-look SAR
        overall_noise_var = (cu * local_mean) ** 2
        weight = local_var / (local_var + overall_noise_var + 1e-8)
        weight = np.clip(weight, 0.0, 1.0)

        filtered = local_mean + weight * (image - local_mean)
        return filtered

    @staticmethod
    def tile_swath(
        image: np.ndarray,
        tile_size: int = 512,
        overlap: float = 0.20,
    ) -> List[Tuple[np.ndarray, int, int]]:
        """Split 2D or 3D raster into tile_size x tile_size patches with overlap.

        Returns list of (tile_data, row_offset, col_offset).
        """
        if image.ndim == 2:
            h, w = image.shape
            is_3d = False
        else:
            c, h, w = image.shape
            is_3d = True

        stride = int(tile_size * (1.0 - overlap))
        tiles = []

        for r in range(0, max(1, h - tile_size + 1), stride):
            for c_idx in range(0, max(1, w - tile_size + 1), stride):
                r_end = min(r + tile_size, h)
                c_end = min(c_idx + tile_size, w)

                if is_3d:
                    tile = image[:, r:r_end, c_idx:c_end]
                    if tile.shape[1] < tile_size or tile.shape[2] < tile_size:
                        # Pad with reflection if boundary tile
                        pad_r = tile_size - tile.shape[1]
                        pad_c = tile_size - tile.shape[2]
                        tile = np.pad(tile, ((0, 0), (0, pad_r), (0, pad_c)), mode="reflect")
                else:
                    tile = image[r:r_end, c_idx:c_end]
                    if tile.shape[0] < tile_size or tile.shape[1] < tile_size:
                        pad_r = tile_size - tile.shape[0]
                        pad_c = tile_size - tile.shape[1]
                        tile = np.pad(tile, ((0, pad_r), (0, pad_c)), mode="reflect")

                tiles.append((tile, r, c_idx))

        return tiles

    def load_and_preprocess(
        self,
        scene_ref: str,
        local_file: Optional[Path] = None,
        swath_shape: Tuple[int, int] = (1024, 1024),
    ) -> Tuple[List[PreprocessedTile], Dict[str, Any]]:
        """Load SAR scene, calibrate to sigma0, apply Lee filter, and tile into 512x512 patches."""
        data_source: Literal["live", "cached", "synthetic"] = "synthetic"

        if local_file and local_file.exists():
            try:
                import rasterio

                with rasterio.open(local_file) as src:
                    raw_data = src.read(1)  # Read primary VV polarization band
                    data_source = "cached"
            except Exception as e:
                logger.warning(f"Could not read {local_file} via rasterio ({e}). Using synthetic generator.")
                raw_data = self._generate_synthetic_raw_sar(swath_shape)
        else:
            raw_data = self._generate_synthetic_raw_sar(swath_shape)

        # 1. Radiometric calibration to sigma0 (dB)
        sigma0_db = self.calibrate_radiometric(raw_data)

        # 2. Lee speckle filtering (5x5)
        filtered_sar = self.apply_lee_filter(sigma0_db, window_size=5)

        # 3. Tile into 512x512 patches with 20% overlap
        raw_tiles = self.tile_swath(filtered_sar, tile_size=512, overlap=0.20)

        tiles: List[PreprocessedTile] = []
        for idx, (t_data, r_off, c_off) in enumerate(raw_tiles):
            # Ensure shape is (1, 512, 512) for PyTorch segmentation
            if t_data.ndim == 2:
                t_tensor = np.expand_dims(t_data, axis=0)
            else:
                t_tensor = t_data

            tile = PreprocessedTile(
                tile_id=f"{scene_ref}_tile_{idx:03d}",
                data=t_tensor,
                bounds=(72.10 + (c_off * 0.001), 18.70 + (r_off * 0.001), 72.10 + ((c_off + 512) * 0.001), 18.70 + ((r_off + 512) * 0.001)),
                row_offset=r_off,
                col_offset=c_off,
                data_source=data_source,
                sensor="Sentinel-1 SAR IW GRD",
            )
            tiles.append(tile)

        metadata = {
            "scene_ref": scene_ref,
            "sensor": "Sentinel-1 SAR IW GRD",
            "tiles_count": len(tiles),
            "data_source": data_source,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        return tiles, metadata

    @staticmethod
    def _generate_synthetic_raw_sar(shape: Tuple[int, int] = (1024, 1024)) -> np.ndarray:
        """Generate realistic synthetic SAR sea surface with low-backscatter oil slick depression."""
        np.random.seed(42)
        # Background sea surface: Rayleigh-distributed multiplicative speckle + mean backscatter
        mean_sea_dn = 240.0
        speckle = np.random.rayleigh(scale=1.0, size=shape)
        sea_surface = mean_sea_dn * speckle

        # Introduce oil slick: 8 dB backscatter damping depression in center
        h, w = shape
        cy, cx = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        # Elongated ellipse rotated
        cos_65 = math.cos(math.radians(65))
        sin_65 = math.sin(math.radians(65))
        x_rot = (x - cx) * cos_65 - (y - cy) * sin_65
        y_rot = (x - cx) * sin_65 + (y - cy) * cos_65
        mask = ((x_rot / 250) ** 2 + (y_rot / 60) ** 2) <= 1.0

        # Damping factor: 8.5 dB depression corresponds to ~0.37 amplitude factor
        damping_factor = 0.37
        sea_surface[mask] *= damping_factor

        return sea_surface.astype(np.float32)
