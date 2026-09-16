"""蛇：位置、方向输入队列、移动与成长。

严格区分「登记意图」与「推进世界」：
- ``enqueue_direction`` 只登记玩家/AI 的转向意图，绝不移动。
- ``move`` 每 Tick 只推进一格。
这样在事件驱动的游戏循环中，按键不会导致一帧多走一格。
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator

from dark_forest_snake.config import MAX_QUEUED_DIRECTIONS
from dark_forest_snake.core.geometry import Cell, Direction


class Snake:
    """一条蛇。body[0] 为蛇头，body[-1] 为蛇尾。"""

    __slots__ = (
        "body",
        "direction",
        "_pending",
        "alive",
        "death_reason",
        "name",
    )

    def __init__(
        self,
        body: Iterable[Cell],
        direction: Direction,
        name: str = "SNAKE",
    ) -> None:
        cells = list(body)
        if not cells:
            raise ValueError("蛇至少需要一节身体")
        self.body: list[Cell] = cells
        self.direction: Direction = direction
        self._pending: deque[Direction] = deque(maxlen=MAX_QUEUED_DIRECTIONS)
        self.alive: bool = True
        self.death_reason: str | None = None
        self.name = name

    # ------------------------------------------------------------ 属性
    @property
    def head(self) -> Cell:
        return self.body[0]

    @property
    def tail(self) -> Cell:
        return self.body[-1]

    @property
    def length(self) -> int:
        return len(self.body)

    @property
    def pending(self) -> tuple[Direction, ...]:
        return tuple(self._pending)

    def cells(self) -> list[Cell]:
        return list(self.body)

    def occupied(self, include_tail: bool = True) -> set[Cell]:
        """身体占用的格子集合。

        ``include_tail=False`` 用于「本 Tick 蛇尾会腾出来」的判定：
        普通移动时尾巴会离开原格，撞上尾巴原格不应致死。
        """
        body = self.body if include_tail else self.body[:-1]
        return set(body)

    # ------------------------------------------------------------ 方向
    def _next_direction(self) -> Direction:
        """本 Tick **实际**会生效的方向。

        这是「登记 → 计划 → 提交」三处必须共用的唯一事实来源：
        ``move()`` 每 Tick 从队列头 ``popleft()`` 消费一个方向，
        因此下一个真实方向就是**队列头**（否则才是当前 direction）。

        之前 ``effective_direction`` 返回**队列尾**，导致
        ``plan_move()``（碰撞判定用）与 ``move()``（实际位移用）
        在队列里压了 ≥2 个方向时各看一个方向 —— 计划与提交分叉。
        """
        if self._pending:
            return self._pending[0]
        return self.direction

    def effective_direction(self) -> Direction:
        """预测「连续输入最终会朝向哪个方向」。

        仅用于 ``enqueue_direction`` 的防反向/防重复基线判断：
        玩家连按 UP 再 LEFT，应按「最终朝 LEFT」来判定后续输入是否反向，
        所以这里返回队列尾。**它不是本 Tick 的移动方向** ——
        移动 / 碰撞判定请用 ``_next_direction``。
        """
        if self._pending:
            return self._pending[-1]
        return self.direction

    def enqueue_direction(self, direction: Direction) -> bool:
        """登记一个转向意图。只改方向，绝不移动。

        返回是否被接受。以下情况拒绝：
        - 与「队列中最后一个待生效方向」反向（防同帧连按掉头）
        - 与该方向完全相同（无意义）
        - 队列已满
        """
        baseline = self.effective_direction()
        if direction is baseline:
            return False
        if direction.is_opposite(baseline):
            return False
        if len(self._pending) >= MAX_QUEUED_DIRECTIONS:
            return False
        self._pending.append(direction)
        return True

    def _consume_direction(self) -> None:
        if self._pending:
            self.direction = self._pending.popleft()

    # ------------------------------------------------------------ 移动
    def next_head(self, direction: Direction | None = None) -> Cell:
        """在不改变自身状态的前提下，预测下一步蛇头位置。

        必须与 ``move()`` 用同一个方向来源（``_next_direction``），
        否则碰撞判定依据的格子会与实际位移的格子不一致。
        """
        d = direction if direction is not None else self._next_direction()
        return self.head.step(d)

    def plan_move(self, direction: Direction | None = None) -> Cell:
        """计算 nextHead，但不提交任何状态变更（同步 Tick 第一阶段）。"""
        return self.next_head(direction)

    def move(self, grow: bool = False, direction: Direction | None = None) -> Cell:
        """推进一格：加入新蛇头；未成长则删除蛇尾。

        返回新的蛇头位置。
        """
        if direction is None:
            self._consume_direction()
            d = self.direction
        else:
            # 显式指定方向（例如回放 / 测试），仍需同步内部方向状态
            if not direction.is_opposite(self.direction) and direction is not self.direction:
                self.direction = direction
            d = self.direction

        new_head = self.head.step(d)
        self.body.insert(0, new_head)
        if not grow:
            self.body.pop()
        return new_head

    def grow(self, amount: int = 1) -> None:
        """原地增长：在头部方向前插，不删尾。

        用于「吃到食物」的语义：移动 + 不删尾。
        """
        for _ in range(amount):
            new_head = self.head.step(self.direction)
            self.body.insert(0, new_head)

    def kill(self, reason: str) -> None:
        self.alive = False
        self.death_reason = reason

    # ------------------------------------------------------------ 工具
    def contains(self, cell: Cell) -> bool:
        return cell in self.body

    def index_of(self, cell: Cell) -> int:
        try:
            return self.body.index(cell)
        except ValueError:
            return -1

    def clone(self) -> "Snake":
        s = Snake(self.body, self.direction, self.name)
        s._pending = deque(self._pending, maxlen=MAX_QUEUED_DIRECTIONS)
        s.alive = self.alive
        s.death_reason = self.death_reason
        return s

    def __iter__(self) -> Iterator[Cell]:
        return iter(self.body)

    def __len__(self) -> int:
        return len(self.body)

    def __repr__(self) -> str:  # pragma: no cover - 调试友好
        state = "alive" if self.alive else f"dead({self.death_reason})"
        return f"Snake({self.name}, len={self.length}, head={self.head}, {state})"
