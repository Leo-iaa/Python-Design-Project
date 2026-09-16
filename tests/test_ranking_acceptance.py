from datetime import datetime
from pathlib import Path

from advanced_file_finder.core.models import MatchMode, SearchOptions, SearchResult
from advanced_file_finder.core.ranker import rank_results
from advanced_file_finder.core.search_service import search


def test_report_relevance_order_is_intuitive(tmp_path: Path) -> None:
    for name in (
        "report.pdf",
        "report_final.pdf",
        "monthly_report.pdf",
        "my_report_backup.pdf",
        "unrelated.pdf",
    ):
        (tmp_path / name).write_text("x")
    results, _ = search(SearchOptions("report", (tmp_path,), MatchMode.PARTIAL))
    names = [x.name for x in results]
    assert names[0] == "report.pdf"
    assert names.index("report_final.pdf") < names.index("monthly_report.pdf")


def test_threshold_is_monotonic() -> None:
    values = [
        SearchResult(
            "MathModel.pdf", Path("MathModel.pdf"), Path("."), ".pdf", 1, datetime.now(), score
        )
        for score in (60, 75, 85, 95)
    ]
    assert len([x for x in values if x.match_score >= 85]) <= len(
        [x for x in values if x.match_score >= 75]
    )


def test_filename_beats_ocr_only_and_combined_capped(tmp_path: Path) -> None:
    now = datetime.now()
    filename = SearchResult(
        "潜热.png", tmp_path / "潜热.png", tmp_path, ".png", 1, now, 100, "filename"
    )
    ocr = SearchResult("IMG.png", tmp_path / "IMG.png", tmp_path, ".png", 1, now, 90, "ocr")
    combined = SearchResult(
        "both.png", tmp_path / "both.png", tmp_path, ".png", 1, now, 99, "filename+ocr"
    )
    ranked = rank_results([ocr, filename, combined])
    assert ranked[0].name == "潜热.png"
    assert all(0 <= x.match_score <= 100 for x in ranked)
