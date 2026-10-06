"""Reptile Database checklist reader and the fossil-date review helper."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from etl.extract.reptiledb import checklist_path, read_checklist, release_of
from scripts.review_fossil_dates import consistent, extremes

ROOT = Path(__file__).resolve().parents[1]


def test_release_of() -> None:
    assert release_of("http://x/data/reptile_checklist_2026_06.xlsx") == "2026-06"
    with pytest.raises(ValueError):
        release_of("http://x/data/other.xlsx")


def test_read_checklist_normalises_columns(tmp_path) -> None:
    path = tmp_path / "reptile_checklist_2026_06.xlsx"
    pd.DataFrame(
        {
            "Species": ["Varanus varius ", "Python regius", None],
            "order": ["Sauria", "Serpentes", None],
            "Family": ["Varanidae", "Pythonidae", None],
        }
    ).to_excel(path, index=False)
    sheet = read_checklist(path)
    assert list(sheet["species"]) == ["Varanus varius", "Python regius"]  # trimmed, blank rows dropped
    assert list(sheet["genus"]) == ["Varanus", "Python"]
    assert list(sheet["family"]) == ["Varanidae", "Pythonidae"]


def test_read_checklist_requires_family(tmp_path) -> None:
    path = tmp_path / "bad.xlsx"
    pd.DataFrame({"Species": ["Varanus varius"], "order": ["Sauria"]}).to_excel(path, index=False)
    with pytest.raises(ValueError, match="family"):
        read_checklist(path)


@pytest.mark.skipif(not checklist_path().exists(), reason="checklist not downloaded")
def test_downloaded_checklist_covers_our_species() -> None:
    sheet = read_checklist(checklist_path())
    assert len(sheet) > 10_000
    with (ROOT / "species_crossref.csv").open(newline="", encoding="utf-8-sig") as handle:
        ours = {r["species"] for r in csv.DictReader(handle)}
    assert ours <= set(sheet["species"])


def test_review_interval_logic() -> None:
    record = {"eag": "247", "lag": "241.464", "tna": "Teleocrater"}
    assert consistent(241.5, record)
    assert consistent(247.0, record)
    assert not consistent(233.2, record)
    assert consistent(None, record) and consistent(100.0, None)
    oldest, youngest = extremes([{"eag": "10", "lag": "5"}, {"eag": "30", "lag": "20"}, {"eag": "8", "lag": "1"}])
    assert oldest["eag"] == "30" and youngest["lag"] == "1"
    assert extremes([]) == (None, None)
