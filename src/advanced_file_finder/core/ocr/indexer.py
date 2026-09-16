"""Cancellable background-friendly image indexing routine."""

import os
import threading
from collections.abc import Callable
from pathlib import Path

from advanced_file_finder.core.filters import filter_directories
from advanced_file_finder.core.ocr.cache import IMAGE_EXTENSIONS, OcrCache
from advanced_file_finder.core.ocr.engine import OcrEngine, OcrResult


def index_images(
    roots: tuple[Path, ...],
    cache: OcrCache,
    engine: OcrEngine,
    cancel: threading.Event | None = None,
    progress: Callable[[int, int, int, int], None] | None = None,
    state: Callable[[str], None] | None = None,
    excluded_directories: tuple[str, ...] = (),
) -> tuple[int, int]:
    """Index changed images and retain successful rows when cancelled."""
    if state:
        state("initializing")
    files: list[Path] = []
    if state:
        state("enumerating")
    for root in roots:
        if cancel and cancel.is_set():
            return 0, 0
        if not root.is_dir():
            continue
        for directory, directories, names in os.walk(root):
            directories[:] = filter_directories(directories, excluded_directories)
            if cancel and cancel.is_set():
                return 0, 0
            for name in names:
                if cancel and cancel.is_set():
                    return 0, 0
                path = Path(directory) / name
                if path.suffix.casefold() in IMAGE_EXTENSIONS:
                    files.append(path)
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
