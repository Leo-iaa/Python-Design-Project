# Advanced File Finder

A Windows-first, read-only file search application built with Python and PySide6. Filesystem work uses `os.walk()` and runs outside the Qt GUI thread.

## Features

- Exact, partial, glob, and regular-expression filename matching
- Multiple concurrent root searches, detected Windows drives, cooperative cancellation, and scan statistics
- Extension, size, date, hidden-file, and excluded-directory filters in the core layer
- CSV (UTF-8-SIG), JSON (UTF-8), and TXT exports
- Native PySide6 search window with sortable results, directory selection, indeterminate progress, stop, export, and double-click open
- A lightweight CLI for automation

## Install and run

UV is required. Do not activate a virtual environment manually:

```powershell
uv sync
uv run python -m advanced_file_finder
```

CLI examples:

```powershell
uv run advanced-file-finder report D:\Documents --ext pdf,docx
uv run advanced-file-finder "^invoice.*\\.pdf$" D:\Documents --regex
```

## Development

```powershell
uv run pytest
uv run ruff check .
```

## Structure

- `src/advanced_file_finder/core`: models, matcher, filters, scanner, concurrent service, exports
- `src/advanced_file_finder/gui`: Qt window and worker
- `src/advanced_file_finder/utils`: per-user search history
- `tests`: temporary-directory unit tests

## Notes

The application never deletes or modifies searched files. Search history is kept in the user's application data directory rather than the repository. Progress is intentionally indeterminate because filesystem totals are not pre-scanned.