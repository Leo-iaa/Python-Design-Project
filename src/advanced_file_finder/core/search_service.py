"""Concurrent root-path searches with cancellation and live notifications."""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.ranker import rank_results
from advanced_file_finder.core.scanner import scan_path

ProgressCallback = Callable[[SearchStats], None]


def search(
    options: SearchOptions,
    cancel: threading.Event | None = None,
    on_result: Callable[[SearchResult], None] | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[SearchResult], SearchStats]:
    """Search each root concurrently and safely publish results and statistics."""
    cancel = cancel or threading.Event()
    lock = threading.Lock()
    started = time.perf_counter()
    results: list[SearchResult] = []
    total = SearchStats()

    def task(root: Path) -> None:
        local = SearchStats()

        def found(item: SearchResult) -> None:
            if cancel.is_set():
                return
            with lock:
                results.append(item)
                total.matches += 1
            if on_result:
                on_result(item)

        scan_path(root, options, local, found, cancel)
        with lock:
            total.files_scanned += local.files_scanned
            total.directories_scanned += local.directories_scanned
            total.permission_denied += local.permission_denied
            total.errors += local.errors
            total.error_messages.extend(local.error_messages)
            snapshot = SearchStats(
                total.files_scanned,
                total.directories_scanned,
                total.matches,
                total.permission_denied,
                total.errors,
            )
        if on_progress:
            on_progress(snapshot)

    workers = min(8, max(1, len(options.search_paths)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="file-search") as executor:
        for future in [executor.submit(task, path) for path in options.search_paths]:
            future.result()
    total.elapsed_time = time.perf_counter() - started
    return rank_results(results), total
