from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import SearchOptions
from advanced_file_finder.core.saved_search import SMART_RANGES, SavedSearch, SavedSearchRepository


def test_saved_crud_and_relative_range(tmp_path: Path) -> None:
    repository = SavedSearchRepository(tmp_path / "saved.json")
    options = SearchOptions("report", (tmp_path,))
    saved = SavedSearch.from_options(
        "Reports", options, time_range_type="relative_days", time_range_value=7
    )
    repository.create(saved)
    assert repository.load()[0].name == "Reports"
    repository.rename(saved.id, "Renamed")
    assert repository.load()[0].name == "Renamed"
    first = saved.to_options(datetime(2026, 1, 10))
    second = saved.to_options(datetime(2026, 2, 10))
    assert first.modified_after != second.modified_after
    repository.delete(saved.id)
    assert repository.load() == []


def test_corrupt_repository_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "saved.json"
    path.write_text("broken", encoding="utf-8")
    assert SavedSearchRepository(path).load() == []
    assert "最近 7 天" in SMART_RANGES
