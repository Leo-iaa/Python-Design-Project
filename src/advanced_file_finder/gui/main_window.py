"""Responsive, native-looking main window."""

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from advanced_file_finder.core.exporter import export_results
from advanced_file_finder.core.models import MatchMode, SearchOptions
from advanced_file_finder.gui.search_worker import SearchWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Advanced File Finder")
        self.resize(1050, 650)
        self.cancel = threading.Event()
        self.results = []
        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("搜索关键词")
        self.extensions = QLineEdit()
        self.extensions.setPlaceholderText("扩展名，如 pdf,docx")
        self.mode = QComboBox()
        self.mode.addItems([x.value for x in MatchMode])
        self.path = QLineEdit(str(Path.cwd()))
        choose = QPushButton("选择目录")
        self.search_button = QPushButton("搜索")
        export_button = QPushButton("导出结果")
        self.stop = QPushButton("停止搜索")
        self.stop.setEnabled(False)
        for w in (
            QLabel("关键词"),
            self.query,
            QLabel("模式"),
            self.mode,
            QLabel("路径"),
            self.path,
            choose,
            self.search_button,
            self.stop,
        ):
            top.addWidget(w)
        layout.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["文件名", "所在目录", "类型", "大小", "修改时间", "完整路径"]
        )
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        bottom = QHBoxLayout()
        self.status = QLabel("就绪")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        bottom.addWidget(self.status)
        bottom.addWidget(self.progress)
        layout.addLayout(bottom)
        self.setCentralWidget(root)
        choose.clicked.connect(self.choose)
        self.search_button.clicked.connect(self.start)
        self.stop.clicked.connect(self.cancel_search)
        export_button.clicked.connect(self.export)
        self.table.cellDoubleClicked.connect(self.open_result)

    def choose(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择搜索目录", self.path.text())
        if directory:
            self.path.setText(directory)

    def start(self) -> None:
        root = Path(self.path.text())
        if not root.is_dir():
            QMessageBox.warning(self, "无效路径", "请选择存在的目录。")
            return
        self.table.setRowCount(0)
        self.cancel.clear()
        self.progress.setVisible(True)
        self.search_button.setEnabled(False)
        self.stop.setEnabled(True)
        self.status.setText("正在扫描…")
        options = SearchOptions(self.query.text(), (root,), MatchMode(self.mode.currentText()))
        self.thread = QThread(self)
        self.worker = SearchWorker(options, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.done)
        self.worker.failed.connect(lambda x: QMessageBox.critical(self, "搜索失败", x))
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def done(self, results: list, stats: object) -> None:
        self.results = results
        self.table.setRowCount(len(results))
        for row, item in enumerate(results):
            values = [
                item.name,
                str(item.parent_path),
                item.extension,
                str(item.size),
                item.modified_time.strftime("%Y-%m-%d %H:%M"),
                str(item.full_path),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.progress.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop.setEnabled(False)
        state = "已取消" if self.cancel.is_set() else "完成"
        self.status.setText(
            f"{state}：扫描 {stats.files_scanned} 文件，找到 {stats.matches}，{stats.elapsed_time:.2f} 秒"
        )

    def export(self) -> None:
        if not self.results:
            QMessageBox.information(self, "导出", "没有可导出的结果。")
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "导出结果", "results.csv", "CSV (*.csv);;JSON (*.json);;Text (*.txt)"
        )
        if path:
            suffix = Path(path).suffix.lstrip(".") or "csv"
            try:
                export_results(self.results, Path(path), suffix)
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "导出失败", str(error))

    def cancel_search(self) -> None:
        self.cancel.set()
        self.status.setText("正在取消…")

    def open_result(self, row: int, _: int) -> None:
        path = self.results[row].full_path
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
