"""GBIF extract."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from etl.config import GBIF_API_BASE, GBIF_DATASET_VERSION

logger = logging.getLogger(__name__)


def extract(out_dir: Path) -> Path:
    """Download / cache GBIF name or occurrence exports into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": "gbif",
        "api_base": GBIF_API_BASE,
        "dataset_version": GBIF_DATASET_VERSION,
        "status": "stub",
        "note": "Wire GBIF species / backbone download here.",
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("GBIF extract stub wrote %s", path)
    return path
