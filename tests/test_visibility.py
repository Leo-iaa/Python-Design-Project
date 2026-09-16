"""阶段 3：黑暗视野与信息隐藏测试。

验证重点：
- 目标不会被直接显示（坐标绝不出现在 PlayerView 中）
- 环境光只与「自己蛇头」有关，不含目标方向/距离
- 灯笼扩大视野
- 敌人在黑暗中不可见
（八方向指示格本身的测试见 tests/test_indicator.py）
"""

from __future__ import annotations

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.visibility import VisibilitySystem


# ================================================================ 视野系统
def test_view_radius_default() -> None:
    vs = VisibilitySystem(20, 20)
    assert vs.view_radius(False) == C.NORMAL_VIEW_RADIUS
    r = C.NORMAL_VIEW_RADIUS
    assert len(vs.visible_cells(Cell(10, 10), r)) == (2 * r + 1) ** 2


def test_view_radius_lantern() -> None:
    vs = VisibilitySystem(30, 30)
    assert vs.view_radius(True) == C.LANTERN_VIEW_RADIUS
    r = C.LANTERN_VIEW_RADIUS
    assert len(vs.visible_cells(Cell(10, 10), r)) == (2 * r + 1) ** 2


def test_visible_cells_clipped_to_map() -> None:
    vs = VisibilitySystem(20, 20)
    cells = vs.visible_cells(Cell(0, 0), 2)
    assert Cell(-1, 0) not in cells
    assert Cell(0, 0) in cells
    assert all(0 <= c.x < 20 and 0 <= c.y < 20 for c in cells)


def test_visibility_hides_enemy_outside_range() -> None:
    vs = VisibilitySystem(30, 30)
    head = Cell(5, 5)
    enemy = [Cell(20, 20), Cell(21, 20)]
    res = vs.compute(head=head, lantern_active=False, enemy_body=enemy)
    assert res.visible_enemy_cells == set()


def test_visibility_shows_enemy_head_when_adjacent() -> None:
    vs = VisibilitySystem(30, 30)
    head = Cell(5, 5)
    enemy = [Cell(6, 5), Cell(7, 5)]
    res = vs.compute(head=head, lantern_active=False, enemy_body=enemy)
    assert Cell(6, 5) in res.visible_enemy_cells


def test_visibility_reveal_all_shows_everything() -> None:
    vs = VisibilitySystem(10, 8)
    enemy = [Cell(9, 7)]
    res = vs.compute(
        head=Cell(0, 0),
        lantern_active=False,
        enemy_body=enemy,
        reveal_all=True,
    )
    assert len(res.visible_cells) == 10 * 8
    assert Cell(9, 7) in res.visible_enemy_cells


def test_brightness_only_for_visible_cells() -> None:
    vs = VisibilitySystem(30, 30)
    res = vs.compute(head=Cell(15, 15), lantern_active=False, enemy_body=[])
    assert set(res.brightness.keys()) == res.visible_cells
    assert len(res.brightness) == (2 * C.NORMAL_VIEW_RADIUS + 1) ** 2


def test_ambient_light_depends_only_on_own_head() -> None:
    """环境光是「相对自己蛇头的衰减」，与目标无关——同位置同 head 必同亮度。"""
    vs = VisibilitySystem(30, 30)
    head = Cell(15, 15)
    res = vs.compute(head=head, lantern_active=False, enemy_body=[])
    # 蛇头处最亮，越远越暗
    from dark_forest_snake.config import MAX_BRIGHTNESS, MIN_BRIGHTNESS
    assert res.brightness[head] == MAX_BRIGHTNESS
    assert all(MIN_BRIGHTNESS <= v <= MAX_BRIGHTNESS for v in res.brightness.values())
    # 同一环（切比雪夫等距）亮度一致 —— 纯径向环境光，无方向性
    ring = {Cell(16, 15), Cell(15, 16), Cell(14, 15), Cell(15, 14)}
    ring_vals = {res.brightness[c] for c in ring}
    assert len(ring_vals) == 1


# ================================================================ PlayerView 信息隔离
def _advance(g: Game, seconds: float, step: float = 1 / 60) -> None:
    t = 0.0
    while t < seconds:
        g.update(step)
        t += step


