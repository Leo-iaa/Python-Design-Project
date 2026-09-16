"""Benchmark real temporary trees; reports actual timings without targets."""

import argparse
import time
from pathlib import Path

from advanced_file_finder.core.models import MatchMode, SearchOptions
from advanced_file_finder.core.search_service import search


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    a = p.parse_args()
    rows = []
    for mode, query in (
        (MatchMode.EXACT, "report_000001.txt"),
        (MatchMode.PARTIAL, "report"),
        (MatchMode.GLOB, "report_*.txt"),
        (MatchMode.REGEX, r"^report_"),
        (MatchMode.FUZZY, "reprt"),
    ):
        started = time.perf_counter()
        results, stats = search(SearchOptions(query, (a.root,), mode))
        elapsed = time.perf_counter() - started
        rows.append(
            (
                mode.value,
                stats.files_scanned,
                len(results),
                elapsed,
                stats.files_scanned / elapsed if elapsed else 0,
            )
        )
        print(
            f"{mode.value}: files={stats.files_scanned} results={len(results)} elapsed={elapsed:.3f}s files/sec={stats.files_scanned / elapsed if elapsed else 0:.0f}"
        )
    report = Path(".local/reports")
    report.mkdir(parents=True, exist_ok=True)
    (report / "file_search_benchmark.md").write_text(
        "# File Search Benchmark\n\n"
        + "\n".join(
            f"- {mode}: {files} files, {results} results, {elapsed:.3f}s, {rate:.0f} files/sec"
            for mode, files, results, elapsed, rate in rows
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
