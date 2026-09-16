"""SQLite-backed OCR metadata cache."""

import sqlite3
from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import SearchResult
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.utils.paths import ocr_database_path

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class OcrCache:
    """Owns all OCR database operations and invalidates by size/mtime."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ocr_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS ocr_files (path TEXT PRIMARY KEY, file_size INTEGER, modified_ns INTEGER, ocr_text TEXT, confidence REAL, engine TEXT, indexed_at TEXT, status TEXT, error TEXT)"
            )

    def get(self, path: Path) -> OcrResult | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT file_size,modified_ns,ocr_text,confidence,engine FROM ocr_files WHERE path=? AND status='indexed'",
                (str(path),),
            ).fetchone()
        if not row or row[0] != stat.st_size or row[1] != stat.st_mtime_ns:
            return None
        return OcrResult(row[2], row[3], row[4])

    def upsert(
        self, path: Path, result: OcrResult, status: str = "indexed", error: str = ""
    ) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO ocr_files VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(path),
                    stat.st_size,
                    stat.st_mtime_ns,
                    result.text,
                    result.confidence,
                    result.engine_name,
                    datetime.now().isoformat(),
                    status,
                    error,
                ),
            )

    def search(self, query: str, roots: tuple[Path, ...]) -> list[SearchResult]:
        rows = []
        with self._connect() as db:
            for root in roots:
                rows.extend(
                    db.execute(
                        "SELECT path,ocr_text,confidence FROM ocr_files WHERE status='indexed' AND path LIKE ? AND ocr_text LIKE ?",
                        (str(root) + "%", f"%{query}%"),
                    ).fetchall()
                )
        results = []
        for value, text, confidence in rows:
            path = Path(value)
            try:
                stat = path.stat()
            except OSError:
                continue
            pos = text.casefold().find(query.casefold())
            excerpt = text[max(0, pos - 40) : pos + len(query) + 80] if pos >= 0 else text[:120]
            results.append(
                SearchResult(
                    path.name,
                    path,
                    path.parent,
                    path.suffix,
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime),
                    max(0.0, min(100.0, confidence * 100)),
                    "ocr",
                    "ocr partial",
                    excerpt,
                )
            )
        return results

    def clear(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM ocr_files")

    def stats(self) -> tuple[int, int, int]:
        with self._connect() as db:
            return db.execute(
                "SELECT count(*),sum(status='pending'),sum(status='failed') FROM ocr_files"
            ).fetchone()
