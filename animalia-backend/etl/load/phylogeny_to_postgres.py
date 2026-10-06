"""Load the assembled phylogeny into phylo_nodes / phylogeny_edges.

The tree is replaced wholesale in one transaction: a rerun gives the same
result, and a failure leaves the previous tree untouched. Species and family
taxa must already be loaded (etl/load/to_postgres.py).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PhyloNode, PhylogenyEdge, Source, Species, Taxon
from etl.config import BACKBONE_PATH, FOSSIL_DATES_PATH
from etl.extract import reptiledb
from etl.transform.build_phylogeny import (
    SOURCE_BACKBONE,
    SOURCE_OPENTREE,
    PhylogenyBuild,
)

OPENTREE_SOURCE_NAME = "Open Tree of Life"
OPENTREE_URL = "https://tree.opentreeoflife.org"
BACKBONE_SOURCE_NAME = "Curated reptile backbone"
TIMETREE_SOURCE_NAME = "TimeTree 5"
TIMETREE_URL = "https://timetree.org"
FOSSIL_SOURCE_NAME = "Curated fossil dates"
REPTILEDB_SOURCE_NAME = "The Reptile Database"
REPTILEDB_URL = "http://www.reptile-database.org"


@dataclass
class PhyloLoadStats:
    nodes: int = 0
    edges: int = 0
    family_tips: int = 0
    group_tips: int = 0


def _upsert_source(db: Session, name: str, version: str | None, url: str | None) -> Source:
    source = db.query(Source).filter(Source.source_name == name).first()
    if source is None:
        source = Source(source_name=name)
        db.add(source)
    source.source_version = version
    source.source_url = url
    db.flush()
    return source


def load(build: PhylogenyBuild, timetree_version: str | None = None) -> PhyloLoadStats:
    """Replace the stored phylogeny with ``build`` (dated or not)."""
    stats = PhyloLoadStats()
    db = SessionLocal()
    try:
        species_by_ott = {
            s.ott_id: s for s in db.query(Species).filter(Species.ott_id.isnot(None))
        }
        families = {t.scientific_name: t for t in db.query(Taxon).filter(Taxon.rank == "family")}

        sources = {
            SOURCE_OPENTREE: _upsert_source(
                db, OPENTREE_SOURCE_NAME, build.synth_id, OPENTREE_URL
            ),
            SOURCE_BACKBONE: _upsert_source(
                db, BACKBONE_SOURCE_NAME, None, f"data/curated/{BACKBONE_PATH.name}"
            ),
        }
        checklist = reptiledb.checklist_path()
        if checklist.exists():  # family membership behind every placement_status
            _upsert_source(
                db, REPTILEDB_SOURCE_NAME, reptiledb.release_of(checklist.name), REPTILEDB_URL
            )
        if any(r.age_source for r in build.records):
            _upsert_source(db, TIMETREE_SOURCE_NAME, timetree_version, TIMETREE_URL)
            _upsert_source(db, FOSSIL_SOURCE_NAME, None, f"data/curated/{FOSSIL_DATES_PATH.name}")

        db.query(PhylogenyEdge).delete()
        db.query(PhyloNode).delete()

        has_children = {r.parent_key for r in build.records if r.parent_key}
        nodes: dict[str, PhyloNode] = {}
        for rec in build.records:
            species = None
            family = None
            if rec.species_ott_id is not None:
                species = species_by_ott.get(rec.species_ott_id)
                if species is None:
                    raise ValueError(f"no species row with ott_id={rec.species_ott_id}")
                family = families.get(rec.family or "")
                if family is None:
                    raise ValueError(f"no family taxon named {rec.family!r}")
            node = PhyloNode(
                source=sources[rec.source],
                external_id=rec.external_id,
                label=rec.label,
                is_tip=rec.key not in has_children,
                species=species,
                family_taxon=family,
                family_ott_id=rec.family_ott_id,
                placement_status=rec.placement_status,
                extinct=rec.extinct,
                collapsed_group=rec.collapsed_group,
                placement_uncertain=rec.placement_uncertain,
                anapsid_skull=rec.anapsid_skull,
                note=rec.note,
                citation=rec.citation,
                age_ma=rec.age_ma,
                age_ci_low=rec.age_ci_low,
                age_ci_high=rec.age_ci_high,
                age_source=rec.age_source,
                age_citation=rec.age_citation,
                age_study_count=rec.age_study_count,
                age_adjusted=rec.age_adjusted,
                age_unadjusted_ma=rec.age_unadjusted_ma,
                first_appearance_ma=rec.first_appearance_ma,
                last_appearance_ma=rec.last_appearance_ma,
            )
            db.add(node)
            nodes[rec.key] = node
            stats.nodes += 1
            if species is not None:
                stats.family_tips += 1
            elif rec.collapsed_group:
                stats.group_tips += 1
        db.flush()

        for rec in build.records:
            if rec.parent_key is None:
                continue
            db.add(
                PhylogenyEdge(
                    parent_node_id=nodes[rec.parent_key].id,
                    child_node_id=nodes[rec.key].id,
                    source=rec.source,
                )
            )
            stats.edges += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return stats


def print_stats(stats: PhyloLoadStats) -> None:
    print(f"phylo nodes: {stats.nodes}")
    print(f"phylo edges: {stats.edges}")
    print(f"family tips: {stats.family_tips}")
    print(f"group tips: {stats.group_tips}")
