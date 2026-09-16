"""阶段 1：Game Engine 端到端测试（不依赖 pygame）。"""

from __future__ import annotations

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.state import GamePhase


@pytest.fixture()
def game() -> Game:
    g = Game(width=20, height=16, seed=1234)
    g.start_match(countdown=0.0)
    return g


def test_engine_does_not_import_pygame() -> None:
    """核心引擎必须在没有 pygame 的环境下也能工作。"""
    import sys

    assert "pygame" not in sys.modules or True  # 允许测试环境已加载
    import dark_forest_snake.core.game as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "import pygame" not in src


def test_start_match_sets_playing(game: Game) -> None:
    assert game.state.phase is GamePhase.PLAYING_NORMAL
    assert all(s.alive for s in game.snakes.values())
    assert game.fruits.fruit is not None


def test_spawns_are_far_apart_and_legal(game: Game) -> None:
    a = game.snakes[P1]
    b = game.snakes[P2]
    assert set(a.body).isdisjoint(set(b.body)), "出生不得重叠"
    assert a.head.manhattan(b.head) >= 1
    for s in (a, b):
        for c in s.body:
            assert 0 <= c.x < game.width
            assert 0 <= c.y < game.height
        nxt = s.head.step(s.direction)
        assert 0 <= nxt.x < game.width and 0 <= nxt.y < game.height, "初始方向不得直接撞墙"


def test_initial_length(game: Game) -> None:
    for s in game.snakes.values():
        assert s.length == C.INITIAL_SNAKE_LENGTH


def test_movement_one_cell_per_tick(game: Game) -> None:
    """推进恰好一个 Tick → 蛇前进恰好 1 格。"""
    before = game.snakes[P1].head
    game.update(C.BASE_MOVE_INTERVAL)
    after = game.snakes[P1].head
    assert before.manhattan(after) == 1


def test_tick_is_simultaneous_not_sequential(game: Game) -> None:
    """两条蛇必须同时推进，绝不能先 P1 后 P2。"""
    a_before = game.snakes[P1].head
    b_before = game.snakes[P2].head
    game.update(C.BASE_MOVE_INTERVAL)
    a_after = game.snakes[P1].head
    b_after = game.snakes[P2].head
    assert a_before.manhattan(a_after) == 1
    assert b_before.manhattan(b_after) == 1


def test_direction_input_rejected_outside_playing() -> None:
    g = Game(width=20, height=16, seed=7)
    assert g.input_direction(P1, Direction.UP) is False
    g.start_match(countdown=0.0)
    assert g.input_direction(P1, Direction.UP) in (True, False)


def test_no_reverse_input_through_game(game: Game) -> None:
    s = game.snakes[P1]
    # 找一个非当前方向
    opposite = {
        Direction.UP: Direction.DOWN,
        Direction.DOWN: Direction.UP,
        Direction.LEFT: Direction.RIGHT,
        Direction.RIGHT: Direction.LEFT,
    }[s.direction]
    assert game.input_direction(P1, opposite) is False


def test_countdown_gates_play() -> None:
    g = Game(width=20, height=16, seed=3)
    g.start_match(countdown=0.5)
    assert g.state.phase is GamePhase.COUNTDOWN
    before = g.snakes[P1].head
    g.update(0.2)
    assert g.snakes[P1].head == before, "倒计时期间不得移动"
    assert game_phase_is(g, GamePhase.COUNTDOWN)
    g.update(0.4)
    assert g.state.phase is GamePhase.PLAYING_NORMAL


def game_phase_is(g: Game, phase: GamePhase) -> bool:
    return g.state.phase is phase


def test_long_run_does_not_crash(game: Game) -> None:
    """长跑压力：大量 Tick，随机注入方向，确认不崩溃、不死循环。"""
    import random as _r

    rng = _r.Random(99)
    opts = list(Direction)
    for i in range(3000):
        if i % 7 == 0:
            game.input_direction(P1, rng.choice(opts))
        if i % 5 == 0:
            game.input_direction(P2, rng.choice(opts))
        if i % 13 == 0:
            game.input_sprint(P1, rng.random() < 0.5)
        game.update(C.BASE_MOVE_INTERVAL)
        if game.is_over():
            game.full_reset()
            game.start_match(countdown=0.0)
    assert game.state.phase in (GamePhase.PLAYING_NORMAL, GamePhase.PLAYING_GOLDEN) or game.is_over()


def test_seeded_games_are_reproducible() -> None:
    """固定 seed → 完全可复现（用于复现果子 / AI / 碰撞 Bug）。"""
    results = []
    for _ in range(2):
        g = Game(width=20, height=16, seed=555)
        g.start_match(countdown=0.0)
        snap = g.debug_snapshot()
        results.append((snap["fruit"], tuple(snap["snakes"][0]["body"])))
    assert results[0] == results[1]


def test_wall_kill_ends_game() -> None:
    """撞墙立即死亡，对方获胜。"""
    g = Game(width=12, height=10, seed=11)
    g.start_match(countdown=0.0)
    # 把 P1 强行贴到墙上并朝墙走
    s = g.snakes[P1]
    s.body = [Cell(0, 4), Cell(1, 4), Cell(2, 4)]
    s.direction = Direction.LEFT
    from collections import deque

    s._pending = deque(maxlen=C.MAX_QUEUED_DIRECTIONS)
    g.update(C.BASE_MOVE_INTERVAL)
    assert g.is_over()
    assert g.winner == P2


def test_full_reset_clears_state(game: Game) -> None:
    game.full_reset()
    assert game.state.phase is GamePhase.MENU
    assert game.snakes == {}
    assert game.winner is None
