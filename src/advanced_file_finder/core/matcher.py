"""Filename matching independent of filesystem traversal."""
from advanced_file_finder.core.models import MatchMode


def matches(name: str, query: str, mode: MatchMode, case_sensitive: bool = False) -> bool:
    """Return whether *name* matches a basic exact or partial query."""
    candidate, needle = (name, query) if case_sensitive else (name.casefold(), query.casefold())
    if mode is MatchMode.EXACT:
        return candidate == needle
    if mode is MatchMode.PARTIAL:
        return needle in candidate
    raise ValueError(f"Unsupported match mode: {mode}")