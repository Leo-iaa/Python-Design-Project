"""SQLite-backed OCR metadata cache."""

import sqlite3
from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import SearchResult
from advanced_file_finder.core.ocr.engine import OcrResult
from advanced_file_finder.utils.paths import ocr_database_path

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
CacheMetadata = tuple[int, int, str]
CacheRecord = tuple[Path, OcrResult, str, str]


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
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
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

    def metadata_snapshot(self) -> dict[str, CacheMetadata]:
        """Read file metadata once for a complete indexing task."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT path,file_size,modified_ns,status FROM ocr_files"
            ).fetchall()
        return {str(path): (int(size), int(modified_ns), str(status)) for path, size, modified_ns, status in rows}

    def is_current(self, path: Path) -> bool:
        """Return true when any recorded status still matches current metadata."""
        try:
            stat = path.stat()
        except OSError:
            return False
        with self._connect() as db:
            row = db.execute(
                "SELECT file_size, modified_ns FROM ocr_files WHERE path=?", (str(path),)
            ).fetchone()
        return bool(row and row[0] == stat.st_size and row[1] == stat.st_mtime_ns)

    def upsert(
        self, path: Path, result: OcrResult, status: str = "indexed", error: str = ""
    ) -> None:
        self.upsert_many([(path, result, status, error)])

    def upsert_many(self, records: list[CacheRecord]) -> int:
        """Persist a batch in one transaction and return rows written."""
        if not records:
            return 0
        indexed_at = datetime.now().isoformat()
        rows = []
        for path, result, status, error in records:
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append(
                (
                    str(path),
                    stat.st_size,
                    stat.st_mtime_ns,
                    result.text,
                    result.confidence,
                    result.engine_name,
                    indexed_at,
                    status,
                    error,
                )
            )
        if not rows:
            return 0
        with self._connect() as db:
            db.executemany("INSERT OR REPLACE INTO ocr_files VALUES (?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

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

    def prune_missing(self) -> int:
        """Remove cache rows whose images no longer exist."""
        with self._connect() as db:
            rows = db.execute("SELECT path FROM ocr_files").fetchall()
            removed = 0
            for (value,) in rows:
                if not Path(value).exists():
                    db.execute("DELETE FROM ocr_files WHERE path=?", (value,))
                    removed += 1
        return removed

    def clear(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM ocr_files")

    def stats(self) -> tuple[int, int, int]:
        with self._connect() as db:
            return db.execute(
                "SELECT count(*),sum(status='pending'),sum(status='failed') FROM ocr_files"
            ).fetchone()