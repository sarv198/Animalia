"""Data-quality assertions before load."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


def run(df: pd.DataFrame) -> None:
    """Raise if the processed frame fails quality gates."""
    required = {"scientific_name", "rank"}
    missing = required - set(df.columns)
    if missing:
        raise ValidationError(f"Missing required columns: {sorted(missing)}")

    if df.empty:
        logger.warning("Processed frame is empty — skipping row-level checks.")
        return

    null_names = df["scientific_name"].isna().sum()
    if null_names:
        raise ValidationError(f"{null_names} rows missing scientific_name")

    dupes = df["scientific_name"].duplicated().sum()
    if dupes:
        logger.warning("%d duplicate scientific_name values", dupes)

    logger.info("Validation passed (%d rows)", len(df))
