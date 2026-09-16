"""结算文案回归测试：撞死获胜不得显示"集齐 3 个金苹果"。"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from dark_forest_snake import config as C  # noqa: E402
from dark_forest_snake.core.game import P1, P2, Game  # noqa: E402
from dark_forest_snake.core.geometry import Cell, Direction  # noqa: E402
from dark_forest_snake.core.state import GamePhase  # noqa: E402
from dark_forest_snake.ui.menu import result_subtitle  # noqa: E402


def _force_play(g: Game) -> None:
    g.start_match(countdown=0.0)
    g.update(0.0)


def test_kill_win_shows_kill_subtitle() -> None:
    """P1 撞墙死 → P2 获胜（0 金苹果）→ 副标题必须是击杀，不是集苹果。"""
    g = Game(width=24, height=18, seed=61)
    _force_play(g)
    g.snakes[P1].body = [Cell(23, 12), Cell(22, 12), Cell(21, 12)]
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = [Cell(5, 5), Cell(4, 5), Cell(3, 5)]
    g.snakes[P2].direction = Direction.UP
    g.update(C.BASE_MOVE_INTERVAL + 0.01)

    assert g.state.phase is GamePhase.GAME_OVER
    assert g.winner == P2

    # 从 P1（败方）与 P2（胜方）两种视角看，文案都必须正确
    for pid in (P1, P2):
        view = g.view_for(pid).to_dict()
        sub = result_subtitle(P2, view)
        assert "击杀" in sub, f"P{pid + 1} 视角副标题错误: {sub}"
        assert "集齐" not in sub, f"撞死获胜却显示集苹果: {sub}"


def test_gold_win_shows_gold_subtitle() -> None:
    """真的集齐 3 个金苹果获胜时，才显示集苹果文案。"""
    g = Game(width=24, height=18, seed=62)
    _force_play(g)
    g.gold_counts[P1] = C.GOLD_TO_WIN  # 直接到位（引擎路径已有集成测试覆盖）
    g._end_game(winner=P1, reason="gold")

    view = g.view_for(P2).to_dict()
    sub = result_subtitle(P1, view)
    assert "集齐" in sub and "金苹果" in sub, f"集苹果获胜文案错误: {sub}"


def test_subtitle_handles_missing_view() -> None:
    """view 缺失时不崩溃，回退为击杀文案（金苹果数不可知则不乱说集齐）。"""
    sub = result_subtitle(P1, None)
    assert "击杀" in sub
    assert "集齐" not in sub


def test_engine_event_text_matches_win_reason() -> None:
    """引擎事件流本身也要区分：撞死获胜不应 emit 集苹果文案。"""
    g = Game(width=24, height=18, seed=63)
    _force_play(g)
    g.snakes[P1].body = [Cell(23, 12), Cell(22, 12), Cell(21, 12)]
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = [Cell(5, 5), Cell(4, 5), Cell(3, 5)]
    g.snakes[P2].direction = Direction.UP
    g.update(C.BASE_MOVE_INTERVAL + 0.01)

    texts = [e.text for e in g.event_log]
    assert any("P2 获胜" in t for t in texts), f"缺少获胜事件: {texts}"
    assert not any("集齐" in t for t in texts), f"撞死获胜却 emit 集苹果: {texts}"
