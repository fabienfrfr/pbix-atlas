"""Parser for the Report/Layout part of a .pbix file.

Isolates the internal, undocumented Power BI Desktop format from the rest of
the package.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable
from pathlib import Path

from .models import VisualFieldUsage


class ReportLayoutParser:
    _FIELD_KEYS = ("Column", "Measure", "HierarchyLevel", "Percentile")

    def load_raw_layout(self, pbix_path: str | Path) -> dict:
        with zipfile.ZipFile(pbix_path, "r") as z:
            raw = z.read("Report/Layout")
        text = raw.decode("utf-16-le", errors="ignore").lstrip("\ufeff")
        return json.loads(text)

    def iter_visual_fields(self, layout: dict) -> Iterable[VisualFieldUsage]:
        for section in layout.get("sections", []):
            page = section.get("displayName") or section.get("name", "")
            for idx, vc in enumerate(section.get("visualContainers", [])):
                try:
                    config = json.loads(vc.get("config", "{}"))
                except json.JSONDecodeError:
                    continue

                single_visual = config.get("singleVisual")
                if not single_visual:
                    continue  # e.g. a visualGroup container, nothing to extract here

                visual_type = single_visual.get("visualType", "unknown")
                proto_query = single_visual.get("prototypeQuery", {})
                alias_to_entity = {f.get("Name"): f.get("Entity") for f in proto_query.get("From", [])}

                for item in proto_query.get("Select", []):
                    kind, table, field = self._resolve_select_item(item, alias_to_entity)
                    yield VisualFieldUsage(
                        page=page,
                        visual_index=idx,
                        visual_type=visual_type,
                        field_kind=kind,
                        table=table,
                        field=field,
                    )

    def _resolve_select_item(self, item: dict, alias_to_entity: dict[str, str]) -> tuple[str, str | None, str]:
        node = item
        for _ in range(3):  # bounded nesting depth (Aggregation/HierarchyLevel)
            if "Aggregation" in node:
                node = node["Aggregation"].get("Expression", {})
                continue
            break

        for key in self._FIELD_KEYS:
            if key in node:
                inner = node[key]
                alias = inner.get("Expression", {}).get("SourceRef", {}).get("Source")
                entity = alias_to_entity.get(alias)
                return key, entity, inner.get("Property", item.get("Name", "?"))

        return "Unresolved", None, item.get("Name", str(item)[:120])
