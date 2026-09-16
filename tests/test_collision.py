"""阶段 1：核心引擎测试 —— 移动、成长、方向队列、碰撞、状态机。"""

from __future__ import annotations

import pytest

from dark_forest_snake.core.collision import (
    CollisionOutcome,
    CollisionSystem,
    DeathReason,
)
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.snake import Snake
from dark_forest_snake.core.state import GamePhase, GameStateMachine, InvalidTransition

from helpers import make_snake, straight_body

W, H = 20, 20


# ================================================================ 几何 / 方向
def test_opposite_detection() -> None:
    assert Direction.UP.is_opposite(Direction.DOWN)
    assert Direction.LEFT.is_opposite(Direction.RIGHT)
    assert not Direction.UP.is_opposite(Direction.LEFT)
    assert not Direction.UP.is_opposite(Direction.UP)


def test_cell_arithmetic() -> None:
    c = Cell(3, 4)
    assert c.step(Direction.RIGHT) == Cell(4, 4)
    assert c.step(Direction.UP) == Cell(3, 3)
    assert c.manhattan(Cell(5, 6)) == 4
    assert c.chebyshev(Cell(5, 6)) == 2
    assert c.as_tuple() == (3, 4)


# ================================================================ 蛇：移动
def test_move_advances_exactly_one_cell() -> None:
    """按一次键 → 位移恰好 1 格。防止一帧跨两格。"""
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    assert s.enqueue_direction(Direction.UP) is True
    before = s.head
    s.move()
    assert s.head.manhattan(before) == 1, "一次 move 必须只前进一格"
    assert s.head == Cell(5, 4)


def test_queued_direction_does_not_move() -> None:
    """登记意图绝不移动 —— 事件驱动循环的关键约束。"""
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    head_before = s.head
    s.enqueue_direction(Direction.UP)
    s.enqueue_direction(Direction.LEFT)
    assert s.head == head_before, "enqueue 不得改变位置"


def test_no_180_reversal() -> None:
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    assert s.enqueue_direction(Direction.LEFT) is False
    assert s.direction is Direction.RIGHT
    assert s.pending == ()


def test_two_key_press_same_frame_uses_queue_tail() -> None:
    """同帧连按 ↑ 再 ←（当前向右）必须都生效，且不出现瞬间掉头。"""
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    assert s.enqueue_direction(Direction.UP) is True
    assert s.enqueue_direction(Direction.LEFT) is True  # 相对队列尾 UP 是合法左转
    s.move()
    assert s.head == Cell(5, 4)
    s.move()
    assert s.head == Cell(4, 4)


def test_no_self_kill_from_double_fast_input() -> None:
    """防反向：向右时连按 ← 再 ↑，反向的 ← 被拒绝，只能转上。"""
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    assert s.enqueue_direction(Direction.LEFT) is False
    assert s.enqueue_direction(Direction.UP) is True
    s.move()
    assert s.head == Cell(5, 4)


def test_queue_capacity() -> None:
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    s.enqueue_direction(Direction.UP)
    s.enqueue_direction(Direction.LEFT)
    assert s.enqueue_direction(Direction.DOWN) is False  # 队列已满


# ================================================================ 蛇：成长
def test_growth_increases_length_and_keeps_tail() -> None:
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    original_tail = s.tail
    assert s.length == 3
    s.move(grow=True)
    assert s.length == 4
    assert s.tail == original_tail, "成长时不得删除蛇尾"


def test_normal_move_keeps_length() -> None:
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    s.move(grow=False)
    assert s.length == 3
    # 蛇头 (5,5) 沿 RIGHT 前进 → (6,5)；身体整体右移一格
    assert s.head == Cell(6, 5)
    assert s.tail == Cell(4, 5)


def test_grow_method() -> None:
    s = make_snake(straight_body((5, 5), 3), Direction.RIGHT)
    s.grow(2)
    assert s.length == 5


# ================================================================ 碰撞
def test_wall_death() -> None:
    cs = CollisionSystem(W, H)
    s = make_snake([(0, 5), (1, 5), (2, 5)], Direction.LEFT)
    report = cs.resolve({0: s}, {0: Cell(-1, 5)})
    assert report.died(0)
    assert report.results[0].reason is DeathReason.WALL


