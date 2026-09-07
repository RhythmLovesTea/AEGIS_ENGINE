# Tier 2 Service — Slick Morphometry, Thickness & Spreading Aging

**Responsibility:** Extract morphological properties (perimeter, principal axis $\theta_{slick}$ via PCA, skeletonization), invert Fay's mechanical spreading equations to estimate spill elapsed age $t_{age}$, and compute Bonn Agreement BAOAC thickness volume.

- **Input Contract (`SlickDetection`):** Geometry polygon, SAR backscatter contrast, optical reflectance.
- **Output Contract (`SlickCharacterization`):** `perimeter_m`, `principal_axis_deg`, `baoac_code`, `estimated_volume_m3`, `t_age_hours`, `age_confidence`.
