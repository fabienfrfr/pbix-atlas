"""Shared data model: node/edge types and small value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NodeType(str, Enum):
    """NodeType (see attributes/methods below)."""

    SOURCE = "source"
    QUERY = "query"
    COLUMN = "column"
    CALCULATED_COLUMN = "calculated_column"
    MEASURE = "measure"
    VISUAL_FIELD = "visual_field"
    UNRESOLVED = "unresolved"


class EdgeType(str, Enum):
    """EdgeType (see attributes/methods below)."""

    FEEDS = "feeds"  # source -> query, query -> query, query -> column
    DERIVES_FROM = "derives_from"  # calculated column / measure depends on another node
    RELATES_TO = "relates_to"  # model relationship (join)
    DISPLAYED_IN = "displayed_in"  # column/measure -> visual field


@dataclass(frozen=True)
class SourceRef:
    """SourceRef (see attributes/methods below)."""

    system: str  # "http", "odata", "sql", "folder", "excel_file", ...
    identifier: str
    raw_match: str


@dataclass(frozen=True)
class DaxReference:
    """DaxReference (see attributes/methods below)."""

    table: str | None  # None for an unqualified reference, e.g. [MyMeasure]
    name: str


@dataclass(frozen=True)
class VisualFieldUsage:
    """VisualFieldUsage (see attributes/methods below)."""

    page: str
    visual_index: int
    visual_type: str
    field_kind: str  # "Column" | "Measure" | "HierarchyLevel" | "Percentile" | "Unresolved"
    table: str | None
    field: str


def node_id(node_type: NodeType, *parts: str) -> str:
    """Node id. Takes `node_type`."""
    return f"{node_type.value}::" + "::".join(parts)
