from pathlib import Path

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
