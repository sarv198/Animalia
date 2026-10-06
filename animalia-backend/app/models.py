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
  - `phylo_nodes` + `phylogeny_edges` = evolutionary relationships, kept
              SEPARATE from taxonomy because the two are not the same thing.
              Nodes include unnamed common ancestors and extinct groups, so
              edges point at nodes, not at species.
  - `sources` = provenance, so every value can be traced to a dataset version.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, false, func
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
    iucn_source: Mapped[str | None] = mapped_column(Text)  # e.g. "Wikipedia infobox (IUCN3.1) ..."
    wikipedia_url: Mapped[str | None] = mapped_column(Text)

    occurrence_count: Mapped[int | None] = mapped_column()

    taxon = relationship("Taxon")
    media = relationship(
        "SpeciesMedia", order_by="SpeciesMedia.position", cascade="all, delete-orphan"
    )


class SpeciesMedia(Base):
    """An openly licensed image of a species, linked (not copied) with its credit."""
    __tablename__ = "species_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"), index=True)
    position: Mapped[int] = mapped_column()  # display order
    source: Mapped[str] = mapped_column(String(50))  # Wikimedia Commons | GBIF
    image_url: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text)  # where the credit can be checked
    licence: Mapped[str] = mapped_column(String(50))
    licence_url: Mapped[str | None] = mapped_column(Text)
    creator: Mapped[str | None] = mapped_column(Text)


class PhyloNode(Base):
    """A node of the phylogeny: a family tip, a collapsed group, or an ancestor.

    Family tips carry the representative species and how confident we are that
    the species stands for its whole family (`placement_status`). Collapsed
    groups (pterosaurs, birds, ...) are drawn as one tip without families.
    """
    __tablename__ = "phylo_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str | None] = mapped_column(String(100), index=True)  # ott123 / mrcaott1ott2
    label: Mapped[str | None] = mapped_column(String(255))
    is_tip: Mapped[bool] = mapped_column(Boolean, server_default=false())

    # --- family tips only ---
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"), index=True)
    family_taxon_id: Mapped[int | None] = mapped_column(ForeignKey("taxa.id"), index=True)
    family_ott_id: Mapped[int | None] = mapped_column()
    placement_status: Mapped[str | None] = mapped_column(String(20))  # confirmed | flagged | unknown

    # --- curated annotations ---
    extinct: Mapped[bool] = mapped_column(Boolean, server_default=false())
    collapsed_group: Mapped[bool] = mapped_column(Boolean, server_default=false())
    placement_uncertain: Mapped[bool] = mapped_column(Boolean, server_default=false())
    anapsid_skull: Mapped[bool] = mapped_column(Boolean, server_default=false())
    note: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text)

    # --- divergence times (etl/transform/date_phylogeny.py) ---
    # age_ma: when this node lived, in millions of years ago. Tips: 0 if living,
    # last fossil if extinct. age_source says where it came from: present |
    # last appearance | fossil minimum | TimeTree 5 | interpolated.
    age_ma: Mapped[float | None] = mapped_column()
    age_ci_low: Mapped[float | None] = mapped_column()
    age_ci_high: Mapped[float | None] = mapped_column()
    age_source: Mapped[str | None] = mapped_column(String(100))
    age_citation: Mapped[str | None] = mapped_column(Text)
    age_study_count: Mapped[int | None] = mapped_column()  # TimeTree studies behind the estimate
    age_adjusted: Mapped[bool] = mapped_column(Boolean, server_default=false())
    age_unadjusted_ma: Mapped[float | None] = mapped_column()  # estimate before adjustment
    first_appearance_ma: Mapped[float | None] = mapped_column()
    last_appearance_ma: Mapped[float | None] = mapped_column()

    source = relationship("Source")
    species = relationship("Species")
    family_taxon = relationship("Taxon")


class PhylogenyEdge(Base):
    """Parent -> child link between phylo_nodes. A child has exactly one parent."""
    __tablename__ = "phylogeny_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_node_id: Mapped[int] = mapped_column(
        ForeignKey("phylo_nodes.id"), index=True
    )
    child_node_id: Mapped[int] = mapped_column(
        ForeignKey("phylo_nodes.id"), index=True, unique=True
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