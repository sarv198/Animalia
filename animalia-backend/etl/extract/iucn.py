"""IUCN Red List extract — live lookup only.

Licensing note
--------------
IUCN Red List data is subject to IUCN terms of use. Prefer authenticated
live API lookups per species. Do **not** bulk-download or redistribute
IUCN datasets without explicit permission from IUCN.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from etl.config import IUCN_API_BASE

logger = logging.getLogger(__name__)


def extract(out_dir: Path, species_names: list[str] | None = None) -> Path:
    """Look up IUCN status for a small curated name list (live API).

    Caches only the responses needed for this project — not a full dump.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    species_names = species_names or []
    manifest = {
        "source": "iucn",
        "api_base": IUCN_API_BASE,
        "mode": "live_lookup",
        "requested": species_names,
        "status": "stub",
        "licensing": (
            "Live lookup only. Do not redistribute bulk IUCN data "
            "without permission."
        ),
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("IUCN extract stub wrote %s (%d names)", path, len(species_names))
    return path
