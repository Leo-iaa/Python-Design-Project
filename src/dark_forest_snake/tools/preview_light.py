"""开发期方向指示格可视化检查工具（文本模式）。

用法：
    uv run python -m dark_forest_snake.tools.preview_light

它能让你在终端里确认八方向指示格机制：
- 蛇头 8 邻格中恰好 1 格发光（* 标记）
- 发光格指向目标所在的大致八方向
- 目标本身不显示，距离不影响指示

这是开发辅助工具，不参与正式游戏。
"""

from __future__ import annotations

import argparse

from dark_forest_snake.core.geometry import Cell
from dark_forest_snake.core.indicator import (
    indicator_cell,
    indicator_name,
)
from dark_forest_snake.core.visibility import VisibilitySystem, ambient_light

RAMP = " .:-=+*#%@"


def main() -> None:
    ap = argparse.ArgumentParser(description="八方向指示格文本预览")
    ap.add_argument("--target-x", type=int, default=20)
    ap.add_argument("--target-y", type=int, default=6)
    ap.add_argument("--head-x", type=int, default=12)
    ap.add_argument("--head-y", type=int, default=10)
    ap.add_argument("--lantern", action="store_true")
    args = ap.parse_args()

    target = Cell(args.target_x, args.target_y)
    head = Cell(args.head_x, args.head_y)

    vs = VisibilitySystem(32, 24)
    radius = vs.view_radius(args.lantern)
    visible = vs.visible_cells(head, radius)
    ind = indicator_cell(head, target)

    print(f"目标 (内部真相) = {target}")
    print(f"蛇头 {head}  视野半径={radius}  灯笼={args.lantern}")
    print(f"指示方向 = {indicator_name(head, target)}  指示格 = {ind}")
    print(f"距目标 {head.manhattan(target)} 格（玩家不可知）\n")

    lo_x = max(0, head.x - radius - 1)
    hi_x = min(32, head.x + radius + 2)
    lo_y = max(0, head.y - radius - 1)
    hi_y = min(24, head.y + radius + 2)

    for y in range(lo_y, hi_y):
        row = []
        for x in range(lo_x, hi_x):
            c = Cell(x, y)
            if c == head:
                row.append("@")
            elif c == ind:
                row.append("*")
            elif c in visible:
                row.append(RAMP[3])
            else:
                row.append(" ")
        print("".join(row))

    print("\n图例: @ 蛇头   * 方向指示格（唯一发光格）  : 普通可见格")
    print("注意：正式游戏里目标与距离永不显示；* 距蛇头恒为 1 格。")


if __name__ == "__main__":
    main()
