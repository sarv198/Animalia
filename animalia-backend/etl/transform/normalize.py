"""Clean scientific names and unify taxonomic ranks."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CANONICAL_RANKS = (
    "domain",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
    "subspecies",
)


def clean_name(name: str) -> str:
    return " ".join(name.strip().split())


def unify_rank(rank: str) -> str:
    r = rank.strip().lower()
    aliases = {
        "divisio": "phylum",
        "division": "phylum",
        "ordo": "order",
        "familia": "family",
        "genus": "genus",
        "species": "species",
    }
    return aliases.get(r, r)


def run(*raw_paths: Path) -> pd.DataFrame:
    """Normalize raw extracts into a single working frame.

    Stub returns an empty schema-ready DataFrame until extractors are wired.
    """
    logger.info("normalize.run inputs=%s", [str(p) for p in raw_paths])
    return pd.DataFrame(
        columns=[
            "scientific_name",
            "rank",
            "parent_name",
            "col_taxon_id",
            "ott_id",
            "gbif_taxon_id",
        ]
    )
