"""Unified concurrent filename/OCR search service."""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ranker import rank_results
from advanced_file_finder.core.scanner import scan_path
from advanced_file_finder.utils.paths import ocr_database_path

ProgressCallback = Callable[[SearchStats], None]


def _ocr_cache() -> OcrCache:
    return OcrCache(ocr_database_path())


def search(
    options: SearchOptions,
    cancel: threading.Event | None = None,
    on_result: Callable[[SearchResult], None] | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[SearchResult], SearchStats]:
    """Search configured sources and merge filename/OCR hits into one ranked list."""
    cancel = cancel or threading.Event()
    lock = threading.Lock()
    started = time.perf_counter()
    results: dict[Path, SearchResult] = {}
    total = SearchStats()

    def publish(item: SearchResult) -> None:
        if cancel.is_set():
            return
        with lock:
            previous = results.get(item.full_path)
            if previous and previous.match_source != item.match_source:
                score = min(100.0, max(previous.match_score, item.match_score) + 5.0)
                item = SearchResult(
                    item.name,
                    item.full_path,
                    item.parent_path,
                    item.extension,
                    item.size,
                    item.modified_time,
                    score,
                    "filename+ocr",
                    "combined filename and OCR",
                    item.ocr_excerpt or previous.ocr_excerpt,
                )
            results[item.full_path] = item
        if on_result:
            on_result(item)

    def task(root: Path) -> None:
        local = SearchStats()
        if options.search_filename:
            scan_path(root, options, local, publish, cancel)
        with lock:
            total.files_scanned += local.files_scanned
            total.directories_scanned += local.directories_scanned
            total.permission_denied += local.permission_denied
            total.errors += local.errors
            total.error_messages.extend(local.error_messages)
            snapshot = SearchStats(
                total.files_scanned,
                total.directories_scanned,
                len(results),
                total.permission_denied,
                total.errors,
            )
        if on_progress:
            on_progress(snapshot)

    workers = min(8, max(1, len(options.search_paths)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="file-search") as executor:
        for future in [executor.submit(task, path) for path in options.search_paths]:
            future.result()
    if options.search_ocr and options.query and not cancel.is_set():
        for item in _ocr_cache().search(options.query, options.search_paths):
            publish(item)
    final = rank_results(list(results.values()))
    total.matches = len(final)
    total.elapsed_time = time.perf_counter() - started
    return final, total
