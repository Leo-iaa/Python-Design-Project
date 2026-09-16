"""网格坐标与方向。纯数据，不依赖任何渲染库。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """四方向。value 为 (dx, dy)，y 轴向下为正。"""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def delta(self) -> tuple[int, int]:
        return self.value

    def is_opposite(self, other: "Direction") -> bool:
        """是否为 180° 反向。反向输入必须被拒绝。"""
        return self.dx + other.dx == 0 and self.dy + other.dy == 0

    def turn_left(self) -> "Direction":
        return _LEFT_OF[self]

    def turn_right(self) -> "Direction":
        return _RIGHT_OF[self]


_LEFT_OF = {
    Direction.UP: Direction.LEFT,
    Direction.LEFT: Direction.DOWN,
    Direction.DOWN: Direction.RIGHT,
    Direction.RIGHT: Direction.UP,
}

_RIGHT_OF = {
    Direction.UP: Direction.RIGHT,
    Direction.RIGHT: Direction.DOWN,
    Direction.DOWN: Direction.LEFT,
    Direction.LEFT: Direction.UP,
}


@dataclass(frozen=True, slots=True)
class Cell:
    """网格格子坐标。不可变，可直接作 dict key。"""

    x: int
    y: int

    def step(self, direction: Direction) -> "Cell":
        return Cell(self.x + direction.dx, self.y + direction.dy)

    def offset(self, dx: int, dy: int) -> "Cell":
        return Cell(self.x + dx, self.y + dy)

    def manhattan(self, other: "Cell") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def chebyshev(self, other: "Cell") -> int:
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def as_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)

    def __repr__(self) -> str:  # pragma: no cover - 调试友好
        return f"Cell({self.x},{self.y})"


def manhattan(a: Cell, b: Cell) -> int:
    return a.manhattan(b)


def chebyshev(a: Cell, b: Cell) -> int:
    return a.chebyshev(b)
