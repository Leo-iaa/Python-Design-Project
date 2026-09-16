"""Typed values exchanged by the core search services."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class MatchMode(StrEnum):
    EXACT = "exact"
    PARTIAL = "partial"
    GLOB = "glob"
    REGEX = "regex"


@dataclass(frozen=True, slots=True)
class SearchOptions:
    query: str
    search_paths: tuple[Path, ...]
    match_mode: MatchMode = MatchMode.PARTIAL
    case_sensitive: bool = False
    extensions: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    include_hidden: bool = False
    include_hidden_directories: bool = False
    excluded_directories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchResult:
    name: str
    full_path: Path
    parent_path: Path
    extension: str
    size: int
    modified_time: datetime


@dataclass(slots=True)
class SearchStats:
    files_scanned: int = 0
    directories_scanned: int = 0
    matches: int = 0
    permission_denied: int = 0
    errors: int = 0
    elapsed_time: float = 0.0
    error_messages: list[str] = field(default_factory=list)