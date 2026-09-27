"""
inspect_crossref.py

Summarize how clean species_crossref.csv is before it is loaded.
Reads the CSV only — does not touch the database.

Usage (from animalia-backend/):
    python scripts/inspect_crossref.py
    python scripts/inspect_crossref.py --in species_crossref.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ID_COLUMNS = ("gbif_usage_key", "col_taxon_id", "ott_id", "iucn_status")


def load_crossref(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def is_missing(series: pd.Series) -> pd.Series:
    return series.str.strip().isin({"", "None", "nan", "NaN"})


def review_reasons(flags: pd.Series) -> pd.Series:
    parts = (
        flags.loc[~is_missing(flags)]
        .str.split(";")
        .explode()
        .str.strip()
    )
    return parts.loc[parts != ""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "species_crossref.csv",
    )
    args = parser.parse_args()

    df = load_crossref(args.input_path)
    flagged = ~is_missing(df["review_flag"]) if "review_flag" in df.columns else None

    print(f"File: {args.input_path}")
    print(f"Total rows: {len(df)}")

    if flagged is None:
        print("Rows with a review_flag: column missing")
    else:
        print(f"Rows with a review_flag: {int(flagged.sum())}")
        reasons = review_reasons(df["review_flag"])
        print("\nReview-flag reasons:")
        if reasons.empty:
            print("  (none)")
        else:
            for reason, count in reasons.value_counts().items():
                print(f"  {reason}: {count}")

    print("\nMissing identifiers:")
    for column in ID_COLUMNS:
        if column not in df.columns:
            print(f"  {column}: column missing")
            continue
        print(f"  {column}: {int(is_missing(df[column]).sum())}")


if __name__ == "__main__":
    main()
