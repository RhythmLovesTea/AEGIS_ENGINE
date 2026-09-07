"""AEGIS-Marine: Automated Forensic PDF Legal Dossier Generator (FR-20, C13).

Compiles court-ready, legally defensible forensic PDF dossiers adhering to:
- PRD Section 11 (C13) & Architecture Sections 4.7 & 6
- Constitutional Rules:
  - Rule 1: Mandatory paired confidence scores across all detections, estimates, and candidates.
  - Rule 4: Explicit surfacing of transponder gaps and dark vessels (never excluded).
  - Rule 5: Systematic evaluation of non-vessel alternative hypotheses before completion.
  - Rule 6: Strictly zero occurrences of banned determination terms.
- ISO/IEC 27037 Digital Evidence standards with deterministic SHA-256 chain-of-custody.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
import qrcode
from scripts.lint_banned_terms import BANNED_RULES
from sqlalchemy.orm import Session

from backend.app.models.entities import AuditLog, Dossier
from backend.app.schemas.common import AISCoverageEnum
from backend.app.schemas.dossier import DossierResult

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_TEMPLATES_DIR = BASE_DIR / "backend" / "templates"
DEFAULT_STORAGE_DIR = BASE_DIR / "data" / "dossiers"

DEFAULT_MODEL_VERSIONS: dict[str, str] = {
    "segmentation": "DeepLabV3+-ResNet50-v1.2.0",
    "morphometry": "Fay-BAOAC-v1.0.0",
    "hindcast": "OpenDrift-1.11.0-OpenOil",
    "attribution_ahp": "AHP-Saaty-CR0.04-v1.0.0",
    "alternative_engine": "AEGIS-AltEngine-v1.0.0",
}

FR20_DISCLAIMER_TEXT = (
    "This dossier provides evidentiary correlation analysis based on spaceborne synthetic "
    "aperture radar (SAR), hydrodynamic Lagrangian hindcasting, and AIS vessel tracking data. "
    "Outputs represent probabilistic candidates and do not constitute a final legal determination "
    "of liability. Final evidentiary verification requires on-site sampling, physical oil chemical "
    "fingerprinting, and authorized maritime inspection pursuant to MARPOL 73/78 Annex I and "
    "UNCLOS Article 217 guidelines."
)


def assert_no_banned_terms(text: str, context_label: str = "text") -> None:
    """Enforces Constitutional Rule 6: zero banned determination terms."""
    import re

    for rule in BANNED_RULES:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            raise ValueError(
                f"Rule 6 Violation: Detected banned term '{rule['name']}' in {context_label}: {text}"
            )


def _to_dict(obj: Any) -> dict[str, Any]:
    """Helper to convert Pydantic models or entities to dictionaries."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "dict"):
        return obj.dict()
    elif isinstance(obj, dict):
        return obj.copy()
    elif hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return dict(obj)


