"""视野系统。

严格区分「谁知道什么」：
- ``ServerTruth``：服务器 / Game Engine 掌握的完整真相。
- ``PlayerView``：某个玩家被允许看到的东西。

金苹果坐标、普通果子坐标、敌人完整身体，都**不会**出现在 PlayerView 中。
玩家只能拿到：自己身体、可见范围内的格子 + 环境光、可见的敌人片段、公共事件，
以及一个八方向量化的目标指示（见 ``core.indicator``）。

亮度语义（自八方向指示格机制起）：
``brightness`` 是**环境光**——只描述「这格在自己的局部视野里有多亮」，
按到自己蛇头的距离衰减，与目标位置完全无关。
目标的唯一线索是单独的 ``target_indicator``（八方向之一），
因此玩家（或恶意客户端）无法从亮度场反推目标距离或坐标。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dark_forest_snake.config import (
    NORMAL_VIEW_RADIUS,
    LANTERN_VIEW_RADIUS,
    MIN_BRIGHTNESS,
    MAX_BRIGHTNESS,
)
from dark_forest_snake.core.geometry import Cell

# 视野外的格子亮度统一为这个值（背景黑）
DARK = 0.0


def ambient_light(cell: Cell, head: Cell, radius: int) -> float:
    """环境光：以自己蛇头为中心的局部照明。

    只依赖「自己与蛇头的距离」——玩家本来就知道自己的蛇头，
    因此这份亮度不含任何目标信息。蛇头最亮，视野边缘最暗。
    """
    d = cell.chebyshev(head)
    t = max(0.0, 1.0 - d / (radius + 1))
    return MIN_BRIGHTNESS + (MAX_BRIGHTNESS - MIN_BRIGHTNESS) * t


@dataclass
class VisibilityResult:
    visible_cells: set[Cell] = field(default_factory=set)
    brightness: dict[Cell, float] = field(default_factory=dict)
    visible_enemy_cells: set[Cell] = field(default_factory=set)
    reveal_all: bool = False


class VisibilitySystem:
    """计算某个玩家能看到什么。"""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def view_radius(self, lantern_active: bool, reveal_all: bool = False) -> int:
        if reveal_all:
            # 全图照亮时返回足以覆盖整张地图的半径
            return max(self.width, self.height) * 2
        return LANTERN_VIEW_RADIUS if lantern_active else NORMAL_VIEW_RADIUS

    def visible_cells(self, head: Cell, radius: int) -> set[Cell]:
        """视野是以蛇头为中心的方形区域（切比雪夫距离）。"""
        out: set[Cell] = set()
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                c = Cell(head.x + dx, head.y + dy)
                if 0 <= c.x < self.width and 0 <= c.y < self.height:
                    out.add(c)
        return out

    def compute(
        self,
        *,
        head: Cell,
        lantern_active: bool,
        enemy_body: list[Cell],
        reveal_all: bool = False,
        radius_override: int | None = None,
    ) -> VisibilityResult:
        """核心计算。

        不接收目标坐标：返回结构里只有「可见格 + 环境光 + 可见敌人」，
        目标方向由 ``core.indicator`` 单独量化后走 ``target_indicator`` 通道。
        """
        if radius_override is not None:
            radius = radius_override
        else:
            radius = self.view_radius(lantern_active, reveal_all)

        result = VisibilityResult(reveal_all=reveal_all)

        if reveal_all:
            cells = {
                Cell(x, y) for x in range(self.width) for y in range(self.height)
            }
        else:
            cells = self.visible_cells(head, radius)

        result.visible_cells = cells

        for c in cells:
            result.brightness[c] = ambient_light(c, head, radius)

        enemy_set = set(enemy_body)
        result.visible_enemy_cells = cells & enemy_set
        return result

    def is_visible(self, cell: Cell, visible: set[Cell]) -> bool:
        return cell in visible
