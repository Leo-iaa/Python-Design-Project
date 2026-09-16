"""Qt worker that keeps filesystem scans off the GUI thread."""

import threading

from PySide6.QtCore import QObject, Signal, Slot

from advanced_file_finder.core.models import SearchOptions
from advanced_file_finder.core.search_service import search


class SearchWorker(QObject):
    finished = Signal(list, object)
    failed = Signal(str)

    def __init__(self, options: SearchOptions, cancel: threading.Event) -> None:
        super().__init__()
        self.options = options
        self.cancel = cancel

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(*search(self.options, self.cancel))
        except Exception as error:
            self.failed.emit(str(error))
