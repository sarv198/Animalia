"""Load species_crossref.csv, then run data-quality checks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.load.to_postgres import load, print_stats
from etl.validate.checks import ValidationError, run as run_checks

DEFAULT_CSV = ROOT / "species_crossref.csv"


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    stats = load(csv_path)
    print_stats(stats)
    try:
        run_checks()
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("all checks passed")


if __name__ == "__main__":
    main()
