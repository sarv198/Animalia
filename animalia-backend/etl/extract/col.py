"""Catalogue of Life extract via ChecklistBank (COL XR)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from etl.config import COL_CHECKLISTBANK_BASE, COL_DATASET_KEY, METADATA_PATH

logger = logging.getLogger(__name__)


def extract(out_dir: Path) -> Path:
    """Download / cache COL checklist data into ``out_dir``.

    Returns path to the primary raw artifact.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": "catalogue_of_life",
        "via": "checklistbank",
        "base_url": COL_CHECKLISTBANK_BASE,
        "dataset_key": COL_DATASET_KEY,
        "status": "stub",
        "note": "Wire ChecklistBank download / export here.",
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _touch_version("col", COL_DATASET_KEY)
    logger.info("COL extract stub wrote %s", path)
    return path


def _touch_version(key: str, version: str) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if METADATA_PATH.exists():
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    data[key] = version
    METADATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
