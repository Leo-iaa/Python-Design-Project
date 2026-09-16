"""Runtime-only search history persisted in the user data directory."""

import json
import os
from datetime import datetime
from pathlib import Path


def history_path() -> Path:
    root = Path(os.getenv("APPDATA", Path.home())) / "AdvancedFileFinder"
    root.mkdir(parents=True, exist_ok=True)
    return root / "history.json"


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
