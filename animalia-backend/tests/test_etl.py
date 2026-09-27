"""ETL unit tests."""

from etl.transform.normalize import clean_name, unify_rank
from etl.validate.checks import VALID_IUCN_CODES


def test_clean_name() -> None:
    assert clean_name("  Panthera   leo ") == "Panthera leo"


def test_unify_rank() -> None:
    assert unify_rank("Familia") == "family"
    assert unify_rank("species") == "species"


def test_valid_iucn_codes() -> None:
    assert VALID_IUCN_CODES == {"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"}
