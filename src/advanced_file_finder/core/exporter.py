"""UTF-8 result exporters."""

import csv
import json
from pathlib import Path

from advanced_file_finder.core.models import SearchResult


def export_results(results: list[SearchResult], destination: Path, format_name: str) -> None:
    """Export results as CSV, JSON, or tab-separated text."""
    rows = [
        {
            "name": r.name,
            "full_path": str(r.full_path),
            "parent_path": str(r.parent_path),
            "extension": r.extension,
            "size": r.size,
            "modified_time": r.modified_time.isoformat(),
        }
        for r in results
    ]
    fmt = format_name.casefold()
    if fmt == "json":
        destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        with destination.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=rows[0].keys()
                if rows
                else ["name", "full_path", "parent_path", "extension", "size", "modified_time"],
            )
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "txt":
        destination.write_text("\n".join(row["full_path"] for row in rows), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported export format: {format_name}")
