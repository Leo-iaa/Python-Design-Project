"""Centralized project-local runtime paths."""

import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_DATA_DIR = PROJECT_ROOT / ".local"
OCR_DATABASE_PATH = LOCAL_DATA_DIR / "ocr.sqlite"


def legacy_ocr_database_path() -> Path:
    """Return the pre-Stage-16 per-user OCR database location."""
    return Path(os.getenv("APPDATA", Path.home())) / "AdvancedFileFinder" / "ocr.sqlite"


def migrate_legacy_ocr() -> Path:
    """Copy a legacy SQLite DB safely, preserving the original and WAL state."""
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    legacy = legacy_ocr_database_path()
    if OCR_DATABASE_PATH.exists() or not legacy.exists():
        return OCR_DATABASE_PATH
    try:
        source = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
        target = sqlite3.connect(OCR_DATABASE_PATH)
        source.backup(target)
        target.close()
        source.close()
        log.info("OCR database migrated from legacy location: %s", legacy)
    except (OSError, sqlite3.Error) as error:
        log.warning("Could not migrate legacy OCR database: %s", error)
        if OCR_DATABASE_PATH.exists():
            OCR_DATABASE_PATH.unlink()
    return OCR_DATABASE_PATH


def ocr_database_path() -> Path:
    """Return the project-local OCR database path, migrating legacy data once."""
    return migrate_legacy_ocr()
