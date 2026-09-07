# Tier 1 Service — Earth Observation Ingestion & Segmentation

**Responsibility:** Ingest spaceborne radar (Sentinel-1 SAR) and optical (Sentinel-2 MSI) imagery, perform polarimetric physics checks (Bragg resonance, Damping Ratio, Co-Polarization Difference), reject lookalikes, and run deep semantic segmentation (DeepLabv3+).

- **Input:** GeoTIFF or Copernicus Scene Reference, bounding coordinates, acquisition time $t_{obs}$.
- **Output Contract (`SlickDetection`):** `polygon` (GeoJSON EPSG:4326), `centroid`, `area_m2`, `confidence`, `lookalike_risk`, `detection_time`.
