from advanced_file_finder.core.matcher import match_score
from advanced_file_finder.core.models import MatchMode


def test_fuzzy_typo_and_threshold() -> None:
    assert match_score("report.pdf", "reprt", MatchMode.FUZZY)[0]
    assert match_score("MathModel", "mathmodle", MatchMode.FUZZY)[0]
    assert match_score("main.tex", "mainn", MatchMode.FUZZY)[0]
    assert not match_score("holiday.jpg", "mathmodle", MatchMode.FUZZY, threshold=75)[0]
    assert not match_score("report.pdf", "reprt", MatchMode.FUZZY, threshold=100)[0]


def test_fuzzy_unicode() -> None:
    assert match_score("数学建模.pdf", "数学建模", MatchMode.FUZZY)[0]
