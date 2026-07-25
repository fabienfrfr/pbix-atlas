"""Physical source detection in Power Query (M) expressions.

Detection relies only on the names of native M functions (Power Query's
public API), never on a specific domain name or vendor system. Supporting a
new source type means adding an entry to DEFAULT_PATTERNS, not a new class.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol
from urllib.parse import urlparse

from .models import SourceRef


class SourceDetector(Protocol):
    def detect(self, expression: str) -> list[SourceRef]:
        ...


class MFunctionSourceDetector:
    """Detects sources via native M function calls."""

    DEFAULT_PATTERNS: dict[str, str] = {
        "http": r'Web\.Contents\(\s*"([^"]+)"',
        "odata": r'OData\.Feed\(\s*"([^"]+)"',
        "sql": r'Sql\.Databases?\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "postgresql": r'PostgreSQL\.Database\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "mysql": r'MySQL\.Database\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "odbc": r'Odbc\.DataSource\(\s*"([^"]+)"',
        "folder": r'Folder\.Files\(\s*"([^"]+)"',
        "sharepoint": r'SharePoint\.(?:Files|Contents)\(\s*"([^"]+)"',
        "excel_file": r'Excel\.Workbook\(\s*File\.Contents\(\s*"([^"]+)"',
        "analysis_services": r'AnalysisServices\.Database\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?',
        "azure_blob": r'AzureStorage\.Blobs\(\s*"([^"]+)"',
    }

    def __init__(self, patterns: Optional[dict[str, str]] = None):
        self._compiled = {
            system: re.compile(pattern)
            for system, pattern in (patterns or self.DEFAULT_PATTERNS).items()
        }

    def detect(self, expression: str) -> list[SourceRef]:
        found = []
        for system, pattern in self._compiled.items():
            for m in pattern.finditer(expression):
                groups = [g for g in m.groups() if g]
                identifier = "/".join(groups) if groups else m.group(0)
                found.append(SourceRef(system=system, identifier=identifier, raw_match=m.group(0)))
        return found


class LiteralUrlFallbackDetector:
    """Catches a bare literal URL, e.g. an M parameter holding just a string."""

    _URL = re.compile(r'"(https?://[^"\s]+)"')

    def detect(self, expression: str) -> list[SourceRef]:
        return [
            SourceRef(system="http", identifier=m.group(1), raw_match=m.group(0))
            for m in self._URL.finditer(expression)
        ]


class SourceDetectorRegistry:
    """Aggregates detectors and deduplicates results."""

    def __init__(self, detectors: Optional[list[SourceDetector]] = None):
        self._detectors = detectors or [MFunctionSourceDetector(), LiteralUrlFallbackDetector()]

    def detect(self, expression: str) -> list[SourceRef]:
        seen: set[tuple[str, str]] = set()
        out: list[SourceRef] = []
        for detector in self._detectors:
            for ref in detector.detect(expression):
                key = (ref.system, ref.identifier)
                if key not in seen:
                    seen.add(key)
                    out.append(ref)
        return out


def normalize_source_identifier(ref: SourceRef) -> str:
    """Stable node identifier, e.g. host+path without a noisy query string."""
    if ref.system in {"http", "odata"} and ref.identifier.startswith("http"):
        parsed = urlparse(ref.identifier)
        return f"{parsed.netloc}{parsed.path}"
    return ref.identifier
