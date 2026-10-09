"""ETL source URLs and pinned dataset versions."""

import os
from pathlib import Path

# Default to <backend root>/data so the pipeline works from any working directory.
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_PATH = DATA_DIR / "metadata" / "source_versions.json"
CURATED_DIR = DATA_DIR / "curated"
OPENTREE_RAW_DIR = RAW_DIR / "opentree"
TIMETREE_RAW_DIR = RAW_DIR / "timetree"
REPTILEDB_RAW_DIR = RAW_DIR / "reptiledb"
BACKBONE_PATH = CURATED_DIR / "reptile_backbone.csv"
FOSSIL_DATES_PATH = CURATED_DIR / "fossil_dates.csv"
FAMILY_OVERRIDES_PATH = CURATED_DIR / "family_status_overrides.csv"
CLADE_NAMES_PATH = CURATED_DIR / "clade_names.csv"
MEDIA_RAW_DIR = RAW_DIR / "media"
# GARD 1.7 range polygons (Roll & Meiri 2022, Dryad, CC0). Dryad serves the
# files only through its website, so they are downloaded by hand into here.
GARD_RAW_DIR = RAW_DIR / "gard"
GARD_DATASET_URL = "https://doi.org/10.5061/dryad.9cnp5hqmb"

# Catalogue of Life / ChecklistBank (COL XR)
COL_CHECKLISTBANK_BASE = "https://api.checklistbank.org"
COL_DATASET_KEY = os.getenv("COL_DATASET_VERSION") or "col"

# Open Tree of Life
OPENTREE_API_BASE = os.getenv(
    "OPENTREE_API_BASE", "https://api.opentreeoflife.org/v3"
)
OPENTREE_SYNTHESIS_VERSION = os.getenv("OPENTREE_SYNTHESIS_VERSION", "")

# TimeTree 5 (divergence times; uses NCBI taxonomy ids)
TIMETREE_API_BASE = os.getenv("TIMETREE_API_BASE", "https://api.timetree.org")

# The Reptile Database species checklist (current family membership)
REPTILEDB_CHECKLIST_URL = os.getenv(
    "REPTILEDB_CHECKLIST_URL",
    "http://www.reptile-database.org/data/reptile_checklist_2026_06.xlsx",
)

# Wikimedia asks API clients to identify themselves with a contact (URL or
# email); anonymous-looking clients are throttled hard.
WIKIMEDIA_CONTACT = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/sarv198/Animalia")

# Non-commercial (CC BY-NC) photos are allowed only while the site is
# non-commercial. Set to "false" before any commercial use.
ALLOW_NONCOMMERCIAL_IMAGES = os.getenv("ALLOW_NONCOMMERCIAL_IMAGES", "true").lower() == "true"

# GBIF
GBIF_API_BASE = "https://api.gbif.org/v1"
GBIF_DATASET_VERSION = os.getenv("GBIF_DATASET_VERSION", "")

# IUCN — live lookup only; do not bulk-redistribute without permission
IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3"