def test_wall_death_all_four_edges() -> None:
    cs = CollisionSystem(W, H)
    cases = [
        (Cell(0, 5), Cell(-1, 5)),
        (Cell(W - 1, 5), Cell(W, 5)),
        (Cell(5, 0), Cell(5, -1)),
        (Cell(5, H - 1), Cell(5, H)),
    ]
    for head, nxt in cases:
        s = make_snake([head, Cell(head.x, head.y)], Direction.RIGHT)
        report = cs.resolve({0: s}, {0: nxt})
        assert report.died(0), f"{nxt} 应为致死墙体"

def test_self_collision() -> None:
    cs = CollisionSystem(W, H)
    # 头向右，身体绕回
    s = make_snake([(5, 5), (4, 5), (4, 6), (5, 6), (6, 6)], Direction.RIGHT)
    report = cs.resolve({0: s}, {0: Cell(5, 6)})
    assert report.died(0)
    assert report.results[0].reason is DeathReason.SELF


def test_enemy_body_collision() -> None:
    cs = CollisionSystem(W, H)
    a = make_snake([(5, 5), (4, 5), (3, 5)], Direction.RIGHT)
    b = make_snake([(7, 5), (8, 5), (9, 5)], Direction.LEFT)
    report = cs.resolve({0: a, 1: b}, {0: Cell(7, 5), 1: Cell(6, 5)})
    assert report.died(0)
    assert report.results[0].reason is DeathReason.ENEMY_BODY


def test_following_enemy_tail_is_safe() -> None:
    """追尾：对方本 Tick 不成长，尾巴会腾空，追尾不算死。"""
    cs = CollisionSystem(W, H)
    a = make_snake([(4, 5), (3, 5), (2, 5)], Direction.RIGHT)
    b = make_snake([(7, 5), (6, 5), (5, 5)], Direction.RIGHT)
    # a 头移到 (5,5) —— 那是 b 的尾巴，b 前进后腾空
    report = cs.resolve({0: a, 1: b}, {0: Cell(5, 5), 1: Cell(8, 5)})
    assert not report.died(0), "追尾对方将腾空的尾巴不应致死"


def test_head_to_head_longer_wins() -> None:
    cs = CollisionSystem(W, H)
    a = make_snake([(5, 5), (4, 5), (3, 5), (2, 5)], Direction.RIGHT)  # len 4
    b = make_snake([(7, 5), (8, 5), (9, 5)], Direction.LEFT)           # len 3
    report = cs.resolve({0: a, 1: b}, {0: Cell(6, 5), 1: Cell(6, 5)})
    assert report.results[0].outcome is CollisionOutcome.OK
    assert report.died(1)
    assert report.results[1].reason is DeathReason.HEAD_TO_HEAD
    assert not report.head_to_head_draw


def test_head_to_head_equal_length_is_draw() -> None:
    cs = CollisionSystem(W, H)
    a = make_snake([(5, 5), (4, 5), (3, 5)], Direction.RIGHT)
    b = make_snake([(7, 5), (8, 5), (9, 5)], Direction.LEFT)
    report = cs.resolve({0: a, 1: b}, {0: Cell(6, 5), 1: Cell(6, 5)})
    assert report.head_to_head_draw
    assert report.both_dead


def test_both_dead_from_two_walls_is_draw() -> None:
    cs = CollisionSystem(W, H)
    a = make_snake([(0, 5), (1, 5), (2, 5)], Direction.LEFT)
    b = make_snake([(W - 1, 5), (W - 2, 5), (W - 3, 5)], Direction.RIGHT)
    report = cs.resolve(
        {0: a, 1: b}, {0: Cell(-1, 5), 1: Cell(W, 5)}
    )
    assert report.both_dead


def test_simultaneous_tick_is_order_independent() -> None:
    """同步判定：无论 pid 顺序如何，结果必须完全一致。"""
    cs = CollisionSystem(W, H)
    a_body = [(5, 5), (4, 5), (3, 5)]
    b_body = [(7, 5), (8, 5), (9, 5)]
    r1 = cs.resolve(
        {0: make_snake(a_body, Direction.RIGHT), 1: make_snake(b_body, Direction.LEFT)},
        {0: Cell(6, 5), 1: Cell(6, 5)},
    )
    r2 = cs.resolve(
        {1: make_snake(b_body, Direction.LEFT), 0: make_snake(a_body, Direction.RIGHT)},
        {1: Cell(6, 5), 0: Cell(6, 5)},
    )
    assert r1.head_to_head_draw == r2.head_to_head_draw
    assert r1.results[0].outcome == r2.results[0].outcome
    assert r1.results[1].outcome == r2.results[1].outcome


