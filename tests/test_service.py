import threading
from pathlib import Path
from advanced_file_finder.core.models import SearchOptions
from advanced_file_finder.core.search_service import search


def test_multiple_paths_and_cancellation(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "first.txt").write_text("")
    (two / "second.txt").write_text("")
    results, stats = search(SearchOptions(".txt", (one, two)))
    assert {x.name for x in results} == {"first.txt", "second.txt"}
    assert stats.files_scanned == 2
    event = threading.Event()
    event.set()
    results, _ = search(SearchOptions(".txt", (one, two)), event)
    assert results == []
