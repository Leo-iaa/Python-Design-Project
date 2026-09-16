from pathlib import Path

from advanced_file_finder.core.models import SearchOptions
from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.core.search_service import search


def test_ocr_only_search_merges_cached_result(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "IMG_1.png"
    image.write_bytes(b"x")
    cache = OcrCache(tmp_path / "ocr.sqlite")
    cache.upsert(image, OcrResult("潜热影响", 0.9))
    monkeypatch.setattr("advanced_file_finder.core.search_service._ocr_cache", lambda: cache)
    results, stats = search(
        SearchOptions("潜热", (tmp_path,), search_filename=False, search_ocr=True)
    )
    assert results[0].match_source == "ocr" and stats.matches == 1
