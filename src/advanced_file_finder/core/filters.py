"""Composable, user-friendly file metadata filters."""

from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import SearchOptions


def normalize_extensions(value: str) -> tuple[str, ...]:
    """Normalize ``pdf,.docx`` style input into lowercase dotted extensions."""
    return tuple(
        f".{part.strip().lstrip('.').casefold()}" for part in value.split(",") if part.strip()
    )


def is_hidden(path: Path) -> bool:
    """Treat dot-prefixed paths as hidden on all supported systems."""
    return path.name.startswith(".")


def allows(path: Path, size: int, modified: datetime, options: SearchOptions) -> bool:
    """Return whether a candidate whose metadata is available passes all filters."""
    if options.extensions and path.suffix.casefold() not in options.extensions:
        return False
    if options.min_size is not None and size < options.min_size:
        return False
    if options.max_size is not None and size > options.max_size:
        return False
    if options.modified_after and modified < options.modified_after:
        return False
    if options.modified_before and modified > options.modified_before:
        return False
    return options.include_hidden or not is_hidden(path)
