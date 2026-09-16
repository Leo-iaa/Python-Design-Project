"""Stable relevance ranking for filename and future OCR matches."""

from datetime import datetime

from advanced_file_finder.core.models import SearchResult


def rank_results(results: list[SearchResult], now: datetime | None = None) -> list[SearchResult]:
    """Sort by name relevance first, with recency/name/path stable tie-breakers."""
    current = now or datetime.now()

    def key(item: SearchResult) -> tuple[float, float, str, str]:
        age_days = max(0.0, (current - item.modified_time).total_seconds() / 86400)
        recency = max(0.0, 100.0 - min(age_days, 100.0))
        combined = min(
            100.0,
            item.match_score * 0.85
            + recency * 0.10
            + (100.0 / (len(item.full_path.parts) + 1)) * 0.05,
        )
        return (
            -combined,
            -item.modified_time.timestamp(),
            item.name.casefold(),
            str(item.full_path).casefold(),
        )

    return sorted(results, key=key)