def test_shield_blocks_one_lethal_hit() -> None:
    cs = CollisionSystem(W, H)
    s = make_snake([(0, 5), (1, 5), (2, 5)], Direction.LEFT)
    report = cs.resolve({0: s}, {0: Cell(-1, 5)}, shield_charges={0: 1})
    assert report.results[0].outcome is CollisionOutcome.SHIELDED
    assert report.results[0].shield_consumed
    assert not report.died(0)


def test_shield_only_once_without_charges() -> None:
    """护盾只剩 0 层时，第二次撞击必然死亡。"""
    cs = CollisionSystem(W, H)
    s = make_snake([(0, 5), (1, 5), (2, 5)], Direction.LEFT)
    r1 = cs.resolve({0: s}, {0: Cell(-1, 5)}, shield_charges={0: 0})
    assert r1.died(0)


def test_shield_saves_short_snake_in_head_to_head() -> None:
    """短蛇有盾 → 头对头不死，双方各自回弹。"""
    cs = CollisionSystem(W, H)
    a = make_snake([(5, 5), (4, 5)], Direction.RIGHT)          # len 2
    b = make_snake([(7, 5), (8, 5), (9, 5)], Direction.LEFT)   # len 3
    report = cs.resolve(
        {0: a, 1: b}, {0: Cell(6, 5), 1: Cell(6, 5)}, shield_charges={0: 1}
    )
    assert not report.died(0), "短蛇有护盾应能活下来"
    assert report.results[0].shield_consumed
    assert not report.died(1)


def test_equal_length_head_to_head_draw_even_with_shield() -> None:
    """等长头对头按规则必须平局重开，护盾不改写该结果。"""
    cs = CollisionSystem(W, H)
    a = make_snake([(5, 5), (4, 5), (3, 5)], Direction.RIGHT)
    b = make_snake([(7, 5), (8, 5), (9, 5)], Direction.LEFT)
    report = cs.resolve(
        {0: a, 1: b}, {0: Cell(6, 5), 1: Cell(6, 5)}, shield_charges={0: 1, 1: 1}
    )
    assert report.head_to_head_draw
    assert report.both_dead


def test_shield_does_not_double_consume() -> None:
    """同一 Tick 内不会消耗两层护盾。"""
    cs = CollisionSystem(W, H)
    s = make_snake([(0, 5), (1, 5), (2, 5)], Direction.LEFT)
    shield = {0: 1}
    report = cs.resolve({0: s}, {0: Cell(-1, 5)}, shield_charges=shield)
    assert report.results[0].shield_consumed
    assert shield[0] == 1, "resolve 不得修改入参"


# ================================================================ 状态机
def test_state_machine_valid_path() -> None:
    sm = GameStateMachine(GamePhase.MENU)
    sm.transition(GamePhase.COUNTDOWN)
    sm.transition(GamePhase.PLAYING_NORMAL)
    sm.transition(GamePhase.PLAYING_GOLDEN)
    sm.transition(GamePhase.GAME_OVER, winner=0, reason="gold")
    assert sm.phase is GamePhase.GAME_OVER
    assert sm.winner == 0


def test_state_machine_rejects_invalid() -> None:
    sm = GameStateMachine(GamePhase.MENU)
    with pytest.raises(InvalidTransition):
        sm.transition(GamePhase.GAME_OVER)


def test_state_machine_phase_helpers() -> None:
    sm = GameStateMachine(GamePhase.PLAYING_NORMAL)
    assert sm.phase.is_playing
    assert not sm.phase.is_finished
    sm.transition(GamePhase.GAME_OVER)
    assert sm.phase.is_finished
    assert not sm.phase.is_playing


def test_state_machine_history() -> None:
    sm = GameStateMachine(GamePhase.MENU)
    sm.transition(GamePhase.COUNTDOWN)
    sm.transition(GamePhase.PLAYING_NORMAL)
    assert sm.history == [
        GamePhase.MENU,
        GamePhase.COUNTDOWN,
        GamePhase.PLAYING_NORMAL,
    ]