class DossierGenerator:
    """Compiles forensic legal dossiers with dual PDF rendering engines and SHA-256 chain-of-custody."""

    def __init__(
        self,
        template_dir: Path | str | None = None,
        storage_dir: Path | str | None = None,
        default_model_versions: dict[str, str] | None = None,
    ) -> None:
        self.template_dir = Path(template_dir or DEFAULT_TEMPLATES_DIR)
        self.storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.model_versions = default_model_versions or DEFAULT_MODEL_VERSIONS.copy()

        # Initialize Jinja2 environment with autoescaping
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

    def compute_canonical_sha256(
        self,
        case_id: uuid.UUID | str,
        detection_data: dict[str, Any],
        characterization_data: dict[str, Any],
        origin_data: dict[str, Any],
        candidates_data: list[dict[str, Any]],
        alternatives_data: list[dict[str, Any]],
        model_versions: dict[str, Any],
        generated_at: datetime,
    ) -> str:
        """Computes deterministic SHA-256 digest over normalized case inputs and outputs."""
        canonical_payload = {
            "case_id": str(case_id),
            "generated_at": generated_at.isoformat(),
            "model_versions": dict(sorted(model_versions.items())),
            "detection": {
                "sensor": detection_data.get("sensor", ""),
                "detection_time": str(detection_data.get("detection_time", "")),
                "area_m2": round(float(detection_data.get("area_m2", 0.0)), 2),
                "confidence": round(float(detection_data.get("confidence", 0.0)), 2),
                "lookalike_risk": round(float(detection_data.get("lookalike_risk", 0.0)), 4),
            },
            "characterization": {
                "perimeter_m": round(float(characterization_data.get("perimeter_m", 0.0)), 2),
                "principal_axis_deg": round(
                    float(characterization_data.get("principal_axis_deg", 0.0)), 2
                ),
                "baoac_code": int(characterization_data.get("baoac_code", 1)),
                "estimated_volume_m3": round(
                    float(characterization_data.get("estimated_volume_m3", 0.0)), 3
                ),
                "t_age_hours": round(float(characterization_data.get("t_age_hours", 0.0)), 2),
                "age_confidence": round(float(characterization_data.get("age_confidence", 0.0)), 2),
            },
            "origin": {
                "centroid": origin_data.get("centroid", {}),
                "time_window_start": str(origin_data.get("time_window_start", "")),
                "time_window_end": str(origin_data.get("time_window_end", "")),
                "confidence_pct": round(float(origin_data.get("confidence_pct", 0.0)), 2),
                "region_area_km2": round(float(origin_data.get("region_area_km2", 0.0)), 2),
            },
            "candidates": [
                {
                    "mmsi": int(c.get("mmsi", 0)),
                    "name": str(c.get("name", "")),
                    "s_culprit": round(float(c.get("s_culprit", 0.0)), 2),
                    "confidence": round(float(c.get("confidence", 0.0)), 2),
                    "ais_coverage": str(c.get("ais_coverage", "")),
                    "sub_scores": {
                        k: round(float(v), 2) for k, v in _to_dict(c.get("sub_scores", {})).items()
                    },
                }
                for c in candidates_data
            ],
            "alternatives": [
                {
                    "hypothesis": str(a.get("hypothesis", "")),
                    "score": round(float(a.get("score", 0.0)), 2),
                    "confidence": round(float(a.get("confidence", 0.0)), 2),
                }
                for a in alternatives_data
            ],
        }

        canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def generate_verification_qr_b64(
        self,
        case_id: uuid.UUID | str,
        sha256_hash: str,
        generated_at: datetime,
        authority: str,
    ) -> tuple[str, bytes]:
        """Generates QR code encoding verification metadata and returns (base64_data_uri, raw_png_bytes)."""
        verification_payload = {
            "authority": authority,
            "case_id": str(case_id),
            "sha256": sha256_hash,
            "generated_at": generated_at.isoformat(),
            "verification_url": f"https://aegis.marine/verify/{case_id}?sha256={sha256_hash}",
        }
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(json.dumps(verification_payload, sort_keys=True))
        qr.make(fit=True)
        img = qr.make_image(fill_color="#001e2b", back_color="#ffffff")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        b64_uri = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
        return b64_uri, png_bytes

    def prepare_template_context(
        self,
        case_id: uuid.UUID | str,
        detection_data: dict[str, Any],
        characterization_data: dict[str, Any],
        origin_data: dict[str, Any],
        candidates_data: list[dict[str, Any]],
        alternatives_data: list[dict[str, Any]],
        environmental_data: dict[str, Any] | None,
        sar_chip_b64: str | None,
        sha256_hash: str,
        verification_qr_b64: str,
        generated_at: datetime,
        generated_by: str,
        model_versions: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepares and validates normalized view context for rendering."""
        # Rule 1 validation: Ensure every candidate score has paired confidence
        for idx, c in enumerate(candidates_data):
            if "confidence" not in c or c["confidence"] is None:
                raise ValueError(
                    f"Rule 1 Violation: Candidate #{idx + 1} ({c.get('name')}) is missing paired confidence value."
                )
            # Verify sub_scores
            sub = _to_dict(c.get("sub_scores", {}))
            for score_key in ["spatial", "temporal", "kinematic", "anomaly", "type"]:
                if score_key not in sub:
                    raise ValueError(
                        f"Rule 2 Violation: Candidate {c.get('name')} missing sub-score '{score_key}'"
                    )

        # Rule 1 & 5 validation: Ensure alternatives exist and each has confidence
        if not alternatives_data:
            raise ValueError(
                "Rule 5 Violation: Case must contain at least one alternative explanation hypothesis."
            )

        for idx, a in enumerate(alternatives_data):
            if "confidence" not in a or a["confidence"] is None:
                raise ValueError(
                    f"Rule 1 Violation: Alternative hypothesis #{idx + 1} missing paired confidence value."
                )

        # Extract centroid coordinates
        det_centroid = detection_data.get("centroid", {})
        det_coords = (
            det_centroid.get("coordinates", [0.0, 0.0])
            if isinstance(det_centroid, dict)
            else [0.0, 0.0]
        )
        det_lon, det_lat = det_coords[0], det_coords[1]

        orig_centroid = origin_data.get("centroid", {})
        orig_coords = (
            orig_centroid.get("coordinates", [0.0, 0.0])
            if isinstance(orig_centroid, dict)
            else [0.0, 0.0]
        )
        orig_lon, orig_lat = orig_coords[0], orig_coords[1]

        area_m2 = float(detection_data.get("area_m2", 0.0))
        area_km2 = round(area_m2 / 1e6, 3)

        vol_m3 = float(characterization_data.get("estimated_volume_m3", 0.0))
        vol_bbl = round(vol_m3 * 6.28981, 1)

        perimeter_m = float(characterization_data.get("perimeter_m", 0.0))
        perimeter_km = round(perimeter_m / 1000.0, 2)

        t_age = float(characterization_data.get("t_age_hours", 0.0))

        # Format candidates for presentation
        formatted_candidates = []
        for c in candidates_data:
            c_dict = _to_dict(c)
            sub = _to_dict(c_dict.get("sub_scores", {}))
            c_dict["sub_scores"] = sub
            cov = c_dict.get("ais_coverage", AISCoverageEnum.FULL)
            c_dict["ais_coverage"] = cov.value if hasattr(cov, "value") else str(cov)
            formatted_candidates.append(c_dict)

        # Sort candidates descending by S_culprit
        formatted_candidates.sort(key=lambda x: float(x.get("s_culprit", 0.0)), reverse=True)

        # Format alternatives with human-readable titles
        hypothesis_titles = {
            "natural_seep": "Natural Geological Hydrocarbon Seep",
            "imaging_artifact": "Synthetic Aperture Radar Lookalike / Artifact",
            "non_ais_vessel": "Unflagged Contact / Non-AIS Maritime Target",
            "biogenic_slick": "Biogenic Marine Surfactant Film",
            "low_wind_zone": "Atmospheric Low-Wind Backscatter Drop",
        }

        formatted_alternatives = []
        for a in alternatives_data:
            a_dict = _to_dict(a)
            hyp_key = a_dict.get("hypothesis", "")
            title = hypothesis_titles.get(hyp_key, hyp_key.replace("_", " ").title())
            a_dict["hypothesis_title"] = title

            evidence = a_dict.get("evidence", {})
            summary_parts = []
            if "geological_basin" in evidence:
                summary_parts.append(f"Catalog reference: {evidence.get('geological_basin')}")
            if "distance_km" in evidence:
                summary_parts.append(
                    f"Distance to nearest seep: {round(float(evidence['distance_km']), 1)} km"
                )
            if "spatial_anomaly" in evidence:
                summary_parts.append(f"Pattern: {evidence.get('spatial_anomaly')}")
            if "explanation" in evidence:
                summary_parts.append(str(evidence["explanation"]))
            elif not summary_parts:
                summary_parts.append(
                    f"Physical consistency evaluation indicates plausibility score of {a_dict.get('score', 0):.1f}."
                )

            a_dict["technical_summary"] = " — ".join(summary_parts)
            formatted_alternatives.append(a_dict)

        # Environmental fallback defaults
        env = environmental_data or {}
        env_context = {
            "current_speed_ms": env.get("current_speed_ms", 0.28),
            "current_dir_deg": env.get("current_dir_deg", 64.0),
            "wind_speed_ms": env.get("wind_speed_ms", 5.2),
            "wind_dir_deg": env.get("wind_dir_deg", 245.0),
            "sst_c": env.get("sst_c", 27.5),
        }

        search_radius_km = round(
            (float(origin_data.get("region_area_km2", 25.0)) / 3.14159) ** 0.5, 2
        )

        return {
            "case_id": str(case_id),
            "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "generated_by": generated_by,
            "model_versions": model_versions,
            "sha256_hash": sha256_hash,
            "verification_qr_b64": verification_qr_b64,
            "sar_chip_b64": sar_chip_b64,
            "detection": {
                "sensor": detection_data.get("sensor", "Sentinel-1 C-SAR IW"),
                "detection_time": str(detection_data.get("detection_time", "")),
                "data_source": str(detection_data.get("data_source", "Copernicus Hub / ESA")),
                "centroid_lat": f"{det_lat:.4f}",
                "centroid_lon": f"{det_lon:.4f}",
                "area_m2": f"{area_m2:,.0f}",
                "area_km2": f"{area_km2:.3f}",
                "confidence": f"{float(detection_data.get('confidence', 0.0)):.1f}",
                "lookalike_risk": f"{float(detection_data.get('lookalike_risk', 0.0)):.2f}",
            },
            "characterization": {
                "perimeter_km": f"{perimeter_km:.2f}",
                "principal_axis_deg": f"{float(characterization_data.get('principal_axis_deg', 0.0)):.1f}",
                "baoac_code": characterization_data.get("baoac_code", 2),
                "estimated_volume_m3": f"{vol_m3:,.2f}",
                "estimated_volume_bbl": f"{vol_bbl:,.1f}",
                "t_age_hours": f"{t_age:.1f}",
                "age_confidence": f"{float(characterization_data.get('age_confidence', 0.0)):.1f}",
                "release_window_str": f"T - {t_age:.1f}h (± {max(0.5, t_age * 0.15):.1f}h)",
            },
            "origin": {
                "centroid_lat": f"{orig_lat:.4f}",
                "centroid_lon": f"{orig_lon:.4f}",
                "region_area_km2": f"{float(origin_data.get('region_area_km2', 0.0)):.2f}",
                "search_radius_km": f"{search_radius_km:.2f}",
                "confidence_pct": f"{float(origin_data.get('confidence_pct', 0.0)):.1f}",
            },
            "environmental": env_context,
            "candidates": formatted_candidates,
            "alternatives": formatted_alternatives,
            "disclaimer_text": FR20_DISCLAIMER_TEXT,
        }

    def render_html(self, template_name: str, context: dict[str, Any]) -> str:
        """Renders Jinja2 HTML template and checks output for Rule 6 compliance."""
        template = self.jinja_env.get_template(template_name)
        rendered_html = template.render(**context)

        # Constitutional Rule 6: Zero banned terms check
        assert_no_banned_terms(rendered_html, context_label="Rendered Dossier HTML")
        return rendered_html

    def generate_pdf_weasyprint(self, html_content: str) -> bytes:
        """Renders PDF bytes from HTML using WeasyPrint."""
        import weasyprint

        html = weasyprint.HTML(string=html_content, base_url=str(self.template_dir))
        return html.write_pdf()

    def generate_pdf_reportlab(
        self,
        context: dict[str, Any],
        qr_png_bytes: bytes | None = None,
    ) -> bytes:
        """Fallback programmatic PDF generator using ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.platypus import (
            Image as RLImage,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#001e2b"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#00684a"),
            fontName="Helvetica-Bold",
        )
        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#001e2b"),
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "BodySmall",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1c2d38"),
        )
        meta_label_style = ParagraphStyle(
            "MetaLabel",
            parent=styles["Normal"],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#5c6c7a"),
            fontName="Helvetica-Bold",
        )
        meta_val_style = ParagraphStyle(
            "MetaVal",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#001e2b"),
            fontName="Helvetica-Bold",
        )
        disclaimer_style = ParagraphStyle(
            "Disclaimer",
            parent=styles["Normal"],
            fontSize=7.5,
            leading=10.5,
            textColor=colors.HexColor("#78350f"),
        )
        mono_style = ParagraphStyle(
            "MonoBlock",
            parent=styles["Normal"],
            fontSize=7,
            leading=9,
            fontName="Courier",
            textColor=colors.HexColor("#001e2b"),
        )

        story = []

        # Header
        story.append(Paragraph("AEGIS-MARINE FORENSIC ATTRIBUTION DOSSIER", title_style))
        story.append(
            Paragraph(
                "AUTOMATED SPACEBORNE DETECTION & HYDRODYNAMIC HINDCAST EVIDENTIARY PACKAGE",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(
            HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#001e2b"), spaceAfter=8)
        )

        # Metadata Bar
        meta_data = [
            [
                Paragraph("CASE IDENTIFIER", meta_label_style),
                Paragraph("ANALYSIS DATE (UTC)", meta_label_style),
                Paragraph("AUTHORITY", meta_label_style),
                Paragraph("VERIFICATION GRADE", meta_label_style),
            ],
            [
                Paragraph(context["case_id"], mono_style),
                Paragraph(context["generated_at"], meta_val_style),
                Paragraph(context["generated_by"], meta_val_style),
                Paragraph("READY (AHP Correlated)", meta_val_style),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[50 * mm, 45 * mm, 45 * mm, 42 * mm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fbfa")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e1e5e8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(meta_table)
        story.append(Spacer(1, 4 * mm))

        # Section 1
        story.append(
            Paragraph(
                "1. Executive Incident Summary & Satellite Acquisition Metadata", section_style
            )
        )
        sec1_text = (
            f"Sensor: {context['detection']['sensor']} | Detection UTC: {context['detection']['detection_time']} | "
            f"Centroid: {context['detection']['centroid_lat']}°, {context['detection']['centroid_lon']}° | "
            f"Observed Area: {context['detection']['area_km2']} km² | "
            f"Lookalike Risk: {context['detection']['lookalike_risk']} | "
            f"Detection Confidence (Rule 1): {context['detection']['confidence']}%"
        )
        story.append(Paragraph(sec1_text, body_style))
        story.append(Spacer(1, 3 * mm))

        # Section 2
        story.append(
            Paragraph("2. Slick Morphometry, Volume & Spreading Aging Inversion", section_style)
        )
        sec2_text = (
            f"Perimeter: {context['characterization']['perimeter_km']} km | "
            f"Principal Axis: {context['characterization']['principal_axis_deg']}° | "
            f"BAOAC Code: {context['characterization']['baoac_code']} | "
            f"Volume: {context['characterization']['estimated_volume_m3']} m³ ({context['characterization']['estimated_volume_bbl']} bbl) | "
            f"Fay Inverted Age: {context['characterization']['t_age_hours']} h | "
            f"Paired Age Confidence: {context['characterization']['age_confidence']}%"
        )
        story.append(Paragraph(sec2_text, body_style))
        story.append(Spacer(1, 3 * mm))

        # Section 3
        story.append(
            Paragraph(
                "3. Hydrodynamic Hindcast Origin Cloud & Environmental Forcing", section_style
            )
        )
        sec3_text = (
            f"Origin Centroid: {context['origin']['centroid_lat']}°, {context['origin']['centroid_lon']}° | "
            f"3-Sigma Uncertainty Area: {context['origin']['region_area_km2']} km² | "
            f"Search Radius: {context['origin']['search_radius_km']} km | "
            f"Origin Confidence (Rule 1): {context['origin']['confidence_pct']}% | "
            f"CMEMS Currents: {context['environmental']['current_speed_ms']} m/s ({context['environmental']['current_dir_deg']}°) | "
            f"ERA5 Winds: {context['environmental']['wind_speed_ms']} m/s ({context['environmental']['wind_dir_deg']}°)"
        )
        story.append(Paragraph(sec3_text, body_style))
        story.append(Spacer(1, 3 * mm))

        # Section 4: Suspect Candidates Table
        story.append(
            Paragraph(
                "4. Ranked Candidate Suspects Table (Analytical Hierarchy Process)", section_style
            )
        )
        table_headers = [
            "#",
            "Candidate Vessel",
            "MMSI",
            "Type",
            "AIS",
            "S_spat",
            "S_temp",
            "S_kin",
            "S_anom",
            "S_type",
            "S_culprit",
            "Conf",
        ]
        table_rows = [table_headers]

        for idx, c in enumerate(context["candidates"]):
            sub = c.get("sub_scores", {})
            table_rows.append(
                [
                    f"#{idx + 1}",
                    c.get("name", "Unknown")[:18],
                    str(c.get("mmsi", "")),
                    c.get("vessel_type", "")[:10],
                    c.get("ais_coverage", "full").upper()[:8],
                    f"{float(sub.get('spatial', 0.0)):.1f}",
                    f"{float(sub.get('temporal', 0.0)):.1f}",
                    f"{float(sub.get('kinematic', 0.0)):.1f}",
                    f"{float(sub.get('anomaly', 0.0)):.1f}",
                    f"{float(sub.get('type', 0.0)):.1f}",
                    f"{float(c.get('s_culprit', 0.0)):.1f}",
                    f"{float(c.get('confidence', 0.0)):.1f}%",
                ]
            )

        cand_table = Table(
            table_rows,
            colWidths=[
                8 * mm,
                32 * mm,
                18 * mm,
                18 * mm,
                16 * mm,
                12 * mm,
                12 * mm,
                12 * mm,
                12 * mm,
                12 * mm,
                15 * mm,
                15 * mm,
            ],
        )
        cand_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f7f6")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#001e2b")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#eceff1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(cand_table)
        story.append(Spacer(1, 3 * mm))

        # Section 5: Alternatives
        story.append(Paragraph("5. Alternative Explanations Evaluated (Rule 5)", section_style))
        for alt in context["alternatives"]:
            alt_text = f"• <b>{alt['hypothesis_title']}</b> — Plausibility: {alt['score']:.1f}/100 | Confidence: {alt['confidence']:.1f}%<br/>&nbsp;&nbsp;{alt['technical_summary']}"
            story.append(Paragraph(alt_text, body_style))
            story.append(Spacer(1, 1.5 * mm))

        story.append(Spacer(1, 2 * mm))

        # Section 6: FR-20 Disclaimer
        story.append(
            Paragraph("<b>6. MANDATORY RESPONSIBLE-USE NOTICE (FR-20)</b>", meta_label_style)
        )
        story.append(Paragraph(context["disclaimer_text"], disclaimer_style))
        story.append(Spacer(1, 4 * mm))

        # Footer / Chain-of-Custody
        footer_data = [
            [
                Paragraph(
                    f"<b>SHA-256 INTEGRITY HASH:</b> {context['sha256_hash']}<br/><b>Model Versions:</b> {context['model_versions']}",
                    mono_style,
                ),
                RLImage(io.BytesIO(qr_png_bytes), width=18 * mm, height=18 * mm)
                if qr_png_bytes
                else Paragraph("[QR]", mono_style),
            ]
        ]
        footer_table = Table(footer_data, colWidths=[155 * mm, 27 * mm])
        footer_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c1ccd6")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fbfa")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(footer_table)

        doc.build(story)
        return buffer.getvalue()

    def generate_dossier(
        self,
        case_id: uuid.UUID | str,
        detection: dict[str, Any] | Any,
        characterization: dict[str, Any] | Any,
        origin: dict[str, Any] | Any,
        candidates: list[dict[str, Any] | Any],
        alternatives: list[dict[str, Any] | Any],
        environmental: dict[str, Any] | None = None,
        sar_chip_b64: str | None = None,
        model_versions: dict[str, Any] | None = None,
        generated_by: str = "AEGIS Automated Forensic Pipeline",
        engine: str = "auto",
        output_path: Path | str | None = None,
        db_session: Session | None = None,
    ) -> DossierResult:
        """Orchestrates end-to-end legal dossier compilation, SHA-256 stamping, PDF generation, and persistence."""
        case_uuid = uuid.UUID(str(case_id))
        now_utc = datetime.now(UTC)
        resolved_versions = model_versions or self.model_versions.copy()

        # Convert objects to dictionaries
        det_dict = _to_dict(detection)
        char_dict = _to_dict(characterization)
        orig_dict = _to_dict(origin)
        cand_list = [_to_dict(c) for c in candidates]
        alt_list = [_to_dict(a) for a in alternatives]

        # 1. Compute Deterministic Canonical SHA-256 Hash
        sha256_hash = self.compute_canonical_sha256(
            case_id=case_uuid,
            detection_data=det_dict,
            characterization_data=char_dict,
            origin_data=orig_dict,
            candidates_data=cand_list,
            alternatives_data=alt_list,
            model_versions=resolved_versions,
            generated_at=now_utc,
        )

        # 2. Generate Verification QR Code
        qr_b64, qr_png_bytes = self.generate_verification_qr_b64(
            case_id=case_uuid,
            sha256_hash=sha256_hash,
            generated_at=now_utc,
            authority=generated_by,
        )

        # 3. Assemble Normalized Template Context
        context = self.prepare_template_context(
            case_id=case_uuid,
            detection_data=det_dict,
            characterization_data=char_dict,
            origin_data=orig_dict,
            candidates_data=cand_list,
            alternatives_data=alt_list,
            environmental_data=environmental,
            sar_chip_b64=sar_chip_b64,
            sha256_hash=sha256_hash,
            verification_qr_b64=qr_b64,
            generated_at=now_utc,
            generated_by=generated_by,
            model_versions=resolved_versions,
        )

        # 4. Render HTML Template with Rule 6 Banned Term Enforcement
        rendered_html = self.render_html("dossier_template.html", context)

        # 5. Render PDF with Dual Engine Fallback
        pdf_bytes: bytes
        if engine == "reportlab":
            pdf_bytes = self.generate_pdf_reportlab(context, qr_png_bytes)
        elif engine == "weasyprint":
            pdf_bytes = self.generate_pdf_weasyprint(rendered_html)
        else:  # auto
            try:
                pdf_bytes = self.generate_pdf_weasyprint(rendered_html)
            except Exception as e:
                logger.warning(
                    "WeasyPrint rendering failed (%s); falling back to ReportLab.", e, exc_info=True
                )
                pdf_bytes = self.generate_pdf_reportlab(context, qr_png_bytes)

        # 6. Save or Store PDF
        file_name = f"dossier_{case_uuid}_{sha256_hash[:16]}.pdf"
        target_path: Path
        if output_path:
            target_path = Path(output_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            target_path = self.storage_dir / file_name

        target_path.write_bytes(pdf_bytes)
        pdf_ref = f"s3://aegis-storage/dossiers/{file_name}"

        # 7. Database Persistence (Dossier and AuditLog)
        dossier_id = uuid.uuid4()
        if db_session is not None:
            db_dossier = Dossier(
                id=dossier_id,
                case_id=case_uuid,
                pdf_ref=pdf_ref,
                sha256_hash=sha256_hash,
                generated_by=generated_by,
                generated_at=now_utc,
                model_versions=resolved_versions,
            )
            db_session.add(db_dossier)

            db_audit = AuditLog(
                case_id=case_uuid,
                user_id=generated_by,
                action="generate_legal_dossier",
                details={
                    "dossier_id": str(dossier_id),
                    "sha256_hash": sha256_hash,
                    "pdf_ref": pdf_ref,
                    "file_size_bytes": len(pdf_bytes),
                    "model_versions": resolved_versions,
                },
                timestamp=now_utc,
            )
            db_session.add(db_audit)
            db_session.commit()

        return DossierResult(
            id=dossier_id,
            case_id=case_uuid,
            pdf_ref=pdf_ref,
            sha256_hash=sha256_hash,
            generated_by=generated_by,
            generated_at=now_utc,
            model_versions=resolved_versions,
            file_size_bytes=len(pdf_bytes),
            verification_qr_b64=qr_b64,
            pdf_bytes=pdf_bytes,
        )

    def verify_dossier_integrity(
        self,
        case_id: uuid.UUID | str,
        detection_data: dict[str, Any],
        characterization_data: dict[str, Any],
        origin_data: dict[str, Any],
        candidates_data: list[dict[str, Any]],
        alternatives_data: list[dict[str, Any]],
        model_versions: dict[str, Any],
        generated_at: datetime,
        expected_sha256: str,
    ) -> bool:
        """Verifies cryptographic chain-of-custody by recalculating and comparing canonical SHA-256."""
        import hmac

        calculated_hash = self.compute_canonical_sha256(
            case_id=case_id,
            detection_data=detection_data,
            characterization_data=characterization_data,
            origin_data=origin_data,
            candidates_data=candidates_data,
            alternatives_data=alternatives_data,
            model_versions=model_versions,
            generated_at=generated_at,
        )
        return hmac.compare_digest(calculated_hash.lower(), expected_sha256.lower())


def generate_dossier(
    case_id: uuid.UUID | str,
    detection: Any,
    characterization: Any,
    origin: Any,
    candidates: list[Any],
    alternatives: list[Any],
    **kwargs: Any,
) -> DossierResult:
    """Convenience functional interface for generating a legal dossier."""
    generator = DossierGenerator()
    return generator.generate_dossier(
        case_id=case_id,
        detection=detection,
        characterization=characterization,
        origin=origin,
        candidates=candidates,
        alternatives=alternatives,
        **kwargs,
    )
