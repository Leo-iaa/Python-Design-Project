from pathlib import Path

from advanced_file_finder.core.models import MatchMode, SearchOptions
from advanced_file_finder.core.search_service import search


def test_all_filename_modes_regression(tmp_path: Path) -> None:
    for name in ("report.pdf", "report_final.pdf", "main.tex"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert (
        search(SearchOptions("report.pdf", (tmp_path,), MatchMode.EXACT))[0][0].name == "report.pdf"
    )
    assert len(search(SearchOptions("report", (tmp_path,), MatchMode.PARTIAL))[0]) == 2
    assert search(SearchOptions("*.tex", (tmp_path,), MatchMode.GLOB))[0][0].name == "main.tex"
    assert search(SearchOptions(r"^main", (tmp_path,), MatchMode.REGEX))[0][0].name == "main.tex"
    assert search(SearchOptions("reprt", (tmp_path,), MatchMode.FUZZY))[0][0].name == "report.pdf"
