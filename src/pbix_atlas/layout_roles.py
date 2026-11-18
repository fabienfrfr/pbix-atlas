"""Extended extraction from Report/Layout: field *roles* (axis/legend/...),
per-visual and per-page filters, and sort order - beyond the base
column/measure usage already handled by `layout.py`.

Kept as a separate module so `layout.py` (which the lineage graph depends on)
stays minimal; this one is consumed only by the code generator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

_FIELD_KEYS = ("Column", "Measure", "HierarchyLevel", "Percentile")

# Power BI's own chart-type vocabulary -> a small, stable set our generator understands.
VISUAL_TYPE_MAP: dict[str, str] = {
    "columnChart": "bar",
    "clusteredColumnChart": "bar",
    "stackedColumnChart": "bar",
    "barChart": "bar_h",
    "clusteredBarChart": "bar_h",
    "stackedBarChart": "bar_h",
    "lineChart": "line",
    "lineStackedColumnComboChart": "line",
    "areaChart": "area",
    "pieChart": "pie",
    "donutChart": "pie",
    "scatterChart": "scatter",
    "tableEx": "table",
    "table": "table",
    "pivotTable": "table",
    "card": "kpi",
    "multiRowCard": "kpi",
    "slicer": "filter",
    "gauge": "gauge",
    "treemap": "treemap",
}


@dataclass
class VisualSpec:
    """VisualSpec (see attributes/methods below)."""

    page: str
    visual_index: int
    visual_type: str
    generic_type: str | None  # entry from VISUAL_TYPE_MAP, or None if unmapped
    # role -> list of (table, field, field_kind)
    roles: dict[str, list[tuple[str | None, str, str]]] = field(default_factory=dict)
    filters: list[dict] = field(default_factory=list)


@dataclass
class PageFilters:
    """PageFilters (see attributes/methods below)."""

    page: str
    filters: list[dict] = field(default_factory=list)


def _resolve_item(item: dict, alias_to_entity: dict[str, str]) -> tuple[str, str | None, str]:
    node = item
    for _ in range(3):
        if "Aggregation" in node:
            node = node["Aggregation"].get("Expression", {})
            continue
        break
    for key in _FIELD_KEYS:
        if key in node:
            inner = node[key]
            alias = inner.get("Expression", {}).get("SourceRef", {}).get("Source")
            entity = alias_to_entity.get(alias)
            return key, entity, inner.get("Property", item.get("Name", "?"))
    return "Unresolved", None, item.get("Name", "?")


def _parse_filter_blob(raw) -> dict | None:
    """A filters entry is either a JSON string or already a dict, depending on
    the Power BI Desktop version that wrote the file."""
    try:
        blob = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(blob, dict):
        return None
    expr = blob.get("expression", {})
    table, field_name = None, None
    for key in _FIELD_KEYS:
        if key in expr:
            table = expr[key].get("Expression", {}).get("SourceRef", {}).get("Entity")
            field_name = expr[key].get("Property")
            break
    return {
        "table": table,
        "field": field_name,
        "filter_type": blob.get("type"),
        "how_created": blob.get("howCreated"),
    }


def extract_visual_specs(layout: dict) -> list[VisualSpec]:
    """Extract visual specs. Takes `layout`."""
    specs: list[VisualSpec] = []
    for section in layout.get("sections", []):
        page = section.get("displayName") or section.get("name", "")
        page_filters = [f for raw in section.get("filters", []) if (f := _parse_filter_blob(raw))]

        for idx, vc in enumerate(section.get("visualContainers", [])):
            try:
                cfg = json.loads(vc.get("config", "{}"))
            except json.JSONDecodeError:
                continue
            sv = cfg.get("singleVisual")
            if not sv:
                continue

            visual_type = sv.get("visualType", "unknown")
            proto = sv.get("prototypeQuery", {})
            alias_to_entity = {f.get("Name"): f.get("Entity") for f in proto.get("From", [])}

            # queryRef -> (kind, table, field), so projections can be matched back
            queryref_to_field: dict[str, tuple[str, str | None, str]] = {}
            for item in proto.get("Select", []):
                kind, table, field_name = _resolve_item(item, alias_to_entity)
                queryref_to_field[item.get("Name", "")] = (kind, table, field_name)

            roles: dict[str, list[tuple[str | None, str, str]]] = {}
            for role, entries in sv.get("projections", {}).items():
                for entry in entries:
                    qref = entry.get("queryRef", "")
                    kind, table, field_name = queryref_to_field.get(qref, ("Unresolved", None, qref))
                    roles.setdefault(role, []).append((table, field_name, kind))

            visual_filters = [f for raw in vc.get("filters", []) if (f := _parse_filter_blob(raw))]

            specs.append(
                VisualSpec(
                    page=page,
                    visual_index=idx,
                    visual_type=visual_type,
                    generic_type=VISUAL_TYPE_MAP.get(visual_type),
                    roles=roles,
                    filters=page_filters + visual_filters,
                )
            )
    return specs
