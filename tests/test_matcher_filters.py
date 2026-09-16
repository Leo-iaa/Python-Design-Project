from datetime import datetime, timedelta
from pathlib import Path

import pytest

from advanced_file_finder.core.filters import allows, normalize_extensions
from advanced_file_finder.core.matcher import build_matcher
from advanced_file_finder.core.models import MatchMode, SearchOptions


def test_modes_and_bad_regex() -> None:
    assert build_matcher("*.PY", MatchMode.GLOB)("a.py")
    assert build_matcher(r"^a.+txt$", MatchMode.REGEX)("a!txt")
    with pytest.raises(ValueError):
        build_matcher("[", MatchMode.REGEX)


def test_filters() -> None:
    now = datetime.now()
    path = Path("report.PDF")
    options = SearchOptions(
        "",
        (Path("."),),
        extensions=normalize_extensions("pdf"),
        min_size=2,
        max_size=4,
        modified_after=now - timedelta(days=1),
    )
    assert allows(path, 3, now, options)
    assert not allows(path, 1, now, options)
