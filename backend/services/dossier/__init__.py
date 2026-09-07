"""AEGIS-Marine: Legal Evidence Dossier Generation Service (FR-20, C13)."""

from backend.services.dossier.dossier_generator import (
    DEFAULT_MODEL_VERSIONS,
    FR20_DISCLAIMER_TEXT,
    DossierGenerator,
    assert_no_banned_terms,
    generate_dossier,
)

__all__ = [
    "DossierGenerator",
    "generate_dossier",
    "assert_no_banned_terms",
    "DEFAULT_MODEL_VERSIONS",
    "FR20_DISCLAIMER_TEXT",
]
