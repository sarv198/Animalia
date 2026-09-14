"""Open Tree of Life extract."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from etl.config import OPENTREE_API_BASE, OPENTREE_SYNTHESIS_VERSION

logger = logging.getLogger(__name__)


def extract(out_dir: Path) -> Path:
    """Fetch / cache OpenTree synthesis or taxonomy into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": "opentree",
        "api_base": OPENTREE_API_BASE,
        "synthesis_version": OPENTREE_SYNTHESIS_VERSION,
        "status": "stub",
        "note": "Wire tnrs / taxonomy / synth tree downloads here.",
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("OpenTree extract stub wrote %s", path)
    return path
