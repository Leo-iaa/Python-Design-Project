"""Feature-complete, responsive Qt desktop interface."""

import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from advanced_file_finder.core.drives import available_drives
from advanced_file_finder.core.exporter import export_results
from advanced_file_finder.core.filters import normalize_extensions
from advanced_file_finder.core.models import MatchMode, SearchOptions, SearchResult, SearchStats
from advanced_file_finder.core.saved_search import SMART_RANGES, SavedSearch, SavedSearchRepository
from advanced_file_finder.gui.search_worker import OcrIndexWorker, SearchWorker
from advanced_file_finder.utils.settings import add_history


class MainWindow(QMainWindow):
    """Present all search modes without blocking Qt's main thread."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Advanced File Finder")
        self.resize(1180, 720)
        self.file_search_cancel_event = threading.Event()
        self.ocr_index_cancel_event = threading.Event()
        self.saved_repository = SavedSearchRepository()
        self.results: list[SearchResult] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("文件名关键词（留空查找所有文件）")
        self.mode = QComboBox()
        self.mode.addItems([item.value for item in MatchMode])
        self.scope = QComboBox()
        self.scope.addItems(["当前目录", "自定义路径", "所有可用磁盘"])
        self.saved_combo = QComboBox()
        self.saved_combo.addItem("已保存搜索")
        self.saved_combo.addItems([item.name for item in self.saved_repository.load()])
        self.smart_combo = QComboBox()
        self.smart_combo.addItem("智能搜索")
        self.smart_combo.addItems(SMART_RANGES)
        self.paths = QLineEdit(str(Path.cwd()))
        browse = QPushButton("添加目录")
        self.search_button = QPushButton("搜索")
        self.stop_button = QPushButton("停止搜索")
        self.stop_button.setEnabled(False)
        self.filename_target = QCheckBox("文件名")
        self.filename_target.setChecked(True)
        self.ocr_target = QCheckBox("图片文字 OCR")
        self.index_button = QPushButton("建立 OCR 索引")
        self.ocr_stop_button = QPushButton("停止 OCR 索引")
        self.ocr_stop_button.setEnabled(False)
        for item in (
            QLabel("关键词"),
            self.query,
            QLabel("匹配"),
            self.mode,
            QLabel("范围"),
            self.scope,
            self.paths,
            browse,
            self.search_button,
            self.stop_button,
        ):
            search_row.addWidget(item)
        layout.addLayout(search_row)

        filters = QGroupBox("高级过滤")
        grid = QGridLayout(filters)
        self.extensions = QLineEdit()
        self.extensions.setPlaceholderText("pdf, docx, .py")
        self.minimum = QLineEdit()
        self.minimum.setPlaceholderText("字节")
        self.maximum = QLineEdit()
        self.maximum.setPlaceholderText("字节")
        self.after_enabled = QCheckBox("修改时间起点")
        self.before_enabled = QCheckBox("修改时间终点")
        self.after_date = QDateEdit(QDate.currentDate().addYears(-1))
        self.before_date = QDateEdit(QDate.currentDate())
        self.after_date.setCalendarPopup(True)
        self.before_date.setCalendarPopup(True)
        self.hidden_files = QCheckBox("包含隐藏文件")
        self.hidden_dirs = QCheckBox("包含隐藏目录")
        self.excluded = QLineEdit(".git, .venv, node_modules, __pycache__")
        grid.addWidget(QLabel("扩展名"), 0, 0)
        grid.addWidget(self.extensions, 0, 1)
        grid.addWidget(QLabel("最小大小"), 0, 2)
        grid.addWidget(self.minimum, 0, 3)
        grid.addWidget(QLabel("最大大小"), 0, 4)
        grid.addWidget(self.maximum, 0, 5)
        grid.addWidget(self.after_enabled, 1, 0)
        grid.addWidget(self.after_date, 1, 1)
        grid.addWidget(self.before_enabled, 1, 2)
        grid.addWidget(self.before_date, 1, 3)
        grid.addWidget(self.hidden_files, 1, 4)
        grid.addWidget(self.hidden_dirs, 1, 5)
        grid.addWidget(QLabel("排除目录"), 2, 0)
        grid.addWidget(self.excluded, 2, 1, 1, 5)
        grid.addWidget(QLabel("搜索目标"), 3, 0)
        grid.addWidget(self.filename_target, 3, 1)
        grid.addWidget(self.ocr_target, 3, 2)
        grid.addWidget(self.index_button, 3, 3)
        grid.addWidget(self.ocr_stop_button, 3, 4)
        layout.addWidget(filters)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "文件名",
                "所在目录",
                "类型",
                "大小",
                "修改时间",
                "完整路径",
                "相关度",
                "来源",
                "OCR 摘要",
            ]
        )
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table)
        bottom = QHBoxLayout()
        self.status = QLabel("就绪")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.export_button = QPushButton("导出结果")
        bottom.addWidget(self.status)
        bottom.addWidget(self.progress)
        bottom.addWidget(self.export_button)
        layout.addLayout(bottom)
        self.setCentralWidget(root)
        browse.clicked.connect(self.add_directory)
        self.scope.currentIndexChanged.connect(self._scope_changed)
        self.search_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.cancel_search)
        self.export_button.clicked.connect(self.export)
        self.index_button.clicked.connect(self.start_ocr_index)
        self.ocr_stop_button.clicked.connect(self.cancel_ocr_index)
        self.table.cellDoubleClicked.connect(lambda row, _: self.open_file(row))
        self.table.customContextMenuRequested.connect(self.context_menu)

    def _scope_changed(self) -> None:
        custom = self.scope.currentText() == "自定义路径"
        self.paths.setEnabled(custom)
        if self.scope.currentText() == "当前目录":
            self.paths.setText(str(Path.cwd()))
        if self.scope.currentText() == "所有可用磁盘":
            self.paths.setText("; ".join(map(str, available_drives())))

    def add_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "添加搜索目录", str(Path.cwd()))
        if directory:
            existing = [value.strip() for value in self.paths.text().split(";") if value.strip()]
            if directory not in existing:
                existing.append(directory)
            self.paths.setText("; ".join(existing))
            self.scope.setCurrentText("自定义路径")

    def _options(self) -> SearchOptions:
        paths = tuple(
            Path(value.strip()) for value in self.paths.text().split(";") if value.strip()
        )
        if not paths or any(not path.is_dir() for path in paths):
            raise ValueError("请选择一个或多个存在的目录。")

        def number(widget: QLineEdit) -> int | None:
            return int(widget.text()) if widget.text().strip() else None

        minimum, maximum = number(self.minimum), number(self.maximum)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("最小大小不能大于最大大小。")
        after = (
            datetime.combine(self.after_date.date().toPython(), datetime.min.time())
            if self.after_enabled.isChecked()
            else None
        )
        before = (
            datetime.combine(self.before_date.date().toPython(), datetime.max.time())
            if self.before_enabled.isChecked()
            else None
        )
        return SearchOptions(
            self.query.text(),
            paths,
            MatchMode(self.mode.currentText()),
            extensions=normalize_extensions(self.extensions.text()),
            min_size=minimum,
            max_size=maximum,
            modified_after=after,
            modified_before=before,
            include_hidden=self.hidden_files.isChecked(),
            include_hidden_directories=self.hidden_dirs.isChecked(),
            excluded_directories=tuple(
                value.strip() for value in self.excluded.text().split(",") if value.strip()
            ),
            search_filename=self.filename_target.isChecked(),
            search_ocr=self.ocr_target.isChecked(),
        )

    def start(self) -> None:
        try:
            options = self._options()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "搜索条件无效", str(error))
            return
        self.results.clear()
        self.table.setRowCount(0)
        self.file_search_cancel_event.clear()
        self.progress.setVisible(True)
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("正在扫描…")
        add_history(options.query, options.match_mode.value, options.search_paths)
        self.thread = QThread(self)
        self.worker = SearchWorker(options, self.file_search_cancel_event)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.results_batch.connect(self.add_results)
        self.worker.progress_changed.connect(self.update_progress)
        self.worker.finished.connect(self.done)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def add_results(self, items: list[SearchResult]) -> None:
        for item in items:
            self.add_result(item)

    def add_result(self, item: SearchResult) -> None:
        self.results.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)
        source = {
            "filename": "文件名",
            "ocr": "图片文字 OCR",
            "filename+ocr": "文件名 + OCR",
        }.get(item.match_source, item.match_source)
        values = (
            item.name,
            str(item.parent_path),
            item.extension,
            str(item.size),
            item.modified_time.strftime("%Y-%m-%d %H:%M"),
            str(item.full_path),
            f"{item.match_score:.1f}",
            source,
            item.ocr_excerpt,
        )
        for col, value in enumerate(values):
            self.table.setItem(row, col, QTableWidgetItem(value))

    def update_progress(self, stats: SearchStats) -> None:
        self.status.setText(
            f"扫描 {stats.files_scanned} 文件 / {stats.directories_scanned} 目录；命中 {stats.matches}"
        )

    def done(self, results: list[SearchResult], stats: SearchStats) -> None:
        self.results = results
        self.progress.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        state = "已取消" if self.file_search_cancel_event.is_set() else "完成"
        self.status.setText(
            f"{state}：扫描 {stats.files_scanned} 文件，命中 {stats.matches}，耗时 {stats.elapsed_time:.2f} 秒"
        )

    def failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        QMessageBox.critical(self, "搜索失败", message)

    def save_current(self) -> None:
        try:
            options = self._options()
        except ValueError as error:
            QMessageBox.warning(self, "保存失败", str(error))
            return
        name, accepted = QInputDialog.getText(self, "保存搜索", "名称：")
        if accepted and name.strip():
            self.saved_repository.create(SavedSearch.from_options(name.strip(), options))
            self.saved_combo.addItem(name.strip())

    def load_saved(self, index: int) -> None:
        if index <= 0:
            return
        values = self.saved_repository.load()
        if index > len(values):
            return
        saved = values[index - 1]
        self.query.setText(saved.query)
        self.mode.setCurrentText(saved.match_mode)
        self.paths.setText("; ".join(saved.search_paths))
        self.extensions.setText(",".join(saved.extensions))
        self.minimum.setText(str(saved.min_size or ""))
        self.maximum.setText(str(saved.max_size or ""))
        self.start()
        self.saved_combo.setCurrentIndex(0)

    def load_smart(self, index: int) -> None:
        if index <= 0:
            return
        label = self.smart_combo.itemText(index)
        kind, value = SMART_RANGES[label]
        now = datetime.now()
        after = (
            now - __import__("datetime").timedelta(hours=value)
            if kind == "relative_hours"
            else now - __import__("datetime").timedelta(days=value)
        )
        self.after_enabled.setChecked(True)
        self.after_date.setDate(QDate(after.year, after.month, after.day))
        self.query.setText("")
        self.start()
        self.smart_combo.setCurrentIndex(0)

    def start_ocr_index(self) -> None:
        if self._ocr_thread_running():
            return
        roots = tuple(
            Path(value.strip()) for value in self.paths.text().split(";") if value.strip()
        )
        if not roots or any(not root.is_dir() for root in roots):
            QMessageBox.warning(self, "OCR 索引", "请选择存在的目录。")
            return
        self.ocr_index_cancel_event.clear()
        self.index_button.setEnabled(False)
        self.ocr_stop_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.status.setText("正在初始化 OCR…")
        self.ocr_thread = QThread(self)
        self.ocr_worker = OcrIndexWorker(roots, self.ocr_index_cancel_event)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.state_changed.connect(self.ocr_index_state)
        self.ocr_worker.progress_changed.connect(self.ocr_index_progress)
        self.ocr_worker.finished.connect(self.ocr_index_done)
        self.ocr_worker.failed.connect(self.ocr_index_failed)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.failed.connect(self.ocr_thread.quit)
        self.ocr_thread.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_thread.finished.connect(self.ocr_thread.deleteLater)
        self.ocr_thread.start()

    def ocr_index_done(
        self, processed: int, total: int, success: int, failed: int, cancelled: bool
    ) -> None:
        self.index_button.setEnabled(True)
        self.ocr_stop_button.setEnabled(False)
        self.progress.setVisible(False)
        if cancelled:
            self.status.setText(
                f"OCR 索引已停止：{processed}/{total}，成功 {success}，失败 {failed}"
            )
        else:
            self.status.setText(f"OCR 索引完成：{total}/{total}，成功 {success}，失败 {failed}")

    def ocr_index_failed(self, message: str) -> None:
        self.index_button.setEnabled(True)
        self.ocr_stop_button.setEnabled(False)
        self.progress.setVisible(False)
        self.status.setText(f"OCR 索引失败：{message}")
        QMessageBox.critical(self, "OCR 索引失败", message)

    def ocr_index_state(self, state: str) -> None:
        if state == "initializing":
            self.status.setText("正在初始化 OCR…")
        elif state == "enumerating":
            self.status.setText("正在枚举图片…")

    def ocr_index_progress(self, current: int, total: int, success: int, failed: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.status.setText(f"OCR 索引：{current}/{total}，成功 {success}，失败 {failed}")

    def cancel_search(self) -> None:
        self.file_search_cancel_event.set()
        self.status.setText("正在取消搜索…")

    def cancel_ocr_index(self) -> None:
        if self._ocr_thread_running():
            self.ocr_index_cancel_event.set()
            self.ocr_stop_button.setEnabled(False)
            self.status.setText("正在停止 OCR 索引…")

    def _ocr_thread_running(self) -> bool:
        thread = self.__dict__.get("ocr_thread")
        if not isinstance(thread, QThread):
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            self.__dict__["ocr_thread"] = None
            return False

    def closeEvent(self, event: object) -> None:
        self.file_search_cancel_event.set()
        self.ocr_index_cancel_event.set()
        for thread_name in ("thread", "ocr_thread"):
            thread = self.__dict__.get(thread_name)
            if not isinstance(thread, QThread):
                continue
            try:
                running = thread.isRunning()
            except RuntimeError:
                running = False
            if running:
                thread.quit()
                thread.wait(10000)
        event.accept()

    def _item_path(self, row: int) -> Path:
        return Path(self.table.item(row, 5).text())

    def open_file(self, row: int) -> None:
        self._open(self._item_path(row))

    def _open(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def context_menu(self, position: object) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        path = self._item_path(row)
        menu = QMenu(self)
        open_action = menu.addAction("打开文件")
        folder_action = menu.addAction("打开所在文件夹")
        copy_path = menu.addAction("复制完整路径")
        copy_name = menu.addAction("复制文件名")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == open_action:
            self._open(path)
        elif chosen == folder_action:
            self._open(path.parent)
        elif chosen == copy_path:
            QApplication.clipboard().setText(str(path))
        elif chosen == copy_name:
            QApplication.clipboard().setText(path.name)

    def export(self) -> None:
        if not self.results:
            QMessageBox.information(self, "导出", "没有可导出的结果。")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "results.csv", "CSV (*.csv);;JSON (*.json);;Text (*.txt)"
        )
        if filename:
            try:
                export_results(
                    self.results, Path(filename), Path(filename).suffix.lstrip(".") or "csv"
                )
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "导出失败", str(error))


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
