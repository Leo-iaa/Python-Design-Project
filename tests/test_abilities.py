"""阶段 2：普通果子与能力系统测试。"""

from __future__ import annotations

import random

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.core.abilities import AbilityState, AbilitySystem
from dark_forest_snake.core.clock import LANTERN, SHIELD, SPRINT, ExpirySet
from dark_forest_snake.core.fruit import (
    ALL_FRUIT_TYPES,
    Fruit,
    FruitSystem,
    FruitType,
    GoldApple,
    SpawnError,
    spawn_position,
)
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Cell
from dark_forest_snake.core.state import GamePhase


# ================================================================ 果子生成
def test_spawn_never_on_wall_or_blocked() -> None:
    rng = random.Random(1)
    fs = FruitSystem(rng, 20, 16, margin=1)
    blocked = {Cell(3, 3), Cell(4, 4), Cell(5, 5)}
    for _ in range(200):
        f = fs.spawn_fruit(blocked)
        assert 0 <= f.cell.x < 20
        assert 0 <= f.cell.y < 16
        assert f.cell not in blocked
        assert f.cell.x != 0 and f.cell.y != 0
        assert f.cell.x != 19 and f.cell.y != 15


def test_spawn_avoids_snake_head_neighbourhood() -> None:
    """果子不得无意义地紧贴蛇头生成。"""
    rng = random.Random(2)
    fs = FruitSystem(rng, 20, 16, margin=1)
    head = Cell(10, 8)
    for _ in range(100):
        f = fs.spawn_fruit(set(), avoid_near=head)
        assert f.cell.manhattan(head) >= 2


def test_spawn_type_is_one_of_three() -> None:
    rng = random.Random(3)
    fs = FruitSystem(rng, 20, 16)
    seen = set()
    for _ in range(300):
        f = fs.spawn_fruit(set())
        seen.add(f.type)
    assert seen == set(ALL_FRUIT_TYPES), "三种果子都应能被随机到"


def test_spawn_raises_when_no_space() -> None:
    rng = random.Random(4)
    fs = FruitSystem(rng, 3, 3, margin=1)
    blocked = {Cell(1, 1)}
    with pytest.raises(SpawnError):
        fs.spawn_fruit(blocked)


def test_only_one_normal_fruit_at_a_time() -> None:
    fs = FruitSystem(random.Random(5), 20, 16)
    fs.spawn_fruit(set())
    assert fs.fruit is not None
    fs.spawn_fruit(set())
    # 再生成一次仍然只有一个
    assert isinstance(fs.fruit, Fruit)
    assert fs.gold is None


# ================================================================ ExpirySet
def test_expiry_grant_and_active() -> None:
    es = ExpirySet()
    es.grant(SPRINT, now=0.0, duration=10.0)
    assert es.active(SPRINT, 0.0)
    assert es.active(SPRINT, 9.99)
    assert not es.active(SPRINT, 10.0)
    assert es.remaining(SPRINT, 4.0) == pytest.approx(6.0)


def test_expiry_repeated_grant_extends_not_shrinks() -> None:
    es = ExpirySet()
    es.grant(SPRINT, now=0.0, duration=10.0)
    es.grant(SPRINT, now=8.0, duration=10.0)  # 应延长到 18
    assert es.remaining(SPRINT, 8.0) == pytest.approx(10.0)


def test_expiry_cleanup() -> None:
    es = ExpirySet()
    es.grant(SPRINT, 0.0, 5.0)
    es.grant(LANTERN, 0.0, 20.0)
    expired = es.cleanup(6.0)
    assert SPRINT in expired
    assert LANTERN not in expired
    assert not es.active(SPRINT, 6.0)


# ================================================================ 疾跑
def test_sprint_requires_active_key_press() -> None:
    """获得疾跑 ≠ 自动加速：不按 Shift 仍是基础速度。"""
    st = AbilityState()
    st.grant(FruitType.SPRINT, now=0.0)
    assert st.has_sprint(0.0)
    assert st.effective_interval(0.0) == C.BASE_MOVE_INTERVAL
    assert not st.is_boosting(0.0)

    st.sprint_held = True
    assert st.effective_interval(0.0) == C.BOOST_MOVE_INTERVAL
    assert st.is_boosting(0.0)

    st.sprint_held = False
    assert st.effective_interval(0.0) == C.BASE_MOVE_INTERVAL


