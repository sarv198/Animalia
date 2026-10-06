"""Open Tree of Life extract.

Caches every response the phylogeny transform needs under ``out_dir`` so the
transform can be re-run offline and the inputs can be audited later:

  about.json              synthesis version (synth_id, taxonomy version)
  induced_subtree.json    topology connecting every representative species
  family_tnrs.json        family name -> OTT id matches (NCBI ids for dating)
  species_tnrs.json       species name -> OTT taxon (carries NCBI ids for dating)
  group_tnrs.json         living collapsed backbone groups (e.g. Aves) -> OTT taxon
  checklist_matches.json  every Reptile Database species name -> OTT id
  group_subtrees.json     Open Tree's full tree under each living backbone group
                          (Lepidosauria, Testudines, Crocodylia), tips as OTT ids
  species_support.json    species OTT id -> published trees that contain it (or
                          its subspecies); empty means Open Tree places it by
                          taxonomy alone. Filled lazily (see PublishedTrees).
  manifest.json           what was fetched and when

The last two feed the whole-family check (etl/transform/family_check.py).
"""

from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from etl.config import (
    BACKBONE_PATH,
    METADATA_PATH,
    OPENTREE_API_BASE,
    OPENTREE_RAW_DIR,
    OPENTREE_SYNTHESIS_VERSION,
)
from etl.extract import reptiledb
from etl.transform import newick

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_CALLS = 0.2  # be polite to a free public API

ABOUT_FILE = "about.json"
SUBTREE_FILE = "induced_subtree.json"
FAMILY_TNRS_FILE = "family_tnrs.json"
SPECIES_TNRS_FILE = "species_tnrs.json"
GROUP_TNRS_FILE = "group_tnrs.json"
CHECKLIST_MATCHES_FILE = "checklist_matches.json"
GROUP_SUBTREES_FILE = "group_subtrees.json"
SPECIES_SUPPORT_FILE = "species_support.json"
MANIFEST_FILE = "manifest.json"

CACHE_FILES = (
    ABOUT_FILE,
    SUBTREE_FILE,
    FAMILY_TNRS_FILE,
    SPECIES_TNRS_FILE,
    GROUP_TNRS_FILE,
    CHECKLIST_MATCHES_FILE,
    GROUP_SUBTREES_FILE,
    SPECIES_SUPPORT_FILE,
)

TNRS_BATCH = 5000  # names per match_names request


def cache_complete(raw_dir: Path = OPENTREE_RAW_DIR) -> bool:
    """True when every file the transform and dating steps read is cached."""
    return all((raw_dir / name).exists() for name in CACHE_FILES)


class OpenTreeError(RuntimeError):
    """Open Tree returned something the pipeline cannot use."""


def _post(path: str, payload: dict[str, Any]) -> requests.Response:
    return requests.post(
        f"{OPENTREE_API_BASE}{path}", json=payload, timeout=REQUEST_TIMEOUT
    )


