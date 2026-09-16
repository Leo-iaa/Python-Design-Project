"""Cancellable background-friendly image indexing routine."""

import os
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from advanced_file_finder.core.filters import filter_directories
from advanced_file_finder.core.models import OcrProgress
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
    detailed_progress: Callable[[OcrProgress], None] | None = None,
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
    metadata = cache.metadata_snapshot()
    total = len(files)
    cache_hits = 0
    needs_ocr = 0
    cache_current: list[bool] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            cache_current.append(False)
            needs_ocr += 1
            continue
        cached = metadata.get(str(path))
        is_hit = bool(cached and cached[:2] == (stat.st_size, stat.st_mtime_ns))
        cache_current.append(is_hit)
        if is_hit:
            cache_hits += 1
        else:
            needs_ocr += 1
    success = failed = ocr_completed = 0
    durations: deque[float] = deque(maxlen=20)
    pending: list[tuple[Path, OcrResult, str, str]] = []

    def flush() -> None:
        if pending:
            cache.upsert_many(pending)
            pending.clear()

    def emit(current: int, path: Path | None = None, size_bytes: int = 0, last_duration: float = 0.0) -> None:
        average = sum(durations) / len(durations) if durations else 0.0
        speed = ocr_completed / sum(durations) if durations and sum(durations) > 0 else 0.0
        remaining = max(0, needs_ocr - ocr_completed)
        eta = remaining / speed if speed > 0 else None
        if progress:
            progress(current, total, success, failed)
        if detailed_progress:
            detailed_progress(
                OcrProgress(
                    current=current,
                    discovered=total,
                    cache_hits=cache_hits,
                    needs_ocr=needs_ocr,
                    ocr_completed=ocr_completed,
                    success=success,
                    failed=failed,
                    current_filename=path.name if path else "",
                    current_size_bytes=size_bytes,
                    last_duration_seconds=last_duration,
                    average_ocr_seconds=average,
                    images_per_second=speed,
                    eta_seconds=eta,
                )
            )

    emit(0)
    for current, (path, is_hit) in enumerate(zip(files, cache_current, strict=True), 1):
        if cancel and cancel.is_set():
            flush()
            break
        if is_hit:
            success += 1
            try:
                size_bytes = path.stat().st_size
            except OSError:
                size_bytes = 0
            emit(current, path, size_bytes)
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0
        started = time.perf_counter()
        try:
            result = engine.recognize(path)
            pending.append((path, result, "indexed", ""))
            success += 1
        except (OSError, ValueError, RuntimeError) as error:
            pending.append((path, OcrResult("", 0.0), "failed", str(error)))
            failed += 1
        duration = time.perf_counter() - started
        durations.append(duration)
        ocr_completed += 1
        if len(pending) >= 50 or (cancel and cancel.is_set()):
            flush()
        emit(current, path, size_bytes, duration)
    flush()
    return success, failed