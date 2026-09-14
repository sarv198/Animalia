"""ETL unit tests."""

import pandas as pd

from etl.transform.normalize import clean_name, unify_rank
from etl.validate.checks import ValidationError, run as validate


def test_clean_name() -> None:
    assert clean_name("  Panthera   leo ") == "Panthera leo"


def test_unify_rank() -> None:
    assert unify_rank("Familia") == "family"
    assert unify_rank("species") == "species"


def test_validate_missing_columns() -> None:
    try:
        validate(pd.DataFrame({"foo": [1]}))
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_validate_empty_ok() -> None:
    validate(pd.DataFrame(columns=["scientific_name", "rank"]))
