"""ETL source URLs and pinned dataset versions."""

from pathlib import Path

from app.config import settings

DATA_DIR = Path(settings.data_dir)
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_PATH = DATA_DIR / "metadata" / "source_versions.json"

# Catalogue of Life / ChecklistBank (COL XR)
COL_CHECKLISTBANK_BASE = "https://api.checklistbank.org"
COL_DATASET_KEY = settings.col_dataset_version or "col"

# Open Tree of Life
OPENTREE_API_BASE = settings.opentree_api_base
OPENTREE_SYNTHESIS_VERSION = settings.opentree_synthesis_version

# GBIF
GBIF_API_BASE = "https://api.gbif.org/v1"
GBIF_DATASET_VERSION = settings.gbif_dataset_version

# IUCN — live lookup only; do not bulk-redistribute without permission
IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3"
