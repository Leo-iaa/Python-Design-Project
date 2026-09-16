import sqlite3
from pathlib import Path

from advanced_file_finder.utils import paths


def test_project_local_path_and_gitignore(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(paths, "LOCAL_DATA_DIR", tmp_path / ".local")
    monkeypatch.setattr(paths, "OCR_DATABASE_PATH", tmp_path / ".local" / "ocr.sqlite")
    assert paths.ocr_database_path() == tmp_path / ".local" / "ocr.sqlite"
    assert paths.LOCAL_DATA_DIR.exists()


def test_legacy_database_backup_does_not_overwrite(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / "legacy" / "ocr.sqlite"
    legacy.parent.mkdir()
    db = sqlite3.connect(legacy)
    db.execute("create table t (x)")
    db.execute("insert into t values (1)")
    db.commit()
    db.close()
    target = tmp_path / ".local" / "ocr.sqlite"
    monkeypatch.setattr(paths, "LOCAL_DATA_DIR", tmp_path / ".local")
    monkeypatch.setattr(paths, "OCR_DATABASE_PATH", target)
    monkeypatch.setattr(paths, "legacy_ocr_database_path", lambda: legacy)
    paths.migrate_legacy_ocr()
    assert target.exists() and legacy.exists()
    target.write_bytes(b"keep")
    paths.migrate_legacy_ocr()
    assert target.read_bytes() == b"keep"
