"""阶段 2：果子系统专项测试。"""

from __future__ import annotations

import random

import pytest

from dark_forest_snake.core.fruit import (
    ALL_FRUIT_TYPES,
    Fruit,
    FruitSystem,
    FruitType,
    GoldApple,
    SpawnError,
    spawn_position,
)
from dark_forest_snake.core.geometry import Cell


def test_fruit_type_labels() -> None:
    assert FruitType.SPRINT.label == "疾跑果"
    assert FruitType.SHIELD.label == "护盾果"
    assert FruitType.LANTERN.label == "灯笼果"


def test_fruit_is_not_gold() -> None:
    f = Fruit(Cell(1, 1), FruitType.SPRINT)
    assert not f.is_gold
    g = GoldApple(Cell(2, 2))
    assert g.is_gold
    assert g.type == "gold"


def test_gold_is_hidden_target_not_normal_fruit() -> None:
    fs = FruitSystem(random.Random(1), 20, 16)
    fs.spawn_gold(set())
    assert fs.gold is not None
    assert fs.fruit is None
    assert fs.game_target == fs.gold.cell


def test_clear_fruit_and_gold() -> None:
    fs = FruitSystem(random.Random(2), 20, 16)
    fs.spawn_fruit(set())
    fs.spawn_gold(set())
    fs.clear_fruit()
    assert fs.fruit is None
    assert fs.gold is not None
    fs.clear_gold()
    assert fs.gold is None
    assert fs.game_target is None


def test_gold_spawns_far_from_heads() -> None:
    fs = FruitSystem(random.Random(3), 20, 16)
    head = Cell(10, 8)
    for _ in range(50):
        g = fs.spawn_gold(set(), avoid_near=head)
        assert g.cell.manhattan(head) >= 3


def test_occupied_reports_both() -> None:
    fs = FruitSystem(random.Random(4), 20, 16)
    fs.spawn_fruit(set())
    fs.spawn_gold(set())
    occ = fs.all_occupied()
    assert fs.fruit.cell in occ
    assert fs.gold.cell in occ
    assert len(occ) == 2


def test_spawn_respects_margin() -> None:
    rng = random.Random(5)
    for _ in range(100):
        c = spawn_position(rng, 20, 16, set(), margin=2)
        assert 2 <= c.x < 18
        assert 2 <= c.y < 14


def test_spawn_failure_then_fallback() -> None:
    """地图塞满时必须抛错而不是死循环。"""
    rng = random.Random(6)
    blocked = {Cell(x, y) for x in range(1, 4) for y in range(1, 3)}
    with pytest.raises(SpawnError):
        spawn_position(rng, 5, 4, blocked, margin=1)


def test_seeded_spawn_reproducible() -> None:
    a = [FruitSystem(random.Random(9), 20, 16).spawn_fruit(set()).cell for _ in range(1)]
    b = [FruitSystem(random.Random(9), 20, 16).spawn_fruit(set()).cell for _ in range(1)]
    assert a == b
