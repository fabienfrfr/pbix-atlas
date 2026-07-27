from __future__ import annotations

import re
from typing import ClassVar, Protocol
from urllib.parse import urlparse

from .models import SourceRef


class SourceDetector(Protocol):
    def detect(self, expression: str) -> list[SourceRef]: ...


class MFunctionSourceDetector:
    DEFAULT_PATTERNS: ClassVar[dict[str, str]] = {
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

    def __init__(self, patterns: dict[str, str] | None = None):
        self._compiled = {
            system: re.compile(pattern) for system, pattern in (patterns or self.DEFAULT_PATTERNS).items()
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
    _URL = re.compile(r'"(https?://[^"\s]+)"')

    def detect(self, expression: str) -> list[SourceRef]:
        return [
            SourceRef(system="http", identifier=m.group(1), raw_match=m.group(0))
            for m in self._URL.finditer(expression)
        ]


class SourceDetectorRegistry:
    def __init__(self, detectors: list[SourceDetector] | None = None):
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
    if ref.system in {"http", "odata"} and ref.identifier.startswith("http"):
        parsed = urlparse(ref.identifier)
        return f"{parsed.netloc}{parsed.path}"
    return ref.identifier
