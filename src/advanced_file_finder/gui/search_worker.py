"""Qt worker that keeps filesystem scans off the GUI thread."""

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.search_service import search


class SearchWorker(QObject):
    """Bridge core callbacks to queued Qt signals."""

    result_found = Signal(object)
    results_batch = Signal(list)
    progress_changed = Signal(object)
    finished = Signal(list, object)
    failed = Signal(str)

    def __init__(self, options: SearchOptions, cancel: threading.Event) -> None:
        super().__init__()
        self.options = options
        self.cancel = cancel
        self._batch: list[SearchResult] = []

    @Slot()
    def run(self) -> None:
        try:
            results, stats = search(
                self.options,
                self.cancel,
                self._emit_result,
                self._emit_progress,
            )
            if self._batch:
                self.results_batch.emit(self._batch)
            self.finished.emit(results, stats)
        except Exception as error:
            self.failed.emit(str(error))

    def _emit_result(self, result: SearchResult) -> None:
        self.result_found.emit(result)

    def _emit_progress(self, stats: SearchStats) -> None:
        self.progress_changed.emit(stats)


class OcrIndexWorker(QObject):
    """Run conservative one-worker OCR indexing in a QThread."""

    progress_changed = Signal(int, int, int, int)
    finished = Signal(int, int)
    failed = Signal(str)

    def __init__(self, roots: tuple[Path, ...], cancel: threading.Event) -> None:
        super().__init__()
        self.roots = roots
        self.cancel = cancel
        self._batch: list[SearchResult] = []

    @Slot()
    def run(self) -> None:
        try:
            from advanced_file_finder.core.ocr.cache import OcrCache
            from advanced_file_finder.core.ocr.engine import RapidOcrEngine
            from advanced_file_finder.core.ocr.indexer import index_images
            from advanced_file_finder.utils.paths import ocr_database_path

            cache = OcrCache(ocr_database_path())
            self.finished.emit(
                *index_images(self.roots, cache, RapidOcrEngine(), self.cancel, self._progress)
            )
        except Exception as error:
            self.failed.emit(str(error))

    def _progress(self, current: int, total: int, success: int, failed: int) -> None:
        self.progress_changed.emit(current, total, success, failed)
