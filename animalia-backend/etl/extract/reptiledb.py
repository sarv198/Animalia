"""The Reptile Database species checklist.

The checklist is the authority on which family each reptile species currently
belongs to. It is downloaded once, cached under data/raw/reptiledb/, and its
release is pinned in data/metadata/source_versions.json. Cite as `citation()`
returns (the form The Reptile Database asks for).

Run directly to (re)download:  python -m etl.extract.reptiledb
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from etl.config import METADATA_PATH, REPTILEDB_CHECKLIST_URL, REPTILEDB_RAW_DIR

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120
_RELEASE_RE = re.compile(r"reptile_checklist_(\d{4})_(\d{2})")

# Columns we rely on, matched case-insensitively against the sheet header.
# 'species' is the full binomial; genus is derived from it.
REQUIRED_COLUMNS = ("order", "family", "species")


CITATION_TEMPLATE = (
    "Uetz, P., Freed, P., Aguilar, R., Reyes, F., Kudera, J. & Hošek, J. (eds.) ({year}) "
    "The Reptile Database, http://www.reptile-database.org, accessed {accessed}"
)


def citation(path: Path | None = None) -> str:
    """The required citation, dated by when the cached checklist was downloaded."""
    path = path or checklist_path()
    accessed = datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else datetime.now()
    year = release_of(path.name).split("-")[0]
    return CITATION_TEMPLATE.format(year=year, accessed=f"{accessed.day} {accessed:%B %Y}")


def release_of(url: str) -> str:
    """'.../reptile_checklist_2026_06.xlsx' -> '2026-06'."""
    match = _RELEASE_RE.search(url)
    if match is None:
        raise ValueError(f"cannot read a release date from {url}")
    return f"{match.group(1)}-{match.group(2)}"


def checklist_path(url: str = REPTILEDB_CHECKLIST_URL, raw_dir: Path = REPTILEDB_RAW_DIR) -> Path:
    return raw_dir / url.rsplit("/", 1)[-1]


def download(url: str = REPTILEDB_CHECKLIST_URL, raw_dir: Path = REPTILEDB_RAW_DIR) -> Path:
    """Download the checklist if it is not cached yet; pin its release."""
    path = checklist_path(url, raw_dir)
    if not path.exists():
        raw_dir.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        if not resp.content.startswith(b"PK"):  # xlsx files are zip archives
            raise ValueError(f"{url} did not return an xlsx file")
        path.write_bytes(resp.content)
        logger.info("downloaded %s (%d bytes)", path, len(resp.content))
    _record_version(release_of(url))
    return path


def _record_version(release: str) -> None:
    versions = {}
    if METADATA_PATH.exists():
        versions = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    versions["reptiledb"] = release
    METADATA_PATH.write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")


def read_checklist(path: Path) -> pd.DataFrame:
    """One row per species, with lower-case column names and a derived 'genus'.

    The sheet's first row is the header; 'species' holds the full binomial.
    """
    frame = pd.read_excel(path, dtype=str)
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"checklist {path.name} is missing columns {missing}; got {list(frame.columns)}")
    frame = frame.dropna(subset=["species"])
    for column in REQUIRED_COLUMNS:
        frame[column] = frame[column].str.strip()
    frame["genus"] = frame["species"].str.split().str[0]
    return frame


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sheet = read_checklist(download())
    print(f"{len(sheet)} species, {sheet['family'].nunique()} families")
