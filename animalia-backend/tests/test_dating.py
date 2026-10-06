"""Dating unit tests: TimeTree parsing/caching, fossil dates, consistency rules.

No network, no database. Reuses the small tree from test_phylogeny:

  Reptilia ─┬─ Mesosauria †
            └─ Sauria ─┬─ Lepidosauria ─┬─ Sphenodontidae
                       │                └─ Squamata ─┬─ Episquamata ─┬─ Lacertidae
                       │                             │               └─ (Varanidae, Pythonidae)
                       │                             └─ Gekkonidae
                       └─ Archelosauria ─┬─ Testudines (Chelidae, Testudinidae)
                                         └─ Archosauria ─┬─ Crocodylia (Alligatoridae, Crocodylidae)
                                                         └─ Aves
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from etl.extract import timetree as timetree_module
from etl.extract.timetree import DivergenceEstimate, TimeTreeClient, parse_mrca
from etl.transform.build_phylogeny import load_backbone
from etl.transform.date_phylogeny import (
    AGE_FOSSIL_MINIMUM,
    AGE_INTERPOLATED,
    AGE_LAST_APPEARANCE,
    AGE_PRESENT,
    AGE_TIMETREE,
    DatingError,
    FossilDate,
    date_records,
    dating_ids,
    load_fossil_dates,
    validate_fossil_dates,
)
from tests.test_phylogeny import build, mini_backbone

ROOT = Path(__file__).resolve().parents[1]

# Fake NCBI ids: ott N -> 10*N; Aves -> 8782.
IDS = {f"ott{n}": [10 * n] for n in range(1, 10)} | {"backbone:Aves": [8782]}

FOSSIL = {
    "Reptilia": FossilDate("Reptilia", 316.9, None, None, None, "cite R", None),
    "Mesosauria": FossilDate("Mesosauria", None, 290.1, 283.3, None, "cite M", None),
    "Aves": FossilDate("Aves", None, 150.8, None, None, "cite A", None),
}

# Pair -> (age, ci_low, ci_high, studies). Keys are the first pair tried per node.
CONSISTENT = {
    (10, 60): (280.0, 275.0, 285.0, 30),    # Sauria
    (10, 20): (245.0, 236.0, 253.0, 20),    # Lepidosauria
    (20, 30): (200.0, 190.0, 210.0, 20),    # Squamata
    (20, 40): (170.0, 165.0, 175.0, 20),    # Episquamata
    (40, 50): (60.0, 55.0, 65.0, 10),       # Varanidae + Pythonidae
    (60, 80): (257.0, 249.0, 265.0, 30),    # Archelosauria
    (60, 70): (210.0, 200.0, 220.0, 20),    # Testudines
    (80, 8782): (243.0, 239.0, 247.0, 40),  # Archosauria
    (80, 90): (90.0, 80.0, 100.0, 20),      # Crocodylia
}


class FakeTimeTree:
    def __init__(self, answers):
        self.answers = {frozenset(k): v for k, v in answers.items()}
        self.asked: list[tuple[int, int]] = []

    def divergence(self, a, b):
        self.asked.append((a, b))
        hit = self.answers.get(frozenset((a, b)))
        if hit is None:
            return None
        age, low, high, n = hit
        return DivergenceEstimate(age, low, high, n, "20260820")


def dated(answers=CONSISTENT, fossil=FOSSIL):
    records = build()
    report = date_records(records, fossil, IDS, FakeTimeTree(answers))
    by_label = {r.label: r for r in records if r.label}
    by_key = {r.key: r for r in records}
    return records, report, by_label, by_key


def _check_monotone(records):
    by_key = {r.key: r for r in records}
    for r in records:
        if r.parent_key:
            parent = by_key[r.parent_key]
            assert max(r.age_ma, r.first_appearance_ma or 0) <= parent.age_ma + 1e-9, r.label


# --------------------------------------------------------------------------- #
# TimeTree parsing + cache
# --------------------------------------------------------------------------- #


def mrca_body(**overrides):
    body = {
        "found_ids": [8555, 8570], "missing_ids": [], "precomputed_age": 162.2,
        "precomputed_ci_low": 155.1, "precomputed_ci_high": 169.4, "adjusted_age": 160.0,
        "time_estimates": "{179,140,221.49}", "version": 20260820,
    }
    body.update(overrides)
    return body


def test_parse_mrca_uses_median_and_counts_studies() -> None:
    est = parse_mrca(mrca_body(), 8555, 8570)
    assert est == DivergenceEstimate(162.2, 155.1, 169.4, 3, "20260820")


@pytest.mark.parametrize(
    "overrides",
    [
        {"missing_ids": [8555], "found_ids": [8570]},   # TimeTree did not know one taxon
        {"found_ids": [8570, 1]},                       # answered for a different pair
        {"precomputed_age": None, "adjusted_age": None},  # node exists but has no age
    ],
)
def test_parse_mrca_rejects_unusable_answers(overrides) -> None:
    assert parse_mrca(mrca_body(**overrides), 8555, 8570) is None


def test_parse_mrca_falls_back_to_adjusted_age() -> None:
    assert parse_mrca(mrca_body(precomputed_age=None), 8555, 8570).age_ma == 160.0


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_client_serves_cache_without_network(tmp_path, monkeypatch) -> None:
    (tmp_path / "mrca.json").write_text(json.dumps({"8555+8570": {"status_code": 200, "body": mrca_body()}}))
    monkeypatch.setattr(timetree_module.requests, "get", lambda *a, **k: pytest.fail("network used"))
    client = TimeTreeClient(cache_dir=tmp_path)
    assert client.divergence(8570, 8555).age_ma == 162.2  # key is order-independent
    assert client.network_calls == 0


def test_client_fetches_once_and_does_not_cache_server_errors(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResponse(503, {}) if "1+2" in url else FakeResponse(200, mrca_body())

    monkeypatch.setattr(timetree_module.requests, "get", fake_get)
    monkeypatch.setattr(timetree_module, "SLEEP_BETWEEN_CALLS", 0)
    client = TimeTreeClient(cache_dir=tmp_path, refresh=True)
    client.divergence(8555, 8570)
    client.divergence(8555, 8570)
    assert len(calls) == 1  # refreshed once per run, then cached
    with pytest.raises(requests.HTTPError):
        client.divergence(1, 2)
    assert "1+2" not in client.cache


def test_client_save_pins_version(tmp_path, monkeypatch) -> None:
    meta = tmp_path / "source_versions.json"
    meta.write_text(json.dumps({"opentree": "x"}))
    monkeypatch.setattr(timetree_module, "METADATA_PATH", meta)
    client = TimeTreeClient(cache_dir=tmp_path)
    client.cache["8555+8570"] = {"status_code": 200, "body": mrca_body()}
    client.save()
    assert json.loads(meta.read_text()) == {"opentree": "x", "timetree": "20260820"}


# --------------------------------------------------------------------------- #
# Dating rules
# --------------------------------------------------------------------------- #


def test_every_node_gets_an_age_from_the_right_source() -> None:
    records, report, by, _ = dated()
    assert all(r.age_ma is not None for r in records)
    assert (by["Reptilia"].age_ma, by["Reptilia"].age_source) == (316.9, AGE_FOSSIL_MINIMUM)
    meso = by["Mesosauria"]
    assert (meso.age_ma, meso.first_appearance_ma, meso.age_source) == (283.3, 290.1, AGE_LAST_APPEARANCE)
    aves = by["Aves"]
    assert (aves.age_ma, aves.first_appearance_ma, aves.age_source) == (0.0, 150.8, AGE_PRESENT)
    assert by["Varanidae"].age_ma == 0.0 and by["Varanidae"].age_source == AGE_PRESENT
    sauria = by["Sauria"]
    assert (sauria.age_ma, sauria.age_ci_low, sauria.age_study_count) == (280.0, 275.0, 30)
    assert sauria.age_source == AGE_TIMETREE and "TimeTree" in sauria.age_citation
    assert by["Archosauria"].age_ma == 243.0  # crocodile vs bird via the Aves NCBI id
    assert report.adjusted == [] and report.discarded == [] and report.interpolated == []
    _check_monotone(records)


def test_tries_the_next_pair_when_timetree_cannot_answer() -> None:
    answers = dict(CONSISTENT)
    del answers[(20, 30)]                    # Lacertidae vs Gekkonidae unknown
    answers[(40, 30)] = (199.0, 190.0, 208.0, 15)  # Varanidae vs Gekkonidae known
    _, _, by, _ = dated(answers)
    assert by["Squamata"].age_ma == 199.0


def test_interpolates_when_timetree_has_nothing() -> None:
    answers = {k: v for k, v in CONSISTENT.items() if k != (20, 30)}
    records, report, by, _ = dated(answers)
    # Halfway between Lepidosauria (245) and its oldest dated descendant, Episquamata (170).
    assert by["Squamata"].age_ma == pytest.approx(207.5)
    assert by["Squamata"].age_source == AGE_INTERPOLATED
    assert report.interpolated == ["Squamata"]
    _check_monotone(records)


def test_overlapping_conflict_raises_the_ancestor() -> None:
    answers = dict(CONSISTENT)
    answers[(20, 40)] = (205.0, 195.0, 215.0, 20)  # Episquamata a bit older than Squamata (200)
    records, report, by, _ = dated(answers)
    squamata = by["Squamata"]
    assert squamata.age_ma == 205.0 and squamata.age_adjusted and squamata.age_unadjusted_ma == 200.0
    assert report.discarded == [] and report.adjusted == [("Squamata", 200.0, 205.0)]
    _check_monotone(records)


def test_clear_conflict_discards_the_weaker_descendant() -> None:
    answers = dict(CONSISTENT)
    answers[(20, 40)] = (240.0, 235.0, 245.0, 2)  # Episquamata far older, only 2 studies
    records, report, by, _ = dated(answers)
    epi = by["Episquamata"]
    assert report.discarded == [("Episquamata", 240.0)]
    assert epi.age_source == AGE_INTERPOLATED and epi.age_adjusted and epi.age_unadjusted_ma == 240.0
    assert epi.age_ma == pytest.approx((200.0 + 60.0) / 2)  # between Squamata and its oldest child
    assert by["Squamata"].age_ma == 200.0 and not by["Squamata"].age_adjusted
    _check_monotone(records)


def test_clear_conflict_discards_the_weaker_ancestor() -> None:
    answers = dict(CONSISTENT)
    answers[(20, 30)] = (150.0, 140.0, 160.0, 2)  # Squamata far younger than Episquamata, weak
    records, report, by, _ = dated(answers)
    assert report.discarded == [("Squamata", 150.0)]
    assert by["Squamata"].age_ma == pytest.approx((245.0 + 170.0) / 2)
    assert by["Episquamata"].age_ma == 170.0
    _check_monotone(records)


def test_fossil_minimum_is_raised_rather_than_contradicting_molecules() -> None:
    answers = dict(CONSISTENT)
    answers[(10, 60)] = (330.0, 320.0, 340.0, 30)  # Sauria older than Reptilia's fossil minimum
    records, report, by, _ = dated(answers)
    assert by["Reptilia"].age_ma == 330.0 and by["Reptilia"].age_unadjusted_ma == 316.9
    _check_monotone(records)


def test_flagged_family_asks_about_its_own_species_first() -> None:
    records = build()
    for r in records:
        if r.family == "Varanidae":
            r.placement_status = "confirmed"
        if r.family == "Pythonidae":
            r.placement_status = "flagged"

    def tnrs(name, ott, ncbi, rank):
        taxon = {"name": name, "ott_id": ott, "rank": rank, "tax_sources": [f"ncbi:{ncbi}"]}
        return {"name": name, "matches": [{"taxon": taxon, "score": 1.0, "is_synonym": False}]}

    ids = dating_ids(
        records,
        species_tnrs={"results": [tnrs("Varanus varius", 4, 1004, "species"), tnrs("Python regius", 5, 1005, "species")]},
        family_tnrs={"results": [tnrs("Varanidae", 400, 2004, "family"), tnrs("Pythonidae", 500, 2005, "family")]},
        group_tnrs={"results": [tnrs("Aves", 81461, 8782, "class")]},
    )
    assert ids["ott4"] == [2004, 1004]  # confirmed: whole family first
    assert ids["ott5"] == [1005, 2005]  # flagged: its own species first
    assert ids["backbone:Aves"] == [8782]
    assert "backbone:Mesosauria" not in ids  # extinct: nothing to ask TimeTree


# --------------------------------------------------------------------------- #
# Curated fossil dates
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("dates", "message"),
    [
        ({"Sauria": FossilDate("Sauria", None, 300.0, None, None, "c", None)}, "node_min_age_ma only"),
        ({"Aves": FossilDate("Aves", 100.0, None, None, None, "c", None)}, "not node_min_age_ma"),
        ({"Aves": FossilDate("Aves", None, 150.0, 10.0, None, "c", None)}, "no last appearance"),
        ({"Crocodylia": FossilDate("Crocodylia", 90.0, None, None, None, "c", None)}, "dated by TimeTree"),
        ({"Nope": FossilDate("Nope", 1.0, None, None, None, "c", None)}, "not in the tree"),
        ({}, "extinct group needs first and last"),
    ],
)
def test_validate_fossil_dates_errors(dates, message) -> None:
    valid = {} if not dates else {"Mesosauria": FOSSIL["Mesosauria"]}  # isolate one problem
    with pytest.raises(DatingError, match=message):
        validate_fossil_dates(valid | dates, mini_backbone())


def test_validate_fossil_dates_accepts_valid_set() -> None:
    validate_fossil_dates(FOSSIL, mini_backbone())


def test_validate_fossil_dates_rejects_reversed_range() -> None:
    dates = {"Mesosauria": FossilDate("Mesosauria", None, 280.0, 290.0, None, "c", None)}
    with pytest.raises(DatingError, match="older than first"):
        validate_fossil_dates(dates, mini_backbone())


def test_real_fossil_dates_are_valid_and_ordered() -> None:
    backbone = load_backbone(ROOT / "data" / "curated" / "reptile_backbone.csv")
    dates = load_fossil_dates(
        ROOT / "data" / "curated" / "fossil_dates.csv", backbone, frozenset({"Squamata"})
    )
    parent = {r.name: r.parent for r in backbone} | {"Squamata": "Lepidosauria"}
    for name, date in dates.items():
        oldest = date.node_min_age_ma or date.first_appearance_ma
        above = parent[name]
        while above and above not in dates:
            above = parent[above]
        if above:  # a group cannot predate the nearest fossil-dated node above it
            assert oldest <= dates[above].node_min_age_ma, name
    assert dates["Pterosauria"].last_appearance_ma == dates["Ornithischia"].last_appearance_ma == 66.0
    assert "Captorhinidae" not in dates
    assert dates["Squamata"].node_min_age_ma == 170.0
    assert (dates["Pterosauria"].first_appearance_ma, dates["Ornithischia"].first_appearance_ma) == (227.0, 210.0)
    assert (dates["Saurischia"].node_min_age_ma, dates["Sauropodomorpha"].first_appearance_ma) == (231.0, 230.0)
    assert dates["Aves"].first_appearance_ma == 150.0


def test_fossil_minimum_on_an_open_tree_clade() -> None:
    """A named Open Tree clade (here Squamata) can take a fossil minimum; when
    molecular dates below it are older, the minimum is raised to meet them."""
    fossil = dict(FOSSIL) | {"Squamata": FossilDate("Squamata", 190.0, None, None, None, "Evans 2003", None)}
    records, report, by, _ = dated(fossil=fossil)
    squamata = by["Squamata"]
    assert squamata.age_source == AGE_FOSSIL_MINIMUM and squamata.age_ma == 190.0
    assert squamata.age_citation == "Evans 2003"
    answers = dict(CONSISTENT)
    answers[(20, 40)] = (205.0, 195.0, 215.0, 30)  # Episquamata older than the 190 minimum
    records, report, by, _ = dated(answers=answers, fossil=fossil)
    assert by["Squamata"].age_ma == 205.0 and by["Squamata"].age_unadjusted_ma == 190.0
    _check_monotone(records)


def test_open_tree_clade_fossil_dates_take_minimum_only() -> None:
    backbone = mini_backbone()
    ok = {"Mesosauria": FOSSIL["Mesosauria"], "Squamata": FossilDate("Squamata", 170.0, None, None, None, "c", None)}
    validate_fossil_dates(ok, backbone, frozenset({"Squamata"}))
    bad = ok | {"Squamata": FossilDate("Squamata", None, 170.0, None, None, "c", None)}
    with pytest.raises(DatingError, match="node_min_age_ma only"):
        validate_fossil_dates(bad, backbone, frozenset({"Squamata"}))
    with pytest.raises(DatingError, match="not in the tree"):
        validate_fossil_dates(ok, backbone)  # Squamata unknown without the clade names


def test_fossil_date_never_applies_to_a_family_tip() -> None:
    fossil = dict(FOSSIL) | {"Varanidae": FossilDate("Varanidae", None, 50.0, None, None, "c", None)}
    _, _, by, _ = dated(fossil=fossil)
    assert by["Varanidae"].age_ma == 0.0 and by["Varanidae"].first_appearance_ma is None
