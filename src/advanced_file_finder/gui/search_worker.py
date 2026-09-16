"""Qt worker that keeps filesystem scans off the GUI thread."""

import threading

from PySide6.QtCore import QObject, Signal, Slot

from advanced_file_finder.core.models import SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.search_service import search


class SearchWorker(QObject):
    """Bridge core callbacks to queued Qt signals."""

    result_found = Signal(object)
    progress_changed = Signal(object)
    finished = Signal(list, object)
    failed = Signal(str)

    def __init__(self, options: SearchOptions, cancel: threading.Event) -> None:
        super().__init__()
        self.options = options
        self.cancel = cancel

    @Slot()
    def run(self) -> None:
        try:
            results, stats = search(
                self.options,
                self.cancel,
                self._emit_result,
                self._emit_progress,
            )
            self.finished.emit(results, stats)
        except Exception as error:
            self.failed.emit(str(error))

    def _emit_result(self, result: SearchResult) -> None:
        self.result_found.emit(result)

    def _emit_progress(self, stats: SearchStats) -> None:
        self.progress_changed.emit(stats)
