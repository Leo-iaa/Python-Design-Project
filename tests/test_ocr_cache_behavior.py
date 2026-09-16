from pathlib import Path

from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.core.ocr.indexer import index_images


class CountingEngine:
    def __init__(self):
        self.calls = 0

    def recognize(self, _: Path) -> OcrResult:
        self.calls += 1
        return OcrResult("cached", 0.8)


def test_cache_hit_skips_engine_and_deleted_rows_are_pruned(tmp_path: Path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"a")
    cache = OcrCache(tmp_path / "db.sqlite")
    engine = CountingEngine()
    index_images((tmp_path,), cache, engine)
    index_images((tmp_path,), cache, engine)
    assert engine.calls == 1
    image.unlink()
    assert cache.prune_missing() == 1
    assert cache.search("cached", (tmp_path,)) == []


def test_failed_status_is_not_retried_when_unchanged(tmp_path: Path) -> None:
    image = tmp_path / "bad.png"
    image.write_bytes(b"x")
    cache = OcrCache(tmp_path / "db.sqlite")

    class Broken:
        calls = 0

        def recognize(self, _: Path) -> OcrResult:
            self.calls += 1
            raise RuntimeError("bad")

    engine = Broken()
    index_images((tmp_path,), cache, engine)
    index_images((tmp_path,), cache, engine)
    assert engine.calls == 1


def test_metadata_snapshot_and_batch_upsert(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"1")
    second.write_bytes(b"22")
    cache = OcrCache(tmp_path / "db.sqlite")
    written = cache.upsert_many(
        [
            (first, OcrResult("one"), "indexed", ""),
            (second, OcrResult("two"), "failed", "mock"),
        ]
    )
    assert written == 2
    snapshot = cache.metadata_snapshot()
    assert snapshot[str(first)][2] == "indexed"
    assert snapshot[str(second)][2] == "failed"