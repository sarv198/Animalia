"""JSON shapes for taxonomy tree responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class TreeNode(BaseModel):
    """One node in the nested classification tree."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rank: str
    children: list[TreeNode] = []

    @model_validator(mode="before")
    @classmethod
    def _from_taxon(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "name": getattr(data, "name", None) or data.scientific_name,
            "rank": data.rank,
            "children": list(getattr(data, "children", None) or []),
        }


TreeNode.model_rebuild()
