"""Qt worker that keeps filesystem scans off the GUI thread."""

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from advanced_file_finder.core.models import OcrProgress, SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.search_service import search


class SearchWorker(QObject):
    """Bridge core callbacks to queued Qt signals."""

    _BATCH_SIZE = 100

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
        self._batch.append(result)
        if len(self._batch) >= self._BATCH_SIZE:
            self.results_batch.emit(self._batch)
            self._batch = []

    def _emit_progress(self, stats: SearchStats) -> None:
        self.progress_changed.emit(stats)


class OcrIndexWorker(QObject):
    """Run conservative one-worker OCR indexing in a QThread."""

    progress_changed = Signal(int, int, int, int)
    detailed_progress = Signal(object)
    state_changed = Signal(str)
    finished = Signal(int, int, int, int, bool)
    failed = Signal(str)

    def __init__(
        self,
        roots: tuple[Path, ...],
        cancel: threading.Event,
        excluded_directories: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.roots = roots
        self.cancel = cancel
        self.excluded_directories = excluded_directories
        self._last_progress = (0, 0, 0, 0)

    @Slot()
    def run(self) -> None:
        try:
            from advanced_file_finder.core.ocr.cache import OcrCache
            from advanced_file_finder.core.ocr.engine import RapidOcrEngine
            from advanced_file_finder.core.ocr.indexer import index_images
            from advanced_file_finder.utils.paths import ocr_database_path

            if self.cancel.is_set():
                self.finished.emit(0, 0, 0, 0, True)
                return
            cache = OcrCache(ocr_database_path())
            success, failed = index_images(
                self.roots,
                cache,
                RapidOcrEngine(),
                self.cancel,
                self._progress,
                self._state,
                self.excluded_directories,
                self._detailed_progress,
            )
            current, total, _progress_success, _progress_failed = self._last_progress
            self.finished.emit(current, total, success, failed, self.cancel.is_set())
        except Exception as error:
            self.failed.emit(str(error))

    def _progress(self, current: int, total: int, success: int, failed: int) -> None:
        self._last_progress = (current, total, success, failed)
        self.progress_changed.emit(current, total, success, failed)

    def _detailed_progress(self, progress: OcrProgress) -> None:
        self.detailed_progress.emit(progress)

    def _state(self, state: str) -> None:
        self.state_changed.emit(state)