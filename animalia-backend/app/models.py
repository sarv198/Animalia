"""
app/models.py

The single source of truth for the database schema. Both the FastAPI app and
the ETL pipeline import these classes, so the tables are defined exactly once.
Alembic reads this file to autogenerate migrations.

Design notes:
  - `taxa`  = the classification hierarchy (order -> family -> genus -> species
              nodes), self-referencing via parent_id. This is what the zoomable
              tree renders.
  - `species` = the leaf entities that carry enrichment (IDs, conservation,
              occurrence counts). External IDs are the "glue" - never join on
              scientific names, which change.
  - `phylogeny_edges` = evolutionary relationships, kept SEPARATE from taxonomy
              because the two are not the same thing (see caveat at bottom).
  - `sources` = provenance, so every value can be traced to a dataset version.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    """Provenance for every ingested dataset. Referenced by version in metadata."""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100))          # "Catalogue of Life"
    source_version: Mapped[str | None] = mapped_column(String(100))  # "COL XR 2026-08-26"
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(100))        # "CC BY 4.0"
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Taxon(Base):
    """A node in the classification hierarchy. Self-referencing to form the tree."""
    __tablename__ = "taxa"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("taxa.id"), index=True)
    scientific_name: Mapped[str] = mapped_column(String(255), index=True)
    rank: Mapped[str] = mapped_column(String(50))  # order | family | genus | species ...
    col_taxon_id: Mapped[str | None] = mapped_column(String(100), index=True)
    taxonomic_source: Mapped[str | None] = mapped_column(String(100))

    parent = relationship("Taxon", remote_side="Taxon.id", backref="children")


class Species(Base):
    """A leaf species carrying all enrichment. External IDs glue the sources together."""
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(primary_key=True)
    taxon_id: Mapped[int | None] = mapped_column(ForeignKey("taxa.id"), index=True)

    scientific_name: Mapped[str] = mapped_column(String(255), index=True, unique=True)
    common_name: Mapped[str | None] = mapped_column(String(255))
    accepted_name: Mapped[str | None] = mapped_column(String(255))

    # --- the glue: external identifiers, never join on names ---
    col_taxon_id: Mapped[str | None] = mapped_column(String(100), index=True)
    gbif_taxon_id: Mapped[int | None] = mapped_column(index=True)
    ott_id: Mapped[int | None] = mapped_column(index=True)  # Open Tree of Life

    # --- conservation (nullable; do NOT cache+redistribute raw IUCN data,
    #     populate this live at request time or from Wikidata P141 instead) ---
    iucn_category: Mapped[str | None] = mapped_column(String(10))  # LC/NT/VU/EN/CR...
    iucn_assessment_year: Mapped[int | None] = mapped_column()

    occurrence_count: Mapped[int | None] = mapped_column()

    taxon = relationship("Taxon")


class PhylogenyEdge(Base):
    """Evolutionary relationship, stored separately from taxonomic hierarchy."""
    __tablename__ = "phylogeny_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id"), index=True
    )
    child_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id"), index=True
    )
    source: Mapped[str | None] = mapped_column(String(100))


class Occurrence(Base):
    """A single GBIF observation point. Start capped; don't dump millions in V1."""
    __tablename__ = "occurrences"

    id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()
    event_date: Mapped[date | None] = mapped_column(Date)
    basis_of_record: Mapped[str | None] = mapped_column(String(100))
    dataset: Mapped[str | None] = mapped_column(String(255))
    gbif_id: Mapped[int | None] = mapped_column(index=True)
    license: Mapped[str | None] = mapped_column(String(100))

    species = relationship("Species")

# CAVEAT on phylogeny_edges: modelling edges as species-to-species only works
# for a flat demo. A real induced phylogeny has *internal* nodes (unnamed common
# ancestors) that aren't species. When you outgrow this, add a `phylo_nodes`
# table and point edges at node ids instead of species ids. Fine to defer for V1.