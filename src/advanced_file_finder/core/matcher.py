"""Compiled filename matching independent of filesystem traversal."""

import fnmatch
import re
from collections.abc import Callable

from advanced_file_finder.core.models import MatchMode


def build_matcher(
    query: str, mode: MatchMode, case_sensitive: bool = False
) -> Callable[[str], bool]:
    """Build a reusable matcher; invalid regular expressions raise ``ValueError``."""
    flags = 0 if case_sensitive else re.IGNORECASE
    if mode is MatchMode.REGEX:
        try:
            pattern = re.compile(query, flags)
        except re.error as error:
            raise ValueError(f"Invalid regular expression: {error}") from error
        return lambda name: bool(pattern.search(name))
    needle = query if case_sensitive else query.casefold()
    if mode is MatchMode.GLOB:
        return lambda name: fnmatch.fnmatchcase(name if case_sensitive else name.casefold(), needle)
    if mode is MatchMode.EXACT:
        return lambda name: (name if case_sensitive else name.casefold()) == needle
    return lambda name: needle in (name if case_sensitive else name.casefold())


def matches(name: str, query: str, mode: MatchMode, case_sensitive: bool = False) -> bool:
    """Compatibility helper for an individual filename."""
    return build_matcher(query, mode, case_sensitive)(name)
