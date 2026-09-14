"""Assemble taxonomy + phylogeny into a loadable tree table."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def run(reconciled: pd.DataFrame) -> pd.DataFrame:
    """Build parent/child links and phylogeny annotations for load."""
    logger.info("build_tree.run rows=%d", len(reconciled))
    cols = [
        "scientific_name",
        "rank",
        "parent_name",
        "col_id",
        "ott_id",
        "gbif_id",
        "iucn_status",
    ]
    for c in cols:
        if c not in reconciled.columns:
            reconciled[c] = None
    return reconciled[cols].copy()
