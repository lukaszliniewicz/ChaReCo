"""Typed models shared by ChaReCo's GUI and background workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    """Immutable snapshot of the options for one analysis job."""

    source_path: str
    is_local: bool
    include_extensions: tuple[str, ...] = ()
    exclude_extensions: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    include_git: bool = False
    include_license: bool = False
    exclude_readme: bool = False
    concatenate: bool = True
    copy_local_folder: bool = False
    branch: str | None = None
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 20_000_000


@dataclass(slots=True)
class AnalysisResult:
    """Self-contained output from one completed analysis job."""

    full_text: str
    folder_structure: str
    file_positions: dict[str, int]
    file_contents: dict[str, str]
    metadata: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
