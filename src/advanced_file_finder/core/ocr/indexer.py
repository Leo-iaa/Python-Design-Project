"""Cancellable background-friendly image indexing routine."""

import threading
from collections.abc import Callable
from pathlib import Path

from advanced_file_finder.core.ocr.cache import IMAGE_EXTENSIONS, OcrCache
from advanced_file_finder.core.ocr.engine import OcrEngine, OcrResult


def index_images(
    roots: tuple[Path, ...],
    cache: OcrCache,
    engine: OcrEngine,
    cancel: threading.Event | None = None,
    progress: Callable[[int, int, int, int], None] | None = None,
) -> tuple[int, int]:
    """Index changed images and retain successful rows when cancelled."""
    files = [
        p
        for root in roots
        if root.is_dir()
        for p in root.rglob("*")
        if p.is_file() and p.suffix.casefold() in IMAGE_EXTENSIONS
    ]
    success = failed = 0
    for current, path in enumerate(files, 1):
        if cancel and cancel.is_set():
            break
        if cache.is_current(path):
            success += 1
            if progress:
                progress(current, len(files), success, failed)
            continue
        try:
            cache.upsert(path, engine.recognize(path))
            success += 1
        except (OSError, ValueError, RuntimeError) as error:
            cache.upsert(path, OcrResult("", 0.0), "failed", str(error))
            failed += 1
        if progress:
            progress(current, len(files), success, failed)
    return success, failed
