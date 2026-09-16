from pathlib import Path

from advanced_file_finder.core.models import OcrProgress
from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.core.ocr.indexer import index_images


class MockEngine:
    def recognize(self, image_path: Path) -> OcrResult:
        return OcrResult("中文潜热 OCR text", 0.9, "mock")


def test_cache_hit_and_invalidation(tmp_path: Path) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"x")
    cache = OcrCache(tmp_path / "ocr.sqlite")
    index_images((tmp_path,), cache, MockEngine())
    assert cache.get(image).text.startswith("中文")
    first = cache.get(image)
    image.write_bytes(b"changed")
    assert cache.get(image) is None
    index_images((tmp_path,), cache, MockEngine())
    assert cache.get(image).text == first.text
    assert cache.search("潜热", (tmp_path,))[0].match_source == "ocr"


def test_failed_engine_is_recorded(tmp_path: Path) -> None:
    image = tmp_path / "bad.jpg"
    image.write_bytes(b"x")
    cache = OcrCache(tmp_path / "ocr.sqlite")

    class Broken:
        def recognize(self, _: Path) -> OcrResult:
            raise RuntimeError("broken")

    assert index_images((tmp_path,), cache, Broken()) == (0, 1)


def test_detailed_progress_reports_cache_and_eta(tmp_path: Path) -> None:
    for name in ("a.png", "b.png", "c.png"):
        (tmp_path / name).write_bytes(name.encode())
    cache = OcrCache(tmp_path / "ocr.sqlite")
    progress: list[OcrProgress] = []
    index_images((tmp_path,), cache, MockEngine(), detailed_progress=progress.append)
    assert progress[-1].discovered == 3
    assert progress[-1].needs_ocr == 3
    assert progress[-1].ocr_completed == 3
    assert progress[-1].current_filename == "c.png"
    assert progress[-1].average_ocr_seconds >= 0
    progress.clear()
    index_images((tmp_path,), cache, MockEngine(), detailed_progress=progress.append)
    assert progress[-1].cache_hits == 3
    assert progress[-1].ocr_completed == 0