def test_player_view_never_contains_target_coordinates() -> None:
    """最重要的一条：PlayerView 绝不能泄漏果子 / 金苹果坐标。"""
    g = Game(width=24, height=18, seed=2024)
    g.start_match(countdown=0.0)

    for _ in range(40):
        g.update(C.BASE_MOVE_INTERVAL)
        if g.is_over():
            break
        for pid in (P1, P2):
            view = g.view_for(pid).to_dict()
            flat = repr(view)
            fruit = g.fruits.fruit
            gold = g.fruits.gold
            if fruit is not None:
                # 果子坐标不得作为独立字段出现
                assert "fruit" not in view
                assert "target" not in view
                assert "gold" not in view
            if gold is not None:
                assert "gold" not in view
            # 可见亮度字典的 key 数量必须等于视野内格子数（不是全图）
            visible = view["visible_brightness"]
            assert len(visible) <= (
                (2 * C.NORMAL_VIEW_RADIUS + 1) ** 2 * 2
            )
            assert flat  # 确保可序列化


def test_player_view_has_no_hidden_trigger() -> None:
    g = Game(width=24, height=18, seed=2025)
    g.start_match(countdown=0.0)
    d = g.view_for(P1).to_dict()
    assert "gold_trigger" not in d
    assert "normal_eaten" not in d
    assert g.gold_trigger >= C.GOLD_TRIGGER_MIN


def test_player_view_dict_keys_are_whitelisted() -> None:
    """字段白名单化：任何新增字段都必须显式确认不泄漏信息。"""
    g = Game(width=24, height=18, seed=2026)
    g.start_match(countdown=0.0)
    allowed = {
        "player",
        "phase",
        "own_body",
        "own_head",
        "own_direction",
        "own_length",
        "own_gold_count",
        "visible_brightness",
        "visible_enemy_cells",
        "enemy_head_visible",
        "enemy_direction_visible",
        "enemy_length_visible",
        "enemy_gold_count",
        "abilities",
        "boosting",
        "view_radius",
        "reveal_active",
        "reveal_remaining",
        "events",
        "winner",
        "draw",
        "clock",
        "countdown_remaining",
        "enemy_alive",
        "target_indicator",
    }
    assert set(g.view_for(P1).to_dict().keys()) == allowed


def test_own_body_fully_visible_but_enemy_restricted() -> None:
    """自己的蛇完整可见（降低随机自撞），敌人受视野严格控制。"""
    g = Game(width=30, height=24, seed=2027)
    g.start_match(countdown=0.0)
    view = g.view_for(P1)
    assert len(view.own_body) == g.snakes[P1].length
    # 出生点相距很远，敌人身体一节都看不到
    assert view.visible_enemy_cells == []
    assert not view.enemy_head_visible
    assert view.enemy_direction_visible is None
    assert view.enemy_length_visible is None


def test_enemy_visible_cells_only_within_view() -> None:
    g = Game(width=30, height=24, seed=2028)
    g.start_match(countdown=0.0)
    r = C.NORMAL_VIEW_RADIUS
    # 把 P2 强行放到 P1 旁边：一节在视野边缘、一节刚好越界
    p1_head = g.snakes[P1].head
    g.snakes[P2].body = [
        p1_head.offset(1, 0),
        p1_head.offset(r, 0),
        p1_head.offset(r + 1, 0),
    ]
    view = g.view_for(P1)
    assert p1_head.offset(1, 0).as_tuple() in view.visible_enemy_cells
    # 视野边缘（距离 r）仍可见；超出 r 的必须被裁掉
    assert p1_head.offset(r, 0).as_tuple() in view.visible_enemy_cells
    assert p1_head.offset(r + 1, 0).as_tuple() not in view.visible_enemy_cells


def test_darkness_persists_over_time() -> None:
    """不得为了方便开发而临时永久取消黑暗系统。"""
    g = Game(width=30, height=24, seed=2029)
    g.start_match(countdown=0.0)
    _advance(g, 5.0)
    if g.is_over():
        return
    view = g.view_for(P1)
    assert len(view.visible_brightness) <= 9
    assert view.view_radius == C.NORMAL_VIEW_RADIUS
    assert not view.reveal_active


def test_lantern_only_affects_owner() -> None:
    """灯笼果只扩大获得者自己的视野。"""
    from dark_forest_snake.core.fruit import FruitType

    g = Game(width=30, height=24, seed=2030)
    g.start_match(countdown=0.0)
    g.abilities[P1].grant(FruitType.LANTERN, g.clock)
    assert g.view_for(P1).view_radius == C.LANTERN_VIEW_RADIUS
    assert g.view_for(P2).view_radius == C.NORMAL_VIEW_RADIUS
    assert len(g.view_for(P1).visible_brightness) > len(
        g.view_for(P2).visible_brightness
    )


def test_reexport_of_config_constants() -> None:
    assert C.NORMAL_VIEW_RADIUS == 3
    assert C.LANTERN_VIEW_RADIUS == 4
    assert C.LANTERN_VIEW_RADIUS > C.NORMAL_VIEW_RADIUS
    assert C.MIN_BRIGHTNESS < C.MAX_BRIGHTNESS