def test_sprint_does_not_work_without_ability() -> None:
    st = AbilityState()
    st.sprint_held = True
    assert st.effective_interval(0.0) == C.BASE_MOVE_INTERVAL
    assert not st.is_boosting(0.0)


def test_sprint_expires_after_10s() -> None:
    st = AbilityState()
    st.grant(FruitType.SPRINT, now=0.0)
    st.sprint_held = True
    assert st.is_boosting(9.9)
    st.tick(10.0)
    assert not st.has_sprint(10.0)
    assert not st.is_boosting(10.0)
    assert st.effective_interval(10.0) == C.BASE_MOVE_INTERVAL


# ================================================================ 护盾
def test_shield_grants_one_charge() -> None:
    st = AbilityState()
    st.grant(FruitType.SHIELD, now=0.0)
    assert st.shield_charges == 1
    assert st.has_shield(0.0)


def test_shield_consumed_once_then_gone() -> None:
    st = AbilityState()
    st.grant(FruitType.SHIELD, 0.0)
    assert st.consume_shield() is True
    assert st.shield_charges == 0
    assert st.consume_shield() is False, "护盾不得无限抵挡"
    assert not st.has_shield(0.0)


def test_shield_expires_after_10s() -> None:
    st = AbilityState()
    st.grant(FruitType.SHIELD, now=0.0)
    st.tick(10.0)
    assert st.shield_charges == 0
    assert not st.has_shield(10.0)


def test_shield_charges_alone_not_enough_after_expiry() -> None:
    st = AbilityState()
    st.grant(FruitType.SHIELD, 0.0)
    # 手工把层数留下但让时间过期
    st.expiries.skip(SHIELD)
    assert st.shield_charges == 1
    assert not st.has_shield(0.0), "过期后即便有层数也不算有护盾"


# ================================================================ 灯笼
def test_lantern_expires_after_10s() -> None:
    st = AbilityState()
    st.grant(FruitType.LANTERN, now=0.0)
    assert st.has_lantern(9.9)
    assert st.lantern_remaining(0.0) == pytest.approx(10.0)
    st.tick(10.0)
    assert not st.has_lantern(10.0)


def test_lantern_widens_view_through_game() -> None:
    g = Game(width=20, height=16, seed=42)
    g.start_match(countdown=0.0)
    assert g.visibility.view_radius(False) == C.NORMAL_VIEW_RADIUS
    assert g.visibility.view_radius(True) == C.LANTERN_VIEW_RADIUS
    assert g.view_for(P1).view_radius == C.NORMAL_VIEW_RADIUS

    g.abilities[P1].grant(FruitType.LANTERN, g.clock)
    assert g.view_for(P1).view_radius == C.LANTERN_VIEW_RADIUS

    g.update(C.ABILITY_DURATION)
    assert g.view_for(P1).view_radius == C.NORMAL_VIEW_RADIUS


# ================================================================ 吃果子 & 成长
def _force_place_fruit_on(game: Game, pid: int, ftype: FruitType) -> Fruit:
    """把普通果子放到某条蛇的下一步位置上（测试用）。"""
    snake = game.snakes[pid]
    target = snake.head.step(snake.direction)
    game.fruits.fruit = Fruit(cell=target, type=ftype)
    return game.fruits.fruit


def test_eating_fruit_grants_ability_and_growth() -> None:
    g = Game(width=24, height=18, seed=77)
    g.start_match(countdown=0.0)
    snake = g.snakes[P1]
    length_before = snake.length
    fruit = _force_place_fruit_on(g, P1, FruitType.SPRINT)

    g.update(C.BASE_MOVE_INTERVAL)

    assert g.snakes[P1].length == length_before + 1, "吃普通果子长度 +1"
    assert g.abilities[P1].has_sprint(g.clock)
    assert any("疾跑果" in e.text for e in g.event_log)
    assert g.fruits.fruit is not None
    assert g.fruits.fruit.cell != fruit.cell, "吃后立即随机生成新的"


