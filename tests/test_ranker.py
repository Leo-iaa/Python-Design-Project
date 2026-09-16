from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import SearchResult
from advanced_file_finder.core.ranker import rank_results


def test_exact_score_ranks_first(tmp_path: Path) -> None:
    now = datetime.now()
    low = SearchResult(
        "monthly_report.pdf", tmp_path / "monthly_report.pdf", tmp_path, ".pdf", 1, now, 82
    )
    high = SearchResult("report.pdf", tmp_path / "report.pdf", tmp_path, ".pdf", 1, now, 100)
    assert rank_results([low, high])[0].name == "report.pdf"


def test_stable_tie_break(tmp_path: Path) -> None:
    now = datetime.now()
    values = [
        SearchResult("b.txt", tmp_path / "b.txt", tmp_path, ".txt", 1, now, 80),
        SearchResult("a.txt", tmp_path / "a.txt", tmp_path, ".txt", 1, now, 80),
    ]
    assert [x.name for x in rank_results(values)] == ["a.txt", "b.txt"]