def read_crossref(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def species_ott_ids(rows: list[dict[str, str]]) -> list[int]:
    """OTT ids of the representative species. Every row must have one."""
    missing = [row["species"] for row in rows if not (row.get("ott_id") or "").strip()]
    if missing:
        raise OpenTreeError(f"species without ott_id: {missing}")
    return [int(float(row["ott_id"])) for row in rows]


def family_names(rows: list[dict[str, str]]) -> list[str]:
    """Unique family names in CSV order."""
    return list(dict.fromkeys(row["family"].strip() for row in rows))


def _family_stem(name: str) -> str | None:
    """'Crotaphytidae' and 'Crotaphytinae' both -> 'Crotaphyt'."""
    for suffix in ("idae", "inae"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def best_family_match(result: dict[str, Any]) -> dict[str, Any] | None:
    """The Open Tree taxon that is the same group as one queried family name.

    Preferred: an exact, non-synonym, family-rank match. Otherwise a synonym is
    accepted only when it is the same group at a different rank, e.g. Open Tree
    keeps Crotaphytidae as subfamily Crotaphytinae of a broad Iguanidae. Any
    other synonym describes a different group, so it is not evidence about ours.
    """
    matches = [m for m in result.get("matches", []) if m.get("score") == 1.0]
    for match in matches:
        taxon = match.get("taxon", {})
        if taxon.get("rank") == "family" and not match.get("is_synonym"):
            return taxon
    stem = _family_stem(result.get("name", ""))
    for match in matches:
        taxon = match.get("taxon", {})
        if (
            stem is not None
            and taxon.get("rank") in {"family", "subfamily"}
            and _family_stem(taxon.get("name", "")) == stem
        ):
            return taxon
    return None


def fetch_about() -> dict[str, Any]:
    resp = _post("/tree_of_life/about", {})
    resp.raise_for_status()
    return resp.json()


def fetch_induced_subtree(ott_ids: list[int]) -> dict[str, Any]:
    """The part of the synthetic tree that connects ``ott_ids``."""
    resp = _post(
        "/tree_of_life/induced_subtree",
        {"ott_ids": ott_ids, "label_format": "name_and_id"},
    )
    if resp.status_code == 400:
        raise OpenTreeError(f"induced_subtree rejected the request: {resp.text[:500]}")
    resp.raise_for_status()
    return resp.json()


def ncbi_id(taxon: dict[str, Any] | None) -> int | None:
    """The NCBI taxonomy id in an OTT taxon's tax_sources, e.g. 'ncbi:8555' -> 8555."""
    for source in (taxon or {}).get("tax_sources", []):
        if source.startswith("ncbi:"):
            return int(source.split(":", 1)[1])
    return None


def living_group_names(backbone_csv: Path = BACKBONE_PATH) -> list[str]:
    """Collapsed backbone groups that are still alive (e.g. Aves): datable by TimeTree."""
    with backbone_csv.open(newline="", encoding="utf-8-sig") as handle:
        return [
            row["name"].strip()
            for row in csv.DictReader(handle)
            if row["collapsed_group"].strip().lower() == "true"
            and row["extinct"].strip().lower() != "true"
        ]


def fetch_name_matches(names: list[str]) -> dict[str, Any]:
    """Exact TNRS matches for scientific names, restricted to animals."""
    resp = _post(
        "/tnrs/match_names",
        {"names": names, "context_name": "Animals", "do_approximate_matching": False},
    )
    resp.raise_for_status()
    return resp.json()


def best_species_match(result: dict[str, Any]) -> dict[str, Any] | None:
    """{ott_id, synonym} for one exact species-name match, preferring an
    accepted name over a synonym. A synonym still points at the same species:
    Open Tree simply files it under another name."""
    exact = [
        m for m in result.get("matches", [])
        if m.get("score") == 1.0 and m.get("taxon", {}).get("rank") in {"species", "subspecies"}
    ]
    exact.sort(key=lambda m: bool(m.get("is_synonym")))
    if not exact:
        return None
    return {"ott_id": exact[0]["taxon"]["ott_id"], "synonym": bool(exact[0].get("is_synonym"))}


def fetch_checklist_matches(names: list[str]) -> dict[str, dict[str, Any]]:
    """species name -> {ott_id, synonym} for every name Open Tree knows exactly."""
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(names), TNRS_BATCH):
        for result in fetch_name_matches(names[start:start + TNRS_BATCH]).get("results", []):
            match = best_species_match(result)
            if match is not None:
                out[result["name"]] = match
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out


def anchor_groups(backbone_csv: Path = BACKBONE_PATH) -> dict[str, list[str]]:
    """Living backbone groups and the two families that define each one."""
    with backbone_csv.open(newline="", encoding="utf-8-sig") as handle:
        return {
            row["name"].strip(): [f.strip() for f in row["anchor_families"].split(";") if f.strip()]
            for row in csv.DictReader(handle)
            if (row["anchor_families"] or "").strip()
        }


def fetch_group_subtrees(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """For each living backbone group: its node in the synthetic tree (the common
    ancestor of its anchor families' representatives) and the full subtree under
    it, with tips labelled by OTT id."""
    ott_by_family = {row["family"].strip(): int(float(row["ott_id"])) for row in rows}
    out: dict[str, dict[str, Any]] = {}
    for group, families in anchor_groups().items():
        missing = [f for f in families if f not in ott_by_family]
        if missing:
            raise OpenTreeError(f"{group}: anchor families without a species: {missing}")
        resp = _post("/tree_of_life/mrca", {"ott_ids": [ott_by_family[f] for f in families]})
        resp.raise_for_status()
        node_id = resp.json()["mrca"]["node_id"]
        resp = _post("/tree_of_life/subtree", {"node_id": node_id, "label_format": "id"})
        resp.raise_for_status()
        out[group] = {"node_id": node_id, "newick": resp.json()["newick"]}
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out


def _published_trees(node_id: str) -> tuple[list[str], int]:
    """(published trees that have this node as a tip, number of tips under it).
    A node that is not in the synthetic tree has neither."""
    resp = _post("/tree_of_life/node_info", {"node_id": node_id})
    if resp.status_code == 400:
        return [], 0
    resp.raise_for_status()
    body = resp.json()
    return list((body.get("terminal") or {}).keys()), body.get("num_tips") or 0


def species_published_trees(ott_id: int) -> list[str]:
    """Published trees (study@tree) in Open Tree that contain this species.

    A species with subspecies is an internal node, so its subspecies tips are
    checked instead. An empty list means Open Tree places the species by
    taxonomy alone: its position is bookkeeping, not evidence.
    """
    trees, num_tips = _published_trees(f"ott{ott_id}")
    if not trees and num_tips:
        resp = _post("/tree_of_life/subtree", {"node_id": f"ott{ott_id}", "label_format": "id"})
        resp.raise_for_status()
        for tip in newick_tip_ids(resp.json()["newick"]):
            if tip != f"ott{ott_id}":
                trees.extend(t for t in _published_trees(tip)[0] if t not in trees)
    return sorted(trees)


class PublishedTrees:
    """Cached ``species_published_trees`` lookups (data/raw/opentree/species_support.json).

    Species are looked up on first use, so the family check only pays for the
    species it needs to judge; reruns are offline.
    """

    def __init__(self, raw_dir: Path = OPENTREE_RAW_DIR, refresh: bool = False) -> None:
        self.path = raw_dir / SPECIES_SUPPORT_FILE
        self.cache: dict[str, list[str]] = {}
        if self.path.exists() and not refresh:
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        self.network_calls = 0

    def __call__(self, ott_id: int) -> list[str]:
        key = str(ott_id)
        if key not in self.cache:
            self.cache[key] = species_published_trees(ott_id)
            self.network_calls += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
        return self.cache[key]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache, indent=1, sort_keys=True), encoding="utf-8")


