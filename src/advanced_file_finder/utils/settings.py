"""Runtime-only search history persisted in the user data directory."""

import json
from datetime import datetime
from pathlib import Path

from advanced_file_finder.utils.paths import (
    SEARCH_HISTORY_PATH,
    ensure_local_dirs,
    migrate_legacy_json,
)


def history_path() -> Path:
    """Return the project-local search-history path."""
    ensure_local_dirs()
    migrate_legacy_json()
    return SEARCH_HISTORY_PATH


def add_history(query: str, mode: str, paths: tuple[Path, ...]) -> None:
    path = history_path()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        entries = []
    entries.insert(
        0,
        {
            "query": query,
            "mode": mode,
            "paths": [str(p) for p in paths],
            "time": datetime.now().isoformat(),
        },
    )
    path.write_text(json.dumps(entries[:20], ensure_ascii=False, indent=2), encoding="utf-8")


def load_history() -> list[dict[str, object]]:
    try:
        return json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
