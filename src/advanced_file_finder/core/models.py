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
    FUZZY = "fuzzy"


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
    fuzzy_threshold: int = 75
    search_filename: bool = True
    search_ocr: bool = False


@dataclass(frozen=True, slots=True)
class SearchResult:
    name: str
    full_path: Path
    parent_path: Path
    extension: str
    size: int
    modified_time: datetime
    match_score: float = 0.0
    match_source: str = "filename"
    match_reason: str = ""
    ocr_excerpt: str = ""


@dataclass(frozen=True, slots=True)
class OcrProgress:
    """Detailed OCR indexing progress for GUI and telemetry."""

    current: int = 0
    discovered: int = 0
    cache_hits: int = 0
    needs_ocr: int = 0
    ocr_completed: int = 0
    success: int = 0
    failed: int = 0
    current_filename: str = ""
    current_size_bytes: int = 0
    last_duration_seconds: float = 0.0
    average_ocr_seconds: float = 0.0
    images_per_second: float = 0.0
    eta_seconds: float | None = None


@dataclass(slots=True)
class SearchStats:
    files_scanned: int = 0
    directories_scanned: int = 0
    matches: int = 0
    permission_denied: int = 0
    errors: int = 0
    elapsed_time: float = 0.0
    error_messages: list[str] = field(default_factory=list)