def newick_tip_ids(text: str) -> list[str]:
    """Tip labels of an id-labelled Newick string ('ott123')."""
    out, stack = [], [newick.parse(text)]
    while stack:
        node = stack.pop()
        if node.children:
            stack.extend(node.children)
        elif node.label:
            out.append(node.label)
    return out


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _record_version(synth_id: str) -> None:
    """Pin the synthesis version in data/metadata/source_versions.json."""
    versions: dict[str, Any] = {}
    if METADATA_PATH.exists():
        versions = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    versions["opentree"] = synth_id
    METADATA_PATH.write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")


def extract(crossref_csv: Path, out_dir: Path = OPENTREE_RAW_DIR) -> Path:
    """Fetch and cache the Open Tree inputs for every species in ``crossref_csv``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_crossref(crossref_csv)
    ott_ids = species_ott_ids(rows)
    families = family_names(rows)

    about = fetch_about()
    synth_id = about.get("synth_id", "")
    if OPENTREE_SYNTHESIS_VERSION and OPENTREE_SYNTHESIS_VERSION != synth_id:
        logger.warning(
            "Open Tree is serving %s but OPENTREE_SYNTHESIS_VERSION pins %s",
            synth_id,
            OPENTREE_SYNTHESIS_VERSION,
        )

    subtree = fetch_induced_subtree(ott_ids)
    tnrs = fetch_name_matches(families)
    family_ott = [
        taxon["ott_id"]
        for taxon in (best_family_match(r) for r in tnrs.get("results", []))
        if taxon is not None
    ]
    species_tnrs = fetch_name_matches([row["species"].strip() for row in rows])
    group_tnrs = fetch_name_matches(living_group_names())
    checklist = reptiledb.read_checklist(reptiledb.download())
    checklist_matches = fetch_checklist_matches(checklist["species"].tolist())
    group_subtrees = fetch_group_subtrees(rows)
    # Which studies contain a species only changes with a new synthesis.
    previous = out_dir / ABOUT_FILE
    previous_synth = json.loads(previous.read_text(encoding="utf-8")).get("synth_id") if previous.exists() else None
    support = PublishedTrees(out_dir, refresh=previous_synth != synth_id)
    for ott_id in ott_ids:  # representatives up front; others on demand
        support(ott_id)

    _write_json(out_dir / ABOUT_FILE, about)
    _write_json(out_dir / SUBTREE_FILE, subtree)
    _write_json(out_dir / FAMILY_TNRS_FILE, tnrs)
    _write_json(out_dir / SPECIES_TNRS_FILE, species_tnrs)
    _write_json(out_dir / GROUP_TNRS_FILE, group_tnrs)
    _write_json(out_dir / CHECKLIST_MATCHES_FILE, checklist_matches)
    _write_json(out_dir / GROUP_SUBTREES_FILE, group_subtrees)
    support.save()
    for stale in ("family_node_info.json", "representative_support.json"):  # superseded
        if (out_dir / stale).exists():
            (out_dir / stale).unlink()
    _write_json(
        out_dir / MANIFEST_FILE,
        {
            "source": "opentree",
            "api_base": OPENTREE_API_BASE,
            "synth_id": synth_id,
            "taxonomy_version": about.get("taxonomy_version"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "species_requested": len(ott_ids),
            "families_requested": len(families),
            "families_matched": len(family_ott),
            "checklist_species": len(checklist),
            "checklist_species_matched": len(checklist_matches),
        },
    )
    _record_version(synth_id)
    logger.info("Open Tree extract (%s) wrote %s", synth_id, out_dir)
    return out_dir
