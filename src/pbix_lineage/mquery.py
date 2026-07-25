"""Dependency resolution between Power Query (M) queries."""

from __future__ import annotations

import re


class MQueryDependencyResolver:
    """
    Table-level dependency detection: a query depends on another if the
    other query's name appears as an identifier in its expression.

    Limitation: resolves at table level, not step-by-step within a single
    `let ... in` query.
    """

    def resolve(self, queries: dict[str, str]) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {}
        for name, expr in queries.items():
            deps = {
                candidate
                for candidate in queries
                if candidate != name and re.search(rf"\b{re.escape(candidate)}\b", expr)
            }
            graph[name] = deps
        return graph
