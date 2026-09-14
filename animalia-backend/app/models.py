"""ORM tables — single source of truth for the database schema."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Taxon(Base):
    __tablename__ = "taxa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("taxa.id"), nullable=True, index=True
    )
    scientific_name: Mapped[str] = mapped_column(String(255), index=True)
    rank: Mapped[str] = mapped_column(String(64), index=True)
    col_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    ott_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    gbif_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    parent: Mapped["Taxon | None"] = relationship(
        "Taxon", remote_side="Taxon.id", back_populates="children"
    )
    children: Mapped[list["Taxon"]] = relationship("Taxon", back_populates="parent")
    species: Mapped["Species | None"] = relationship(
        "Species", back_populates="taxon", uselist=False
    )


class Species(Base):
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxon_id: Mapped[int] = mapped_column(
        ForeignKey("taxa.id"), unique=True, index=True
    )
    common_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorship: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iucn_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    taxon: Mapped[Taxon] = relationship("Taxon", back_populates="species")
