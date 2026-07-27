"""Extraction of Table[Field] / 'Table'[Field] / [Field] references from DAX."""

from __future__ import annotations

import re

from .models import DaxReference


class DaxReferenceParser:
    _REF = re.compile(r"(?:'([^']+)'|\b([A-Za-z_][A-Za-z0-9_]*)\b)?\[([^\[\]]+)\]")

    def parse(self, expression: str) -> list[DaxReference]:
        if not expression:
            return []
        return [DaxReference(table=m.group(1) or m.group(2), name=m.group(3)) for m in self._REF.finditer(expression)]
