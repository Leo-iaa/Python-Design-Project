"""Centralized paths and safe migration for application-owned persistence."""

import json
import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_DIR = PROJECT_ROOT / ".local"
# Backward-compatible alias for callers/tests from the previous path module.
LOCAL_DATA_DIR = LOCAL_DIR
OCR_DIR = LOCAL_DIR / "ocr"
CONFIG_DIR = LOCAL_DIR / "config"
LOG_DIR = LOCAL_DIR / "logs"
REPORT_DIR = LOCAL_DIR / "reports"
BENCHMARK_DIR = LOCAL_DIR / "benchmark_data"
OCR_DATABASE_PATH = LOCAL_DIR / "ocr.sqlite"
SEARCH_HISTORY_PATH = CONFIG_DIR / "search_history.json"
SAVED_SEARCH_PATH = CONFIG_DIR / "saved_searches.json"


def legacy_app_dir() -> Path:
    """Return the previous application-owned data directory."""
    return Path(os.getenv("APPDATA", Path.home())) / "AdvancedFileFinder"


def legacy_ocr_database_path() -> Path:
    return legacy_app_dir() / "ocr.sqlite"


def ensure_local_dirs() -> None:
    """Create all project-local persistence directories as needed."""
    for directory in (LOCAL_DATA_DIR, OCR_DIR, CONFIG_DIR, LOG_DIR, REPORT_DIR, BENCHMARK_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _migrate_json(legacy: Path, target: Path) -> bool:
    if not legacy.exists():
        return False
    try:
        old = json.loads(legacy.read_text(encoding="utf-8"))
        if target.exists():
            new = json.loads(target.read_text(encoding="utf-8"))
            if old != new:
                log.warning("Persistence conflict; retaining legacy file: %s", legacy)
                return False
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
            if json.loads(target.read_text(encoding="utf-8")) != old:
                return False
        legacy.unlink()
        return True
    except (OSError, json.JSONDecodeError, TypeError) as error:
        log.warning("Could not migrate JSON %s: %s", legacy, error)
        return False


def migrate_legacy_json() -> None:
    """Migrate known project JSON files and remove only verified legacy copies."""
    ensure_local_dirs()
    _migrate_json(legacy_app_dir() / "history.json", SEARCH_HISTORY_PATH)
    _migrate_json(legacy_app_dir() / "saved_searches.json", SAVED_SEARCH_PATH)


def migrate_legacy_ocr() -> Path:
    """Copy a legacy SQLite DB safely, preserving the original until verified."""
    ensure_local_dirs()
    legacy = legacy_ocr_database_path()
    if OCR_DATABASE_PATH.exists() or not legacy.exists():
        return OCR_DATABASE_PATH
    source = target = None
    try:
        source = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
        target = sqlite3.connect(OCR_DATABASE_PATH)
        source.backup(target)
        check = target.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise sqlite3.DatabaseError(f"integrity_check: {check}")
        log.info("OCR database migrated from legacy location: %s", legacy)
    except (OSError, sqlite3.Error) as error:
        log.warning("Could not migrate legacy OCR database: %s", error)
        if OCR_DATABASE_PATH.exists():
            OCR_DATABASE_PATH.unlink()
        return OCR_DATABASE_PATH
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{legacy}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    legacy.unlink()
    return OCR_DATABASE_PATH


def ocr_database_path() -> Path:
    """Return the project-local OCR DB after safe legacy migration."""
    return migrate_legacy_ocr()
