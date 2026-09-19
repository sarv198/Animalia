"""ID matching / cross-reference across COL, OpenTree, GBIF (and optional IUCN)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def run(normalized: pd.DataFrame, *, iucn_raw: Path | None = None) -> pd.DataFrame:
    """Reconcile external IDs onto a unified taxon table.

    Place your crossref matching script logic here.
    """
    logger.info(
        "reconcile.run rows=%d iucn_raw=%s",
        len(normalized),
        iucn_raw,
    )
    out = normalized.copy()
    if "iucn_category" not in out.columns:
        out["iucn_category"] = None
    return out
