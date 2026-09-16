"""Regression: 方向队列导致 plan 与 move 分叉，蛇头"方向变了却不动/落错格"。

根因（已修复）：
    ``Snake.plan_move()`` 用 ``effective_direction()``（返回**队列尾**），
    而 ``Snake.move()`` 用 ``_consume_direction()``（``popleft``，即**队列头**）。
    当一帧内压入 ≥2 个方向（AI 或玩家同帧连按），碰撞判定依据的格子与
    实际位移的格子就不一致：
      - 碰撞判定看了错误的格子 → 误杀 / 漏杀 / 误头对头
      - 玩家感觉"方向变了，但蛇头没按预期走"

修复：
    新增 ``_next_direction()``（队列头，move 的真实来源），
    让 ``next_head``/``plan_move`` 与 ``move`` 共用同一事实来源。

本文件只用项目真实类型：Cell / Direction / Snake / resolve_tick。
"""

from __future__ import annotations

from dark_forest_snake.core.collision import CollisionOutcome, resolve_tick
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.snake import Snake


def _snake(body: list[tuple[int, int]], direction: Direction, name: str = "S") -> Snake:
    return Snake([Cell(x, y) for (x, y) in body], direction, name=name)


# ================================================================ 用户指定的最小场景
def test_user_minimal_scenario_moves_down() -> None:
    """P1 body [(10,6),(10,5),(9,5)] direction DOWN → head 必须推进到 (10,7)。"""
    p1 = _snake([(10, 6), (10, 5), (9, 5)], Direction.DOWN, "P1")
    p2 = _snake([(28, 4), (29, 4), (30, 4)], Direction.LEFT, "P2")

    planned = p1.plan_move()
    assert planned == Cell(10, 7)

    report = resolve_tick(
        snakes={0: p1, 1: p2},
        planned_heads={0: planned, 1: p2.plan_move()},
        grow_flags={0: False, 1: False},
        shield_charges={0: 0, 1: 0},
        width=24,
        height=18,
    )
    res = report.results[0]
    assert res.outcome is CollisionOutcome.OK
    assert res.blocked is False, "正常移动不得被误判为 blocked"

    if not res.blocked:
        p1.move(grow=False)
    assert p1.head == Cell(10, 7)


# ================================================================ 队列分叉（本次根因）
def test_plan_and_move_agree_when_queue_nonempty() -> None:
    """压入多个方向后，plan_move 必须与 move 落到同一格（不允许分叉）。"""
    s = _snake([(10, 10), (9, 10), (8, 10)], Direction.RIGHT)
    assert s.enqueue_direction(Direction.UP)
    assert s.enqueue_direction(Direction.LEFT)

    planned = s.plan_move()
    actual = s.move()
    assert planned == actual, (
        f"plan 与 move 分叉：planned={planned} move={actual}。"
        "碰撞判定与实际位移落在不同格子上。"
    )


def test_plan_move_matches_imminent_tick_direction() -> None:
    """plan_move 必须反映**本 Tick**即将生效的方向（队列头），不是队列尾。

    蛇朝 RIGHT，压入 UP 再 LEFT。本 Tick 实际执行 UP（队列头）。
    若 plan 错用队列尾 LEFT，会给出 (9,10)；正确应为 (10,9)。
    """
    s = _snake([(10, 10), (9, 10), (8, 10)], Direction.RIGHT)
    s.enqueue_direction(Direction.UP)
    s.enqueue_direction(Direction.LEFT)

    assert s.plan_move() == Cell(10, 9), "plan_move 必须基于本 Tick 实际方向（队列头）"


def test_no_false_head_to_head_from_queue_drift() -> None:
    """队列漂移不得把 planned 头推到对方 planned 头同格，造成误头对头。

    修复前：A 压入 UP+LEFT 后 planned 错用队列尾 LEFT → (9,10)，
    恰好等于 B 的 planned (9,10)，被误判 head_to_head_draw。
    修复后：A planned 用队列头 UP → (10,9)，与 B 不同格，不误判。
    B 放在远处，朝与 A 无关的方向走，双方都不应死。
    """
    a = _snake([(10, 10), (9, 10), (8, 10)], Direction.RIGHT, "A")
    b = _snake([(20, 16), (21, 16), (22, 16)], Direction.UP, "B")
    a.enqueue_direction(Direction.UP)
    a.enqueue_direction(Direction.LEFT)

    report = resolve_tick(
        snakes={0: a, 1: b},
        planned_heads={0: a.plan_move(), 1: b.plan_move()},
        grow_flags={0: False, 1: False},
        shield_charges={0: 0, 1: 0},
        width=24,
        height=18,
    )
    assert report.head_to_head is False, (
        f"误头对头：planned A={a.plan_move()} B={b.plan_move()} events={report.events}"
    )
    assert report.head_to_head_draw is False
    assert report.results[0].outcome is not CollisionOutcome.DEAD
    assert report.results[1].outcome is not CollisionOutcome.DEAD


def test_collision_judged_on_actual_move_cell() -> None:
    """碰撞判定必须落在 move 真正会去的格子上（与 planned 一致）。"""
    # A 队列化后本 Tick 实际向上 (10,9)；若 plan 误用队列尾 LEFT 会去 (9,10)。
    a = _snake([(10, 10), (10, 11), (10, 12)], Direction.RIGHT, "A")
    a.enqueue_direction(Direction.UP)
    a.enqueue_direction(Direction.LEFT)

    # A 本 Tick 实际执行 UP → (10,9)。把 B 摆在 (10,9)，A 应撞 B（ENEMY_BODY）。
    b = _snake([(10, 9), (11, 9), (12, 9)], Direction.LEFT, "B")

    report = resolve_tick(
        snakes={0: a, 1: b},
        planned_heads={0: a.plan_move(), 1: b.plan_move()},
        grow_flags={0: False, 1: False},
        shield_charges={0: 0, 1: 0},
        width=24,
        height=18,
    )
    # A 实际去 (10,9)，正好是 B 的头 → 应判 A 撞敌身死亡
    assert report.results[0].outcome is CollisionOutcome.DEAD, (
        f"A 实际去 (10,9) 撞上 B，却判 {report.results[0].outcome}；"
        f"planned={a.plan_move()}（应为 (10,9)）"
    )


# ================================================================ 回归保护：正常路径不受影响
def test_single_queued_direction_still_moves_correctly() -> None:
    """只压一个方向时，plan 与 move 一致，且正常前进。"""
    s = _snake([(5, 5), (4, 5), (3, 5)], Direction.RIGHT)
    s.enqueue_direction(Direction.DOWN)
    assert s.plan_move() == Cell(5, 6)
    assert s.move() == Cell(5, 6)
    assert s.direction is Direction.DOWN


def test_reverse_input_directly_still_rejected() -> None:
    """修复不得破坏防反向：当前方向的 180° 反向仍必须被拒绝。"""
    s = _snake([(10, 10), (9, 10), (8, 10)], Direction.RIGHT)
    assert s.enqueue_direction(Direction.LEFT) is False
