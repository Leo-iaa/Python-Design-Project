"""Concurrent root-path searches with a cooperative cancellation event."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.scanner import scan_path


def search(
    options: SearchOptions, cancel: threading.Event | None = None
) -> tuple[list[SearchResult], SearchStats]:
    """Search roots concurrently; cancellation retains already collected results."""
    cancel = cancel or threading.Event()
    lock = threading.Lock()
    started = time.perf_counter()
    results: list[SearchResult] = []
    total = SearchStats()

    def task(root: Path) -> None:
        local = SearchStats()
        found = scan_path(
            root, options, local, lambda item: None if cancel.is_set() else results.append(item)
        )
        if cancel.is_set():
            found = []
        with lock:
            results.extend(found)`n            total.files_scanned += local.files_scanned
            total.directories_scanned += local.directories_scanned
            total.permission_denied += local.permission_denied
            total.errors += local.errors
            total.error_messages.extend(local.error_messages)
            total.matches += len(found)

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(options.search_paths)))) as executor:
        futures = [executor.submit(task, path) for path in options.search_paths]
        for future in futures:
            future.result()
    total.matches = len(results)
    total.elapsed_time = time.perf_counter() - started
    return results, total
