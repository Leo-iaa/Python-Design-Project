from pathlib import Path

from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.core.ocr.indexer import estimate_image_count, index_images


class MockOcrEngine:
    def __init__(self):
        self.paths: list[Path] = []

    def recognize(self, image_path: Path) -> OcrResult:
        self.paths.append(image_path)
        return OcrResult("text", 0.9, "mock")


def test_ocr_indexer_prunes_default_runtime_directories(tmp_path: Path) -> None:
    included = tmp_path / "included.png"
    excluded = tmp_path / ".local" / "runtime.png"
    included.write_bytes(b"ok")
    excluded.parent.mkdir()
    excluded.write_bytes(b"no")
    cache = OcrCache(tmp_path / "db.sqlite")
    engine = MockOcrEngine()

    assert index_images((tmp_path,), cache, engine) == (1, 0)
    assert engine.paths == [included]


def test_explicit_ocr_exclusions_override_defaults(tmp_path: Path) -> None:
    git_image = tmp_path / ".git" / "image.png"
    local_image = tmp_path / ".local" / "image.png"
    git_image.parent.mkdir()
    local_image.parent.mkdir()
    git_image.write_bytes(b"git")
    local_image.write_bytes(b"local")
    cache = OcrCache(tmp_path / "db.sqlite")
    engine = MockOcrEngine()

    assert index_images((tmp_path,), cache, engine, excluded_directories=(".local",)) == (1, 0)
    assert engine.paths == [git_image]

def test_estimate_image_count_respects_exclusions(tmp_path: Path) -> None:
    (tmp_path / "kept.png").write_bytes(b"x")
    excluded = tmp_path / ".local"
    excluded.mkdir()
    (excluded / "ignored.png").write_bytes(b"x")
    assert estimate_image_count((tmp_path,)) == 1
    assert estimate_image_count((tmp_path,), (".local",)) == 1