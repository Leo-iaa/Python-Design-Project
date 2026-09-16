"""Filename matching and normalized relevance scoring."""

import fnmatch
import re
from collections.abc import Callable
from pathlib import Path

from rapidfuzz.fuzz import WRatio

from advanced_file_finder.core.models import MatchMode


def _text(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.casefold()


def build_matcher(
    query: str, mode: MatchMode, case_sensitive: bool = False
) -> Callable[[str], bool]:
    """Build a reusable matcher; invalid regular expressions raise ``ValueError``."""
    needle = _text(query, case_sensitive)
    if mode is MatchMode.REGEX:
        try:
            pattern = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"Invalid regular expression: {error}") from error
        return lambda name: bool(pattern.search(name))
    if mode is MatchMode.GLOB:
        return lambda name: fnmatch.fnmatchcase(_text(name, case_sensitive), needle)
    if mode is MatchMode.FUZZY:
        return lambda name: match_score(name, query, mode, case_sensitive)[0]
    if mode is MatchMode.EXACT:
        return lambda name: _text(name, case_sensitive) == needle
    return lambda name: needle in _text(name, case_sensitive)


def match_score(
    name: str, query: str, mode: MatchMode, case_sensitive: bool = False, threshold: int = 75
) -> tuple[bool, float, str]:
    """Return match status, score from 0-100, and a reason for ranking."""
    candidate = _text(name, case_sensitive)
    needle = _text(query, case_sensitive)
    if mode is MatchMode.FUZZY:
        value = name if "." not in query else Path(name).name
        stem = Path(value).stem if "." not in query else value
        score = float(WRatio(_text(stem, case_sensitive), needle))
        return score >= threshold, score, f"fuzzy {score:.0f}"
    matched = build_matcher(query, mode, case_sensitive)(name)
    if not matched:
        return False, 0.0, ""
    if mode is MatchMode.EXACT:
        return True, 100.0, "exact filename"
    if mode is MatchMode.PARTIAL and _text(Path(name).stem, case_sensitive) == needle:
        return True, 98.0, "stem exact"
    if candidate.startswith(needle):
        return True, 94.0, "filename prefix"
    if mode is MatchMode.PARTIAL:
        return True, 82.0, "filename partial"
    return True, 80.0, f"{mode.value} match"
