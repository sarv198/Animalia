"""Orchestrator: extract → transform → validate → load."""

from __future__ import annotations

import logging
from pathlib import Path

from etl.config import METADATA_PATH, PROCESSED_DIR, RAW_DIR
from etl.extract import col, gbif, iucn, opentree
from etl.load import to_postgres
from etl.transform import build_tree, normalize, reconcile
from etl.validate import checks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_dirs() -> None:
    for path in (
        RAW_DIR / "col",
        RAW_DIR / "gbif",
        RAW_DIR / "opentree",
        RAW_DIR / "iucn",
        PROCESSED_DIR,
        METADATA_PATH.parent,
    ):
        path.mkdir(parents=True, exist_ok=True)


def run(skip_iucn: bool = True) -> None:
    """Run the full ETL pipeline.

    IUCN is skipped by default (live lookup / licensing).
    """
    ensure_dirs()
    logger.info("Extracting sources…")
    col_raw = col.extract(RAW_DIR / "col")
    ott_raw = opentree.extract(RAW_DIR / "opentree")
    gbif_raw = gbif.extract(RAW_DIR / "gbif")
    iucn_raw = None if skip_iucn else iucn.extract(RAW_DIR / "iucn")

    logger.info("Transforming…")
    normalized = normalize.run(col_raw, ott_raw, gbif_raw)
    reconciled = reconcile.run(normalized, iucn_raw=iucn_raw)
    tree_df = build_tree.run(reconciled)

    out_path = PROCESSED_DIR / "tree.parquet"
    tree_df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)

    logger.info("Validating…")
    checks.run(tree_df)

    logger.info("Loading into Postgres…")
    to_postgres.load(out_path)
    logger.info("Pipeline complete.")


if __name__ == "__main__":
    run()
