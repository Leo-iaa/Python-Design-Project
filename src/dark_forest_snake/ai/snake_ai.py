"""AI：与玩家信息完全对等的贪吃蛇 AI。

**绝对禁止**：直接读取 fruit_position / gold_position / hidden_enemy_position。
AI 只能访问 ``AIPerception``——一个与玩家视野同源的信息包：
    当前可见区域、环境光、八方向目标指示（与玩家看到的发光格同源）、
    公共事件、自身状态、已发现危险区域。

决策结构：有限状态机 + 评分函数。
    SEARCH_FRUIT  默认：沿八方向指示推进
    SEARCH_GOLD   金苹果阶段：同样靠指示方向，但更激进
    CHASE         看得见敌人头部时：尝试堵截 / 争抢
    EVADE         有护盾或长度劣势时：避让
    ESCAPE_TRAP   空间不足时：优先保命
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from dark_forest_snake.core.geometry import Cell, Direction


class AIState(str, Enum):
    SEARCH_FRUIT = "search_fruit"
    SEARCH_GOLD = "search_gold"
    CHASE = "chase"
    EVADE = "evade"
    ESCAPE_TRAP = "escape_trap"


@dataclass
class AIPerception:
    """AI 唯一被允许访问的信息。**刻意不含任何隐藏目标坐标。**

    这个类就是信息隔离的契约：只要 AI 只用这里的字段，
    就不可能作弊。单元测试会检查字段白名单。
    """

    # 自身
    own_body: list[Cell]
    own_head: Cell
    own_direction: Direction
    own_length: int
    own_gold_count: int
    own_shield: bool
    own_sprint_remaining: float
    own_lantern: bool
    own_view_radius: int
    boosting: bool

    # 可见世界
    visible_cells: set[Cell]
    brightness: dict[Cell, float]

    # 可见敌人（可能为空）
    visible_enemy_cells: list[Cell]
    enemy_head: Cell | None
    enemy_length: int | None

    # 公共信息
    phase: str
    map_width: int
    map_height: int
    events: list[str] = field(default_factory=list)

    # 八方向目标指示 (sx, sy)，与玩家看到的光带同源。
    # 这是 AI 唯一的目标方向线索：没有坐标。
    indicator: tuple[int, int] | None = None
    # 目标接近度 ∈ [0,1]，与玩家看到的光点亮度同源。
    goal_proximity: float = 0.0
    # 目标种类（sprint/shield/lantern/gold），与玩家看到的光点颜色同源。
    goal_kind: str | None = None
    # 视野内的果子 / 金苹果（玩家进视野也能看到，信息对等）。
    seen_fruit: Cell | None = None
    seen_gold: Cell | None = None

    # 记忆（AI 自己积累的，不是外泄的真值）
    last_brightness: float = 0.0
    last_head: Cell | None = None
    danger_cells: set[Cell] = field(default_factory=set)

    def brightness_at(self, cell: Cell) -> float:
        return self.brightness.get(cell, 0.0)


ALLOWED_PERCEPTION_FIELDS = frozenset(AIPerception.__dataclass_fields__.keys())

# 任何形如这些名字的字段都绝不允许出现在 AIPerception 上
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "fruit",
        "fruit_position",
        "fruit_cell",
        "gold",
        "gold_position",
        "gold_cell",
        "target",
        "target_cell",
        "target_position",
        "hidden_enemy",
        "hidden_enemy_position",
        "gold_trigger",
        "normal_eaten",
        "true_state",
        "game",
        "engine",
    }
)


@dataclass
class AIAction:
    direction: Direction | None = None
    sprint: bool = False


class SnakeAI:
    """有限状态机 + 评分函数。"""

    def __init__(
        self,
        pid: int,
        rng: random.Random | None = None,
        *,
        aggression: float = 0.5,
    ) -> None:
        self.pid = pid
        self.rng = rng or random.Random()
        self.aggression = aggression
        self.state = AIState.SEARCH_FRUIT
        self._stuck_ticks = 0
        self._last_head: Cell | None = None
        self._danger: set[Cell] = set()
        self._sprint_cooldown = 0.0
        # 探索记忆：AI 自己走过的格子（玩家等价信息），用于避免原地打转。
        self._visited: set[Cell] = set()

    # ================================================================ 主入口
    def decide(self, p: AIPerception) -> AIAction:
        """返回本 Tick 的动作。只使用 p 中的信息。"""
        self._update_memory(p)
        self.state = self._choose_state(p)
        candidates = self._legal_moves(p)
        if not candidates:
            return AIAction(direction=None, sprint=False)

        scored = [
            (self._score(p, d, nxt), d) for d, nxt in candidates
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
        best_dir = scored[0][1]

        return AIAction(direction=best_dir, sprint=self._should_sprint(p))

    # ================================================================ 记忆
    def _update_memory(self, p: AIPerception) -> None:
        if self._last_head is not None and p.own_head == self._last_head:
            self._stuck_ticks += 1
        else:
            self._stuck_ticks = 0
        self._last_head = p.own_head

        self._visited.add(p.own_head)

        # 记忆危险：视野边缘快贴墙的位置视为危险
        for c in p.visible_cells:
            if self._near_edge(c, p):
                self._danger.add(c)
        self._danger &= set(p.visible_cells) | {
            Cell(c.x, c.y) for c in self._danger if not self._near_edge(c, p)
        }

    @staticmethod
    def _near_edge(c: Cell, p: AIPerception) -> bool:
        return c.x <= 1 or c.y <= 1 or c.x >= p.map_width - 2 or c.y >= p.map_height - 2

    # ================================================================ 指示方向
    def _indicator_alignment(self, p: AIPerception, d: Direction) -> int:
        """候选方向 d 与八方向指示的对齐轴数（0~2）。

        indicator = NE → 选 N 得 1、选 E 得 1；indicator = E → 选 E 得 1。
        这是 AI 从「发光格」读到的全部目标信息，与玩家完全对等。
        """
        if p.indicator is None:
            return 0
        sx, sy = p.indicator
        align = 0
        if sx != 0 and d.dx == sx:
            align += 1
        if sy != 0 and d.dy == sy:
            align += 1
        return align

    # ================================================================ 状态选择
    def _choose_state(self, p: AIPerception) -> AIState:
        # 1. 逃命优先：四周空间不足
        if self._space_around(p) <= len(p.own_body) + 2:
            return AIState.ESCAPE_TRAP

        # 2. 金苹果阶段 → 争夺
        if p.phase == "playing_golden":
            if p.enemy_head is not None and self._enemy_is_threat(p):
                return AIState.CHASE
            return AIState.SEARCH_GOLD

        # 3. 看得见敌人
        if p.enemy_head is not None:
            if self._enemy_is_threat(p):
                return AIState.EVADE
            if self._should_chase(p):
                return AIState.CHASE

        return AIState.SEARCH_FRUIT

    def _enemy_is_threat(self, p: AIPerception) -> bool:
        """对方比我长、且离我很近 → 视为威胁。"""
        if p.enemy_length is None or p.enemy_head is None:
            return False
        close = p.own_head.manhattan(p.enemy_head) <= 3
        longer = p.enemy_length > p.own_length
        return close and longer and not p.own_shield

    def _should_chase(self, p: AIPerception) -> bool:
        """我更长、离得近、且不是金苹果阶段 → 可以压迫对方。"""
        if p.enemy_head is None or p.enemy_length is None:
            return False
        if p.enemy_length >= p.own_length:
            return False
        if not p.own_shield and p.own_length < p.enemy_length + 2:
            return False
        return p.own_head.manhattan(p.enemy_head) <= 6 and self.aggression > 0.4

    def _space_around(self, p: AIPerception) -> int:
        """粗略估算头部周围可走的空间（洪水填充，深度有限）。"""
        return self._flood_size(p.own_head, set(p.own_body), p, limit=40)

    @staticmethod
    def _flood_size(
        start: Cell, blocked: set[Cell], p: AIPerception, limit: int = 60
    ) -> int:
        """从 start 出发能被身体挡住之前的可达格数（上限 limit）。

        这是一个廉价的"还能不能转身"估计，用来避免钻进死胡同。
        """
        seen = {start}
        stack = [start]
        count = 0
        while stack and count < limit:
            cur = stack.pop()
            count += 1
            for d in Direction:
                nxt = cur.step(d)
                if nxt in seen or nxt in blocked:
                    continue
                if not (0 <= nxt.x < p.map_width and 0 <= nxt.y < p.map_height):
                    continue
                seen.add(nxt)
                stack.append(nxt)
        return count

    # ================================================================ 合法动作
    def _legal_moves(
        self, p: AIPerception
    ) -> list[tuple[Direction, Cell]]:
        own = set(p.own_body)
        out: list[tuple[Direction, Cell]] = []
        for d in Direction:
            if d.is_opposite(p.own_direction):
                continue
            nxt = p.own_head.step(d)
            if not (0 <= nxt.x < p.map_width and 0 <= nxt.y < p.map_height):
                continue
            # 自己的身体（尾巴会腾空，但保守起见仍视为障碍中除尾）
            if nxt in own and nxt != p.own_body[-1]:
                continue
            if nxt in p.visible_enemy_cells:
                continue
            out.append((d, nxt))
        return out

    # ================================================================ 评分
    def _score(self, p: AIPerception, d: Direction, nxt: Cell) -> float:
        score = 0.0

        # 1) 八方向指示对齐：这是找目标的基本依据。
        #    indicator = NE → N / E 各得一分；对角指示时两轴分头推进。
        align = self._indicator_alignment(p, d)
        if self.state is AIState.SEARCH_GOLD:
            score += align * 60.0
        elif self.state in (AIState.SEARCH_FRUIT, AIState.CHASE, AIState.EVADE):
            score += align * 35.0
        else:
            score += align * 10.0

        # 1b) 光带越亮（离目标越近），方向权重越高——与玩家读光等价。
        score += align * 25.0 * p.goal_proximity

        # 1c) 视野内直接看到果子 / 金苹果：直线逼近，比读光更优先。
        seen = p.seen_gold or p.seen_fruit
        if seen is not None:
            weight = 30.0 if p.seen_gold is not None else 18.0
            score -= nxt.manhattan(seen) * weight

        # 2) 安全：靠近墙 / 危险区重罚
        if self._near_edge(nxt, p):
            score -= 60.0
        if nxt in self._danger:
            score -= 25.0

        # 3) 自由度：选择更开阔的方向
        free = 0
        for dd in Direction:
            c = nxt.step(dd)
            if 0 <= c.x < p.map_width and 0 <= c.y < p.map_height:
                if c not in p.own_body:
                    free += 1
        score += free * 3.0

        # 3b) 安全空间前瞻：进入这一格后如果剩余可走空间过小，重罚。
        #     这是避免"为了追一个方向而钻进死胡同"的关键。
        open_space = self._flood_size(nxt, set(p.own_body) | (p.own_head and {p.own_head} or set()), p, limit=60)
        if open_space <= p.own_length + 1:
            score -= 90.0
        else:
            score += min(open_space, 40) * 1.5

        # 3c) 探索：已访问过的格子轻微惩罚，避免在原地打转
        if nxt in self._visited:
            score -= 4.0

        # 4) 状态专属偏好
        if self.state is AIState.CHASE and p.enemy_head is not None:
            # 压迫：向敌人头部方向靠拢，但保持一点距离避免头对头
            dist_after = nxt.manhattan(p.enemy_head)
            if dist_after >= 2:
                score += (12 - dist_after) * 6.0
            else:
                score -= 40.0  # 太近会头对头，主动回避
        elif self.state is AIState.EVADE and p.enemy_head is not None:
            score += nxt.manhattan(p.enemy_head) * 5.0
        elif self.state is AIState.ESCAPE_TRAP:
            score += free * 8.0

        # 5) 避免直线回退导致的自锁
        if self._stuck_ticks > 4:
            score -= 5.0

        return score

    def _should_sprint(self, p: AIPerception) -> bool:
        """疾跑决策：不能永久开启。"""
        if p.own_sprint_remaining <= 0:
            return False
        if self.state is AIState.ESCAPE_TRAP:
            return True
        if self.state is AIState.SEARCH_GOLD:
            # 金苹果阶段才积极冲刺
            return p.own_sprint_remaining > 1.5
        if self.state is AIState.SEARCH_FRUIT:
            # 搜索阶段只在能力窗口早期、且有明确方向时短促冲刺
            return p.indicator is not None and p.own_sprint_remaining > 6.0
        return False


def _to_cell(value) -> Cell:
    """接受 (x, y) 列表 / 元组 / Cell / "x,y" 字符串，统一转成 Cell。"""
    if isinstance(value, Cell):
        return value
    if isinstance(value, str):
        x, y = value.split(",", 1)
        return Cell(int(x), int(y))
    x, y = value
    return Cell(int(x), int(y))


def _to_indicator(value) -> tuple[int, int] | None:
    """把网络上的 [sx, sy] / 元组统一成 (int, int)，None 透传。"""
    if value is None:
        return None
    sx, sy = value
    return (int(sx), int(sy))


def perception_from_view(view, game_dims: tuple[int, int]) -> AIPerception:
    """把一个 PlayerViewState 转成 AIPerception。

    这是唯一允许的转换入口——只要 PlayerViewState 不含隐藏信息，
    AI 就不可能作弊。注意 AIPerception 的亮度表直接来自 view，
    可见格子集合也由亮度表的 key 推出。
    """
    width, height = game_dims
    brightness = {
        _to_cell(k): float(v) for k, v in view.visible_brightness.items()
    }
    visible = set(brightness.keys())
    own_body = [_to_cell(c) for c in view.own_body]
    enemy_cells = [_to_cell(c) for c in view.visible_enemy_cells]

    enemy_head = None
    if view.enemy_head_visible and enemy_cells:
        # 我们只能看到敌人身体的一部分。取离我方头部最近的一节作为近似头部，
        # 这是一个保守估计（不引入任何额外真值）。
        oh = _to_cell(view.own_head)
        enemy_head = min(enemy_cells, key=lambda c: c.manhattan(oh))

    direction = Direction(tuple(view.own_direction))

    seen_fruit = None
    vf = getattr(view, "visible_fruit", None)
    if vf:
        seen_fruit = _to_cell(vf["cell"])
    seen_gold = None
    vg = getattr(view, "visible_gold", None)
    if vg:
        seen_gold = _to_cell(vg)

    return AIPerception(
        own_body=own_body,
        own_head=_to_cell(view.own_head),
        own_direction=direction,
        own_length=view.own_length,
        own_gold_count=view.own_gold_count,
        own_shield=view.abilities.get("shield", 0.0) > 0,
        own_sprint_remaining=view.abilities.get("sprint", 0.0),
        own_lantern=view.abilities.get("lantern", 0.0) > 0,
        own_view_radius=view.view_radius,
        boosting=view.boosting,
        visible_cells=visible,
        brightness=brightness,
        visible_enemy_cells=enemy_cells,
        enemy_head=enemy_head,
        enemy_length=view.enemy_length_visible,
        phase=view.phase,
        map_width=width,
        map_height=height,
        events=[str(e.get("text", "")) for e in view.events],
        indicator=_to_indicator(getattr(view, "target_indicator", None)),
        goal_proximity=float(getattr(view, "target_proximity", 0.0) or 0.0),
        goal_kind=getattr(view, "target_kind", None),
        seen_fruit=seen_fruit,
        seen_gold=seen_gold,
    )


def perception_from_dict(view_dict: dict, game_dims: tuple[int, int]) -> AIPerception:
    """从（网络传来的）字典构建感知包 —— LAN 客户端上的 AI 也走这条路径。"""

    class _V:
        pass

    v = _V()
    for k, val in view_dict.items():
        setattr(v, k, val)
    v.abilities = view_dict.get("abilities", {})
    return perception_from_view(v, game_dims)
