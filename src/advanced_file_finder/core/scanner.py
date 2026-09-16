"""Safe recursive scanner based on :func:`os.walk`."""
import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.matcher import matches
from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats


def scan_path(root: Path, options: SearchOptions, stats: SearchStats,
              on_result: Callable[[SearchResult], None] | None = None) -> list[SearchResult]:
    """Recursively scan one directory, retaining filesystem failures in statistics."""
    started = time.perf_counter()
    results: list[SearchResult] = []

    def onerror(error: OSError) -> None:
        if isinstance(error, PermissionError):
            stats.permission_denied += 1
        else:
            stats.errors += 1
            stats.error_messages.append(str(error))

    if not root.is_dir():
        stats.errors += 1
        stats.error_messages.append(f"Search path does not exist or is not a directory: {root}")
        stats.elapsed_time += time.perf_counter() - started
        return results
    for directory, _, filenames in os.walk(root, onerror=onerror):
        stats.directories_scanned += 1
        parent = Path(directory)
        for filename in filenames:
            stats.files_scanned += 1
            if not matches(filename, options.query, options.match_mode, options.case_sensitive):
                continue
            path = parent / filename
            try:
                metadata = path.stat()
            except PermissionError:
                stats.permission_denied += 1
                continue
            except OSError as error:
                stats.errors += 1
                stats.error_messages.append(str(error))
                continue
            result = SearchResult(filename, path, parent, path.suffix, metadata.st_size,
                                  datetime.fromtimestamp(metadata.st_mtime))
            results.append(result)
            stats.matches += 1
            if on_result:
                on_result(result)
    stats.elapsed_time += time.perf_counter() - started
    return results