import threading
from pathlib import Path

from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.core.ocr.indexer import index_images


class MockOcrEngine:
    def __init__(self, cancel_after: int | None = None, cancel: threading.Event | None = None):
        self.calls = 0
        self.cancel_after = cancel_after
        self.cancel = cancel

    def recognize(self, image_path: Path) -> OcrResult:
        self.calls += 1
        if self.cancel_after and self.calls >= self.cancel_after and self.cancel:
            self.cancel.set()
        return OcrResult(f"text-{image_path.name}", 0.9, "mock")


def _images(tmp_path: Path, count: int = 4) -> list[Path]:
    paths = []
    for index in range(count):
        path = tmp_path / f"image-{index}.png"
        path.write_bytes(bytes([index]))
        paths.append(path)
    return paths


def test_cancel_before_start_keeps_cache_empty(tmp_path: Path) -> None:
    _images(tmp_path)
    cache = OcrCache(tmp_path / "ocr.sqlite")
    cancel = threading.Event()
    cancel.set()
    engine = MockOcrEngine(cancel=cancel)

    assert index_images((tmp_path,), cache, engine, cancel) == (0, 0)
    assert engine.calls == 0
    assert cache.stats()[0] == 0


def test_cancel_during_indexing_preserves_current_and_restart_hits_cache(tmp_path: Path) -> None:
    images = _images(tmp_path)
    cache = OcrCache(tmp_path / "ocr.sqlite")
    cancel = threading.Event()
    first_engine = MockOcrEngine(cancel_after=2, cancel=cancel)

    assert index_images((tmp_path,), cache, first_engine, cancel) == (2, 0)
    assert first_engine.calls == 2
    assert cache.get(images[0]) is not None
    assert cache.get(images[1]) is not None
    assert cache.get(images[2]) is None

    cancel.clear()
    second_engine = MockOcrEngine()
    assert index_images((tmp_path,), cache, second_engine, cancel) == (4, 0)
    assert second_engine.calls == 2


def test_cancel_during_enumeration_does_not_dispatch_partial_work(tmp_path: Path, monkeypatch) -> None:
    images = _images(tmp_path, 3)
    cache = OcrCache(tmp_path / "ocr.sqlite")
    cancel = threading.Event()

    def fake_walk(_root):
        yield str(tmp_path), [], [images[0].name]
        cancel.set()
        yield str(tmp_path), [], [images[1].name, images[2].name]

    monkeypatch.setattr("advanced_file_finder.core.ocr.indexer.os.walk", fake_walk)
    engine = MockOcrEngine()
    assert index_images((tmp_path,), cache, engine, cancel) == (0, 0)
    assert engine.calls == 0
    assert cache.stats()[0] == 0


def test_cancel_can_be_requested_twice(tmp_path: Path) -> None:
    _images(tmp_path, 2)
    cache = OcrCache(tmp_path / "ocr.sqlite")
    cancel = threading.Event()
    cancel.set()
    cancel.set()
    assert index_images((tmp_path,), cache, MockOcrEngine(), cancel) == (0, 0)