"""Adapter around pbixray, isolating the rest of the package from its API."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pbixray import PBIXRay


class PBIXModel:
    def __init__(self, pbix_path: str | Path):
        self.path = Path(pbix_path)
        self._ray = PBIXRay(str(self.path))

    def queries(self) -> dict[str, str]:
        """Power Query tables + M parameters (often staging steps in layered models)."""
        queries: dict[str, str] = {}
        for _, row in self._ray.power_query.iterrows():
            queries[str(row["TableName"])] = str(row["Expression"])
        for _, row in self._ray.m_parameters.iterrows():
            queries[str(row["ParameterName"])] = str(row["Expression"])
        return queries

    def schema_columns(self) -> pd.DataFrame:
        return self._ray.schema[["TableName", "ColumnName"]]

    def calculated_columns(self) -> pd.DataFrame:
        return self._ray.dax_columns

    def measures(self) -> pd.DataFrame:
        return self._ray.dax_measures

    def relationships(self) -> pd.DataFrame:
        return self._ray.relationships
