from pathlib import Path

from advanced_file_finder.core.models import MatchMode, SearchOptions, SearchStats
from advanced_file_finder.core.scanner import scan_path


def opts(root: Path, query: str) -> SearchOptions:
    return SearchOptions(query=query, search_paths=(root,), match_mode=MatchMode.PARTIAL)


def test_scans_nested_and_unicode(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "报告.txt").write_text("ok", encoding="utf-8")
    stats = SearchStats()
    results = scan_path(tmp_path, opts(tmp_path, "报告"), stats)
    assert [item.name for item in results] == ["报告.txt"]
    assert stats.files_scanned == 1
    assert stats.directories_scanned == 2


def test_exact_and_missing_path(tmp_path: Path) -> None:
    (tmp_path / "alpha.py").write_text("", encoding="utf-8")
    exact = SearchOptions("alpha.py", (tmp_path,), MatchMode.EXACT)
    assert len(scan_path(tmp_path, exact, SearchStats())) == 1
    stats = SearchStats()
    assert scan_path(tmp_path / "missing", opts(tmp_path, "x"), stats) == []
    assert stats.errors == 1