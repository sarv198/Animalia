"""Curate family-representative species for the tree-of-life subset."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def curate(input_csv: Path, output_csv: Path) -> None:
    """Filter / annotate family representatives from an input checklist.

    Expected columns (flexible): family, scientific_name, include (bool-ish).
    """
    if not input_csv.exists():
        raise FileNotFoundError(input_csv)

    with input_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    selected = [
        r
        for r in rows
        if str(r.get("include", "true")).strip().lower() in {"1", "true", "yes", "y"}
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({k for r in selected for k in r.keys()}) or [
        "family",
        "scientific_name",
        "include",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)

    logger.info("Wrote %d curated species → %s", len(selected), output_csv)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/family_candidates.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/family_representatives.csv"),
    )
    args = parser.parse_args()
    curate(args.input, args.output)


if __name__ == "__main__":
    main()
