"""ETL source URLs and pinned dataset versions."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_PATH = DATA_DIR / "metadata" / "source_versions.json"

# Catalogue of Life / ChecklistBank (COL XR)
COL_CHECKLISTBANK_BASE = "https://api.checklistbank.org"
COL_DATASET_KEY = os.getenv("COL_DATASET_VERSION") or "col"

# Open Tree of Life
OPENTREE_API_BASE = os.getenv(
    "OPENTREE_API_BASE", "https://api.opentreeoflife.org/v3"
)
OPENTREE_SYNTHESIS_VERSION = os.getenv("OPENTREE_SYNTHESIS_VERSION", "")

# GBIF
GBIF_API_BASE = "https://api.gbif.org/v1"
GBIF_DATASET_VERSION = os.getenv("GBIF_DATASET_VERSION", "")

# IUCN — live lookup only; do not bulk-redistribute without permission
IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3"
