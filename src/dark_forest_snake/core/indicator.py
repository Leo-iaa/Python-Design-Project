"""八方向目标指示格（navigation indicator）。

本模块是玩家找目标的**唯一**方向线索：

- 蛇头周围 8 个相邻格中，恰好 1 格作为「方向提示格」发光。
- 方向由 ``sign(dx) / sign(dy)`` 量化而来，全系统只有 8 个方向：
  N / NE / E / SE / S / SW / W / NW。
- 提示格只表达「目标大致在那个方向」，**不含距离、坐标、扇区角度**。
- 提示格距蛇头恒为 1 格：灯笼扩大视野不会把它推到第二圈。

信息边界：本模块的输入 target 只存在于服务器 / Game Engine 内部；
对外（PlayerViewState / 网络消息 / AI 感知）只传递量化后的
``(sx, sy)`` 或据此算出的提示格，客户端无法反推目标坐标。

注意坐标系：y 轴向下为正（与 Direction 一致），因此
``(0, -1)`` 是 N（上），``(0, 1)`` 是 S（下）。
"""

from __future__ import annotations

from dark_forest_snake.core.geometry import Cell

# (sx, sy) -> 方向名。y 向下为正，所以 (0,-1) 是 N。
INDICATOR_NAMES: dict[tuple[int, int], str] = {
    (0, -1): "N",
    (1, -1): "NE",
    (1, 0): "E",
    (1, 1): "SE",
    (0, 1): "S",
    (-1, 1): "SW",
    (-1, 0): "W",
    (-1, -1): "NW",
}

# 反向映射：方向名 -> (sx, sy)
INDICATOR_DELTAS: dict[str, tuple[int, int]] = {v: k for k, v in INDICATOR_NAMES.items()}


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


def indicator_direction(head: Cell, target: Cell) -> tuple[int, int]:
    """目标相对蛇头的八方向量化向量 (sx, sy)，分量 ∈ {-1, 0, 1}。

    只取符号：无论目标多远，同方向的返回值完全一致——
    这正是「不透露距离」的实现方式。
    """
    return (_sign(target.x - head.x), _sign(target.y - head.y))


def indicator_cell(head: Cell, target: Cell) -> Cell | None:
    """蛇头 8 邻格中应当发光的提示格。

    返回 ``None`` 表示没有有效提示（目标与蛇头同格，或无目标）——
    此时不绘制任何指示。

    提示格恒为 ``(hx+sx, hy+sy)``，距蛇头恰好 1 格（含对角）。
    它可能落在墙格甚至地图外：这是「方向」而非「寻路建议」，
    调用方（渲染层）按可表达范围自行裁剪，本函数不做边界修正，
    也**绝不**因为前方是墙就改指别的方向。
    """
    sx, sy = indicator_direction(head, target)
    if sx == 0 and sy == 0:
        return None
    return Cell(head.x + sx, head.y + sy)


def indicator_name(head: Cell, target: Cell) -> str | None:
    """八方向的名称（N/NE/E/SE/S/SW/W/NW），主要用于测试与日志。"""
    d = indicator_direction(head, target)
    return INDICATOR_NAMES.get(d)


def indicator_cell_from_direction(head: Cell, direction: tuple[int, int]) -> Cell | None:
    """由量化方向 (sx, sy) 还原提示格。

    渲染层 / AI 拿到的是 ``(sx, sy)`` 而非目标坐标，用它在本地
    算出发光格——这与服务器直接发提示格等价，但线上少传一份坐标。
    """
    sx, sy = direction
    if sx == 0 and sy == 0:
        return None
    if (sx, sy) not in INDICATOR_NAMES:
        raise ValueError(f"非法的八方向向量: {direction}")
    return Cell(head.x + sx, head.y + sy)