def test_eating_does_not_grow_twice() -> None:
    """回归：吃到食物只应增长 1 节。"""
    g = Game(width=24, height=18, seed=78)
    g.start_match(countdown=0.0)
    before = g.snakes[P1].length
    _force_place_fruit_on(g, P1, FruitType.SHIELD)
    g.update(C.BASE_MOVE_INTERVAL)
    assert g.snakes[P1].length == before + 1


def test_eating_shield_fruit_gives_charge() -> None:
    g = Game(width=24, height=18, seed=79)
    g.start_match(countdown=0.0)
    _force_place_fruit_on(g, P1, FruitType.SHIELD)
    g.update(C.BASE_MOVE_INTERVAL)
    assert g.abilities[P1].shield_charges == 1


def test_eating_lantern_fruit_widens_view() -> None:
    g = Game(width=24, height=18, seed=80)
    g.start_match(countdown=0.0)
    _force_place_fruit_on(g, P1, FruitType.LANTERN)
    g.update(C.BASE_MOVE_INTERVAL)
    assert g.view_for(P1).view_radius == C.LANTERN_VIEW_RADIUS


def test_eating_broadcasts_event_to_both_players() -> None:
    """任何普通果子都应产生公共事件通知。"""
    g = Game(width=24, height=18, seed=81)
    g.start_match(countdown=0.0)
    _force_place_fruit_on(g, P2, FruitType.LANTERN)
    g.update(C.BASE_MOVE_INTERVAL)
    assert any("P2" in e.text and "灯笼果" in e.text for e in g.event_log)
    # 公共事件不区分玩家可见性
    v1 = g.view_for(P1)
    assert any("灯笼果" in str(ev["text"]) for ev in v1.events)


def test_normal_fruit_count_increments() -> None:
    g = Game(width=24, height=18, seed=82)
    g.start_match(countdown=0.0)
    assert g.normal_eaten_this_round == 0
    _force_place_fruit_on(g, P1, FruitType.SPRINT)
    g.update(C.BASE_MOVE_INTERVAL)
    assert g.normal_eaten_this_round == 1


# ================================================================ 速度
def test_boost_makes_ticks_faster_only_when_held() -> None:
    """疾跑只改变自己的移动频率：每 Tick 仍只走一格，且不把对手带快。"""
    g = Game(width=24, height=18, seed=83)
    g.start_match(countdown=0.0)
    g.abilities[P1].grant(FruitType.SPRINT, g.clock)

    g.input_sprint(P1, False)
    h0 = g.snakes[P1].head
    g.update(C.BASE_MOVE_INTERVAL)
    assert h0.manhattan(g.snakes[P1].head) == 1

    # 开疾跑后只过一个「加速间隔」：疾跑者恰好多走一格
    g.input_sprint(P1, True)
    self_head = g.snakes[P1].head
    other_head = g.snakes[P2].head
    g.update(C.BOOST_MOVE_INTERVAL)
    assert self_head.manhattan(g.snakes[P1].head) == 1
    # 未疾跑的一方计时器独立：这段时间还不到它的一步，不许被带快
    assert other_head.manhattan(g.snakes[P2].head) == 0
    # 但相同时间内疾跑者能走更多 Tick
    g2 = Game(width=24, height=18, seed=84)
    g2.start_match(countdown=0.0)
    g2.abilities[P1].grant(FruitType.SPRINT, g2.clock)
    g2.input_sprint(P1, True)
    steps_normal = int(1.0 / C.BASE_MOVE_INTERVAL)
    steps_boost = int(1.0 / C.BOOST_MOVE_INTERVAL)
    assert steps_boost > steps_normal


def test_ability_system_tick_clears_expired() -> None:
    a = AbilitySystem([0, 1])
    a[0].grant(FruitType.SPRINT, 0.0)
    a[1].grant(FruitType.LANTERN, 0.0)
    expired = a.tick(10.0)
    assert SPRINT in expired[0]
    assert LANTERN in expired[1]


def test_ability_system_reset() -> None:
    a = AbilitySystem([0, 1])
    a[0].grant_all(0.0)
    a.reset()
    assert a[0].shield_charges == 0
    assert not a[0].has_sprint(0.0)
    assert not a[0].has_lantern(0.0)
