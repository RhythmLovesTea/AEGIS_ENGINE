"""AEGIS-Marine: Bonn Agreement Oil Appearance Code (BAOAC) Thickness Profiler.

Implements Tier 2 thickness mapping and volumetric estimation:
1. Bonn Agreement Oil Appearance Code (BAOAC) classification (Codes 1 to 5):
   - Code 1 (Sheen): 0.04 - 0.30 um (Nominal 0.15 um)
   - Code 2 (Rainbow): 0.30 - 5.00 um (Nominal 2.5 um)
   - Code 3 (Metallic): 5.00 - 50.0 um (Nominal 25 um)
   - Code 4 (Discontinuous True Oil): 50.0 - 200.0 um (Nominal 100 um)
   - Code 5 (Continuous True Oil): > 200.0 um (Nominal 300 um)
2. Mapping from SAR backscatter damping ratio and optical reflectance contrast to BAOAC codes.
3. Integrated volumetric calculation: V_total = sum(A_i * d_i) in m^3.
4. Volumetric uncertainty bounds [V_min, V_max].
5. Rule 1 compliant paired confidence scoring.

References:
- Bonn Agreement Aerial Surveillance Handbook (BAOAC standard)
- Technical Specification Section 4.2.2 & 4.2.3: Thickness & Appearance Inversion
- AEGIS-Marine_Architecture.md Section 4.2: Tier 2 Service
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BAOACSpec:
    """Specification of a Bonn Agreement appearance class."""

    code: int
    name: str
    description: str
    min_thickness_um: float
    max_thickness_um: float
    nominal_thickness_um: float
    min_damping_db: float
    max_damping_db: float

    @property
    def nominal_thickness_m(self) -> float:
        """Nominal thickness converted to meters."""
        return self.nominal_thickness_um * 1e-6

    @property
    def min_thickness_m(self) -> float:
        """Minimum thickness converted to meters."""
        return self.min_thickness_um * 1e-6

    @property
    def max_thickness_m(self) -> float:
        """Maximum thickness converted to meters."""
        return self.max_thickness_um * 1e-6


# Standard BAOAC Reference Specifications
BAOAC_TABLE: Dict[int, BAOACSpec] = {
    1: BAOACSpec(
        code=1,
        name="Sheen",
        description="Silvery-grey surface sheen with faint reflectivity",
        min_thickness_um=0.04,
        max_thickness_um=0.30,
        nominal_thickness_um=0.15,
        min_damping_db=4.5,
        max_damping_db=6.5,
    ),
    2: BAOACSpec(
        code=2,
        name="Rainbow",
        description="Characteristic optical interference bands with distinct rainbow hues",
        min_thickness_um=0.30,
        max_thickness_um=5.00,
        nominal_thickness_um=2.50,
        min_damping_db=6.5,
        max_damping_db=8.5,
    ),
    3: BAOACSpec(
        code=3,
        name="Metallic",
        description="Dull metallic sheen reflecting true ocean color with grey-brown undertones",
        min_thickness_um=5.00,
        max_thickness_um=50.0,
        nominal_thickness_um=25.0,
        min_damping_db=8.5,
        max_damping_db=11.5,
    ),
    4: BAOACSpec(
        code=4,
        name="Discontinuous True Oil",
        description="Discontinuous dark patches of true petroleum color and emulsion",
        min_thickness_um=50.0,
        max_thickness_um=200.0,
        nominal_thickness_um=100.0,
        min_damping_db=11.5,
        max_damping_db=14.5,
    ),
    5: BAOACSpec(
        code=5,
        name="Continuous True Oil",
        description="Continuous heavy dark brown/black emulsion layer and mousse",
        min_thickness_um=200.0,
        max_thickness_um=500.0,
        nominal_thickness_um=300.0,
        min_damping_db=14.5,
        max_damping_db=30.0,
    ),
}


@dataclass(frozen=True)
class ThicknessSegment:
    """Individual polygon or sub-patch thickness assignment."""

    segment_id: str
    area_m2: float
    baoac_code: int
    name: str
    nominal_thickness_um: float
    estimated_volume_m3: float
    volume_min_m3: float
    volume_max_m3: float
    damping_ratio_db: Optional[float] = None


@dataclass(frozen=True)
class SlickThicknessProfile:
    """Integrated spatial thickness and volumetric output (Rule 1 compliant)."""

    total_area_m2: float
    estimated_volume_m3: float
    volume_min_m3: float
    volume_max_m3: float
    dominant_baoac_code: int  # 1 to 5 (primary code by volume severity)
    area_distribution: Dict[int, float]  # Code -> area_m2
    volume_distribution: Dict[int, float]  # Code -> volume_m3
    segments: List[ThicknessSegment]
    confidence: float  # [0.0 - 100.0] (Rule 1 paired confidence)


def classify_baoac_from_radar_damping(
    damping_ratio_db: float,
    optical_contrast: Optional[float] = None,
) -> int:
    """Map measured radar damping ratio (dB) and optical contrast to a BAOAC code.

    Args:
        damping_ratio_db: Measured clean-sea vs slick backscatter damping (dB).
        optical_contrast: Optional multispectral optical reflectance contrast.

    Returns:
        BAOAC code integer (1 to 5).
    """
    # Optical contrast override for thick emulsions if available
    if optical_contrast is not None:
        if optical_contrast >= 0.25:
            return 5
        elif optical_contrast >= 0.15:
            return 4

    # Standard radar backscatter damping discrimination
    if damping_ratio_db < 6.5:
        return 1
    elif damping_ratio_db < 8.5:
        return 2
    elif damping_ratio_db < 11.5:
        return 3
    elif damping_ratio_db < 14.5:
        return 4
    else:
        return 5


def compute_segment_volume(area_m2: float, baoac_code: int) -> Tuple[float, float, float]:
    """Calculate nominal, minimum, and maximum volume (m^3) for a given area and BAOAC code.

    Formula:
        V = Area * Thickness_meters
    """
    if area_m2 <= 0.0:
        return 0.0, 0.0, 0.0

    spec = BAOAC_TABLE.get(baoac_code, BAOAC_TABLE[3])
    vol_nominal = area_m2 * spec.nominal_thickness_m
    vol_min = area_m2 * spec.min_thickness_m
    vol_max = area_m2 * spec.max_thickness_m

    return round(vol_nominal, 4), round(vol_min, 4), round(vol_max, 4)


def profile_slick_thickness(
    area_m2: float,
    damping_ratio_db: float = 8.5,
    optical_contrast: Optional[float] = None,
    sub_segments: Optional[List[Dict[str, Any]]] = None,
) -> SlickThicknessProfile:
    """Profile spatial slick thickness and calculate integrated volume.

    Handles two operating modes:
    1. Explicit sub-segments: when multi-segment polygons are provided.
    2. Empirical multi-fraction distribution: standard 80/20 oil spill profile
       (80% sheen/rainbow, 15% metallic, 5% thick emulsion) centered around dominant class.

    Args:
        area_m2: Total slick surface area in square meters.
        damping_ratio_db: Representative radar damping ratio in dB.
        optical_contrast: Optional optical contrast metric.
        sub_segments: Optional list of dicts with {"segment_id", "area_m2", "damping_ratio_db"}.

    Returns:
        SlickThicknessProfile with total volume, bounds, distribution, and confidence.
    """
    if area_m2 <= 0.0:
        raise ValueError(f"Area must be positive, got {area_m2}")

    segments: List[ThicknessSegment] = []
    area_dist: Dict[int, float] = {code: 0.0 for code in range(1, 6)}
    volume_dist: Dict[int, float] = {code: 0.0 for code in range(1, 6)}

    has_multi_sensor = optical_contrast is not None

    if sub_segments and len(sub_segments) > 0:
        # 1. Multi-segment explicit profiling
        seg_idx = 1
        for seg in sub_segments:
            seg_area = float(seg.get("area_m2", 0.0))
            if seg_area <= 0.0:
                continue
            seg_dr = float(seg.get("damping_ratio_db", damping_ratio_db))
            code = int(seg.get("baoac_code", classify_baoac_from_radar_damping(seg_dr, optical_contrast)))
            code = max(1, min(5, code))

            spec = BAOAC_TABLE[code]
            v_nom, v_min, v_max = compute_segment_volume(seg_area, code)

            seg_id = str(seg.get("segment_id", f"seg-{seg_idx:03d}"))
            segments.append(
                ThicknessSegment(
                    segment_id=seg_id,
                    area_m2=round(seg_area, 2),
                    baoac_code=code,
                    name=spec.name,
                    nominal_thickness_um=spec.nominal_thickness_um,
                    estimated_volume_m3=v_nom,
                    volume_min_m3=v_min,
                    volume_max_m3=v_max,
                    damping_ratio_db=seg_dr,
                )
            )
            area_dist[code] += seg_area
            volume_dist[code] += v_nom
            seg_idx += 1
    else:
        # 2. Standard physical distribution based on primary damping ratio
        primary_code = classify_baoac_from_radar_damping(damping_ratio_db, optical_contrast)

        if primary_code == 1:
            fractions = {1: 0.90, 2: 0.10}
        elif primary_code == 2:
            fractions = {1: 0.50, 2: 0.40, 3: 0.10}
        elif primary_code == 3:
            fractions = {1: 0.60, 2: 0.25, 3: 0.15}
        elif primary_code == 4:
            fractions = {1: 0.65, 2: 0.20, 3: 0.10, 4: 0.05}
        else:  # primary_code == 5
            fractions = {1: 0.60, 2: 0.20, 3: 0.10, 4: 0.06, 5: 0.04}

        for code, frac in fractions.items():
            seg_area = area_m2 * frac
            spec = BAOAC_TABLE[code]
            v_nom, v_min, v_max = compute_segment_volume(seg_area, code)

            segments.append(
                ThicknessSegment(
                    segment_id=f"baoac-{code}-{spec.name.lower().replace(' ', '_')}",
                    area_m2=round(seg_area, 2),
                    baoac_code=code,
                    name=spec.name,
                    nominal_thickness_um=spec.nominal_thickness_um,
                    estimated_volume_m3=v_nom,
                    volume_min_m3=v_min,
                    volume_max_m3=v_max,
                    damping_ratio_db=damping_ratio_db,
                )
            )
            area_dist[code] += seg_area
            volume_dist[code] += v_nom

    total_volume_nom = sum(s.estimated_volume_m3 for s in segments)
    total_volume_min = sum(s.volume_min_m3 for s in segments)
    total_volume_max = sum(s.volume_max_m3 for s in segments)

    # Determine dominant code: highest volume code, or highest code if volume is tied
    dominant_code = max(volume_dist.keys(), key=lambda c: (volume_dist[c], c))

    # Calculate Rule 1 paired confidence
    # Multi-modal (SAR + EO optical) provides highest confidence; SAR-only is moderate-high
    base_confidence = 88.0 if has_multi_sensor else 78.0
    if area_m2 >= 50000.0:
        base_confidence += 6.0
    elif area_m2 < 10000.0:
        base_confidence -= 5.0

    confidence = round(max(10.0, min(98.0, base_confidence)), 1)

    return SlickThicknessProfile(
        total_area_m2=round(area_m2, 2),
        estimated_volume_m3=round(total_volume_nom, 3),
        volume_min_m3=round(total_volume_min, 3),
        volume_max_m3=round(total_volume_max, 3),
        dominant_baoac_code=dominant_code,
        area_distribution={c: round(a, 2) for c, a in area_dist.items()},
        volume_distribution={c: round(v, 4) for c, v in volume_dist.items()},
        segments=segments,
        confidence=confidence,
    )
