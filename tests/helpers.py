"""共享测试工具。"""

from __future__ import annotations

from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.snake import Snake


def make_snake(
    cells: list[tuple[int, int]] | list[Cell],
    direction: Direction = Direction.RIGHT,
    name: str = "S",
) -> Snake:
    """按 (x, y) 列表或 Cell 列表构造蛇，第一个为蛇头。"""
    body = [c if isinstance(c, Cell) else Cell(*c) for c in cells]
    return Snake(body, direction, name=name)


def straight_body(
    head: tuple[int, int], length: int, direction: Direction = Direction.RIGHT
) -> list[tuple[int, int]]:
    """沿 direction 的反方向铺一条直线身体。"""
    hx, hy = head
    back = (
        Direction.UP
        if direction is Direction.DOWN
        else Direction.DOWN
        if direction is Direction.UP
        else Direction.RIGHT
        if direction is Direction.LEFT
        else Direction.LEFT
    )
    out = [(hx, hy)]
    for i in range(1, length):
        out.append((hx + back.dx * i, hy + back.dy * i))
    return out
