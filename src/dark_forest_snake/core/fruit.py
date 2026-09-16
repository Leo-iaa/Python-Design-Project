"""果子：普通彩色果子（场上同时只有 1 个）+ 金苹果（隐藏）。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from dark_forest_snake.core.geometry import Cell


class FruitType(str, Enum):
    SPRINT = "sprint"    # 青色 · 疾跑果
    SHIELD = "shield"    # 紫色 · 护盾果
    LANTERN = "lantern"  # 蓝色 · 灯笼果

    @property
    def label(self) -> str:
        return {
            FruitType.SPRINT: "疾跑果",
            FruitType.SHIELD: "护盾果",
            FruitType.LANTERN: "灯笼果",
        }[self]


ALL_FRUIT_TYPES: tuple[FruitType, ...] = (
    FruitType.SPRINT,
    FruitType.SHIELD,
    FruitType.LANTERN,
)


@dataclass(frozen=True, slots=True)
class Fruit:
    cell: Cell
    type: FruitType

    @property
    def is_gold(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class GoldApple:
    """金苹果。同样不可直接显示，只能靠亮度寻找。"""

    cell: Cell

    @property
    def type(self) -> str:
        return "gold"

    @property
    def is_gold(self) -> bool:
        return True


class SpawnError(RuntimeError):
    pass


def spawn_position(
    rng: random.Random,
    width: int,
    height: int,
    blocked: set[Cell],
    *,
    avoid_near: Cell | None = None,
    min_avoid_distance: int = 2,
    margin: int = 1,
) -> Cell:
    """在合法格中随机取一个位置。

    非法格：墙上、蛇身上、以及（可选）紧贴某点的格子。
    ``avoid_near`` 通常传蛇头，避免果子无意义地贴在嘴边生成。
    """
    candidates: list[Cell] = []
    for x in range(margin, width - margin):
        for y in range(margin, height - margin):
            c = Cell(x, y)
            if c in blocked:
                continue
            if avoid_near is not None and c.manhattan(avoid_near) < min_avoid_distance:
                continue
            candidates.append(c)

    if not candidates:
        # 退化：放宽 avoid_near 限制再试
        for x in range(margin, width - margin):
            for y in range(margin, height - margin):
                c = Cell(x, y)
                if c not in blocked:
                    candidates.append(c)
    if not candidates:
        raise SpawnError("没有可用的出生格")
    return rng.choice(candidates)


class FruitSystem:
    """管理普通果子与金苹果的生成。规则层不做任何渲染假设。"""

    def __init__(
        self,
        rng: random.Random,
        width: int,
        height: int,
        *,
        margin: int = 1,
    ) -> None:
        self.rng = rng
        self.width = width
        self.height = height
        self.margin = margin
        self.fruit: Fruit | None = None
        self.gold: GoldApple | None = None

    # ------------------------------------------------------------ 普通果子
    def spawn_fruit(
        self,
        blocked: set[Cell],
        *,
        avoid_near: Cell | None = None,
    ) -> Fruit:
        cell = spawn_position(
            self.rng,
            self.width,
            self.height,
            blocked,
            avoid_near=avoid_near,
            min_avoid_distance=2,
            margin=self.margin,
        )
        ftype = self.rng.choice(ALL_FRUIT_TYPES)
        self.fruit = Fruit(cell=cell, type=ftype)
        return self.fruit

    def spawn_fruit_of_type(
        self,
        ftype: FruitType,
        blocked: set[Cell],
        *,
        avoid_near: Cell | None = None,
    ) -> Fruit:
        cell = spawn_position(
            self.rng,
            self.width,
            self.height,
            blocked,
            avoid_near=avoid_near,
            min_avoid_distance=2,
            margin=self.margin,
        )
        self.fruit = Fruit(cell=cell, type=ftype)
        return self.fruit

    def clear_fruit(self) -> None:
        self.fruit = None

    # ------------------------------------------------------------ 金苹果
    def spawn_gold(self, blocked: set[Cell], *, avoid_near: Cell | None = None) -> GoldApple:
        cell = spawn_position(
            self.rng,
            self.width,
            self.height,
            blocked,
            avoid_near=avoid_near,
            min_avoid_distance=3,
            margin=self.margin,
        )
        self.gold = GoldApple(cell=cell)
        return self.gold

    def clear_gold(self) -> None:
        self.gold = None

    # ------------------------------------------------------------ 查询
    @property
    def game_target(self) -> Cell | None:
        """当前场上唯一争夺目标的坐标（内部用；绝不直接发给客户端）。"""
        if self.gold is not None:
            return self.gold.cell
        if self.fruit is not None:
            return self.fruit.cell
        return None

    def all_occupied(self) -> set[Cell]:
        out: set[Cell] = set()
        if self.fruit is not None:
            out.add(self.fruit.cell)
        if self.gold is not None:
            out.add(self.gold.cell)
        return out
