from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.exporter import export_results
from advanced_file_finder.core.models import SearchResult


def test_export_formats(tmp_path: Path) -> None:
    result = SearchResult("中文.txt", tmp_path / "中文.txt", tmp_path, ".txt", 1, datetime.now())
    for suffix in ("csv", "json", "txt"):
        target = tmp_path / f"out.{suffix}"
        export_results([result], target, suffix)
        assert target.exists() and target.stat().st_size
    assert (tmp_path / "out.csv").read_bytes().startswith(b"\xef\xbb\xbf")
