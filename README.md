# Advanced File Finder

Advanced File Finder is a Windows-first, read-only desktop search tool built with Python 3.12, PySide6 and UV. Filesystem work runs in worker threads so the GUI stays responsive.

## Search modes

- `exact`: complete filename match
- `partial`: case-insensitive substring match
- `fuzzy`: RapidFuzz WRatio over the filename stem, with a configurable 0-100 threshold (default 75)
- `glob`: patterns such as `*.pdf`
- `regex`: Python regular expressions with friendly invalid-pattern errors

Results are ranked by filename relevance first, with recency and path depth used only as stable tie-breakers. Fuzzy scores, OCR scores and combined-source bonuses are normalized to 0-100.

## Filters and scopes

The GUI supports current directory, multiple custom directories, and all detected Windows drives. Filters include extension, minimum/maximum size, modification date range, hidden files/directories, and excluded directory names.

## Saved and Smart Search

Use **保存当前** to persist the complete query configuration in the user application-data directory. Saved searches can be loaded from the toolbar. Built-in Smart Searches include 今天, 最近 24 小时, 最近 7 天, and 最近 30 天; their time windows are resolved relative to the time of execution rather than stored as fixed dates.

## OCR image search

OCR is local-only and uses RapidOCR with Pillow-compatible image formats: PNG, JPG/JPEG, BMP and WEBP. Click **建立 OCR 索引** before searching image text, then enable **图片文字 OCR** (alone or together with 文件名). OCR text is cached in SQLite at the project-local path `<PROJECT_ROOT>/.local/ocr.sqlite` (legacy `%APPDATA%\\AdvancedFileFinder\\ocr.sqlite` databases are copied safely once), keyed by path, file size and modification time. Changed images are reprocessed; cached images are reused. Indexing is cancellable and reports real `processed / total`, success and failure counts. OCR matches show a short excerpt and participate in the same ranking and export pipeline. No image or OCR content is uploaded.

The first index can take time because the OCR model runs locally. Subsequent searches use the cache and are much faster.

## Install and run

UV is required; do not activate a virtual environment manually:

```powershell
uv sync
uv run python -m advanced_file_finder
```

CLI examples:

```powershell
uv run advanced-file-finder report D:\Documents --ext pdf,docx
uv run advanced-file-finder "^invoice.*\\.pdf$" D:\Documents --regex
```

## Development and verification

```powershell
uv run pytest
uv run ruff check .
```

The test suite uses temporary directories and mock OCR engines; it does not scan a real system drive or use private user images.

## Project structure

- `src/advanced_file_finder/core`: models, matcher, filters, scanner, concurrent service, ranker, exporters, saved searches and OCR engine/cache/indexer
- `src/advanced_file_finder/gui`: PySide6 main window and background workers
- `src/advanced_file_finder/utils`: user-data settings/history locations
- `tests`: filename, filter, ranking, saved-search, export, OCR-cache and regression tests

The application never deletes or modifies searched files. OCR databases and search history are kept outside the repository; `.gitignore` excludes runtime data and build artifacts.