"""Lightweight CLI for scripted searches and GUI diagnostics."""

import argparse
from pathlib import Path

from advanced_file_finder.core.filters import normalize_extensions
from advanced_file_finder.core.models import MatchMode, SearchOptions
from advanced_file_finder.core.search_service import search


def run_cli() -> None:
    """Parse a query and print matching full paths."""
    parser = argparse.ArgumentParser(prog="advanced-file-finder")
    parser.add_argument("query", nargs="?", help="filename query")
    parser.add_argument("paths", nargs="*", type=Path, help="directories to search")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--exact", action="store_const", const=MatchMode.EXACT, dest="mode")
    group.add_argument("--glob", action="store_const", const=MatchMode.GLOB, dest="mode")
    group.add_argument("--regex", action="store_const", const=MatchMode.REGEX, dest="mode")
    parser.add_argument("--ext", default="")
    parser.add_argument("--min-size", type=int)
    parser.add_argument("--max-size", type=int)
    args = parser.parse_args()
    if not args.query:
        parser.print_help()
        return
    options = SearchOptions(
        args.query,
        tuple(args.paths or [Path.cwd()]),
        args.mode or MatchMode.PARTIAL,
        extensions=normalize_extensions(args.ext),
        min_size=args.min_size,
        max_size=args.max_size,
    )
    try:
        results, stats = search(options)
    except ValueError as error:
        parser.error(str(error))
        return
    for item in results:
        print(item.full_path)
    print(
        f"{stats.matches} matches; scanned {stats.files_scanned} files in {stats.elapsed_time:.2f}s"
    )
