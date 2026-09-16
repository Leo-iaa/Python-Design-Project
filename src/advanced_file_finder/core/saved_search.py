"""User-owned saved searches and dynamic smart-search time ranges."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from advanced_file_finder.core.models import MatchMode, SearchOptions
from advanced_file_finder.utils.settings import history_path


def saved_path() -> Path:
    return history_path().with_name("saved_searches.json")


@dataclass(slots=True)
class SavedSearch:
    id: str
    name: str
    query: str
    match_mode: str
    search_paths: tuple[str, ...]
    case_sensitive: bool = False
    fuzzy_threshold: int = 75
    extensions: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    modified_after: str | None = None
    modified_before: str | None = None
    include_hidden: bool = False
    excluded_directories: tuple[str, ...] = ()
    time_range_type: str | None = None
    time_range_value: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_options(cls, name: str, options: SearchOptions, **kwargs: object) -> "SavedSearch":
        now = datetime.now().isoformat()
        return cls(
            str(uuid.uuid4()),
            name,
            options.query,
            options.match_mode.value,
            tuple(str(x) for x in options.search_paths),
            options.case_sensitive,
            options.fuzzy_threshold,
            options.extensions,
            options.min_size,
            options.max_size,
            options.modified_after.isoformat() if options.modified_after else None,
            options.modified_before.isoformat() if options.modified_before else None,
            options.include_hidden,
            options.excluded_directories,
            kwargs.get("time_range_type"),
            kwargs.get("time_range_value"),
            now,
            now,
        )

    def to_options(self, now: datetime | None = None) -> SearchOptions:
        current = now or datetime.now()
        after = datetime.fromisoformat(self.modified_after) if self.modified_after else None
        before = datetime.fromisoformat(self.modified_before) if self.modified_before else None
        if self.time_range_type == "relative_days":
            after, before = current - timedelta(days=self.time_range_value or 0), current
        if self.time_range_type == "relative_hours":
            after, before = current - timedelta(hours=self.time_range_value or 0), current
        return SearchOptions(
            self.query,
            tuple(Path(x) for x in self.search_paths),
            MatchMode(self.match_mode),
            self.case_sensitive,
            self.extensions,
            self.min_size,
            self.max_size,
            after,
            before,
            self.include_hidden,
            False,
            self.excluded_directories,
            self.fuzzy_threshold,
        )


class SavedSearchRepository:
    """JSON repository with corruption recovery and CRUD operations."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or saved_path()

    def load(self) -> list[SavedSearch]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return []
        values = []
        for item in raw if isinstance(raw, list) else []:
            try:
                values.append(SavedSearch(**item))
            except (TypeError, ValueError):
                continue
        return values

    def _write(self, values: list[SavedSearch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(x) for x in values], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create(self, value: SavedSearch) -> SavedSearch:
        self._write([value, *self.load()])
        return value

    def update(self, value: SavedSearch) -> None:
        self._write([value if x.id == value.id else x for x in self.load()])

    def rename(self, identifier: str, name: str) -> None:
        values = self.load()
        for value in values:
            if value.id == identifier:
                value.name = name
                value.updated_at = datetime.now().isoformat()
        self._write(values)

    def delete(self, identifier: str) -> None:
        self._write([x for x in self.load() if x.id != identifier])


SMART_RANGES = {
    "今天": ("relative_days", 1),
    "最近 24 小时": ("relative_hours", 24),
    "最近 7 天": ("relative_days", 7),
    "最近 30 天": ("relative_days", 30),
}
