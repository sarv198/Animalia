"""Load processed Parquet into Postgres."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Species, Taxon

logger = logging.getLogger(__name__)


def load(parquet_path: Path) -> None:
    """Upsert taxa/species from a processed tree Parquet file."""
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)

    df = pd.read_parquet(parquet_path)
    logger.info("Loading %d rows from %s", len(df), parquet_path)

    if df.empty:
        logger.warning("Nothing to load.")
        return

    db: Session = SessionLocal()
    try:
        # Stub: replace with real upsert / parent resolution once ETL produces data.
        for _, row in df.iterrows():
            name = row.get("scientific_name")
            if not name or pd.isna(name):
                continue
            existing = (
                db.query(Taxon).filter(Taxon.scientific_name == name).first()
            )
            if existing:
                continue
            taxon = Taxon(
                scientific_name=str(name),
                rank=str(row.get("rank") or "species"),
                col_taxon_id=_opt_str(row.get("col_taxon_id") or row.get("col_id")),
                taxonomic_source=_opt_str(row.get("taxonomic_source")),
            )
            db.add(taxon)
            db.flush()
            if str(row.get("rank") or "").lower() == "species":
                db.add(
                    Species(
                        taxon_id=taxon.id,
                        scientific_name=str(name),
                        col_taxon_id=_opt_str(
                            row.get("col_taxon_id") or row.get("col_id")
                        ),
                        gbif_taxon_id=_opt_int(
                            row.get("gbif_taxon_id") or row.get("gbif_id")
                        ),
                        ott_id=_opt_int(row.get("ott_id")),
                        iucn_category=_opt_str(
                            row.get("iucn_category") or row.get("iucn_status")
                        ),
                    )
                )
        db.commit()
        logger.info("Load committed.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _opt_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)


def _opt_int(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)
