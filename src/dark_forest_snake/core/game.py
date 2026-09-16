"""Game Engine：完整的《黑暗森林贪吃蛇》游戏规则。

**不依赖 pygame**，可被单机模式、LAN 服务器、AI 自对弈与单元测试直接调用。

同步 Tick 的公平性保证：
    1. 快照旧状态
    2. 分别计算 P1 / P2 的 nextHead
    3. 统一碰撞判定（collision.resolve_tick）
    4. 统一提交状态
绝不「先移动 P1 再移动 P2」。

所有随机性来自注入的 ``random.Random``（支持 seeded），
所有时间来自 ``GameClock``（dt 由外部注入），因此整局完全可复现。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from dark_forest_snake import config as C
from dark_forest_snake.core.abilities import AbilitySystem
from dark_forest_snake.core.clock import LANTERN, REVEAL, SPRINT, ExpirySet
from dark_forest_snake.core.collision import (
    CollisionOutcome,
    DeathReason,
    resolve_tick,
)
from dark_forest_snake.core.fruit import (
    Fruit,
    FruitSystem,
    FruitType,
    GoldApple,
)
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.indicator import indicator_direction
from dark_forest_snake.core.snake import Snake
from dark_forest_snake.core.state import GamePhase, GameStateMachine
from dark_forest_snake.core.visibility import VisibilitySystem

P1 = 0
P2 = 1
PLAYER_IDS = (P1, P2)


def _new_reveal_map() -> dict[int, ExpirySet]:
    """全图照亮**必须按玩家单独跟踪**。

    这是一个信息隔离的关键点：如果共用一个 ExpirySet，
    吃到金苹果的人会让对方也获得 3 秒全图视野 —— 严重违规。
    """
    return {P1: ExpirySet(), P2: ExpirySet()}


def _cell_key(x: int, y: int) -> str:
    """把坐标编码成 JSON 安全的字符串 key。"""
    return f"{x},{y}"


def parse_cell_key(key: str) -> tuple[int, int]:
    """把 "x,y" 还原成坐标。用于客户端渲染层。"""
    x, y = key.split(",", 1)
    return int(x), int(y)


@dataclass
class GameEvent:
    """公共事件（双方都能看到）。不得包含隐藏目标坐标。"""

    kind: str
    text: str
    player: int | None = None
    at: float = 0.0

    def __post_init__(self) -> None:
        if self.at == 0.0:
            self.at = getattr(self, "_now", 0.0)


@dataclass
class PlayerViewState:
    """发给某个玩家的视角状态。**绝不包含隐藏目标坐标。**

    字段白名单化：任何新增字段都需要确认它不会泄漏信息。
    """

    player: int
    phase: str
    # 自己的蛇（完整可见，用暗淡轮廓绘制以降低随机自撞）
    own_body: list[tuple[int, int]]
    own_head: tuple[int, int]
    own_direction: tuple[int, int]
    own_length: int
    own_gold_count: int
    # 自己能看到的地图：坐标 -> 亮度。视野外完全不出现。
    visible_brightness: dict[tuple[int, int], float]
    # 视野内的敌人身体片段（可能为空）
    visible_enemy_cells: list[tuple[int, int]]
    enemy_head_visible: bool
    enemy_direction_visible: tuple[int, int] | None
    enemy_length_visible: int | None
    enemy_gold_count: int
    # 能力
    abilities: dict[str, float]
    boosting: bool
    view_radius: int
    # 全图照亮（仅金苹果获得者）
    reveal_active: bool
    reveal_remaining: float
    # 公共事件
    events: list[dict[str, object]]
    # 胜负
    winner: int | None
    draw: bool
    clock: float
    # 倒计时剩余
    countdown_remaining: float
    # 对方是否可见（用于 HUD 提示，不含坐标）
    enemy_alive: bool
    # 八方向目标指示 (sx, sy) ∈ {-1,0,1}²，例如 (1,-1) 代表 NE。
    # 这是目标方向信息的唯一出口：已量化到八方向，不含坐标。
    # None 表示当前没有可指示的目标（或未开局）。
    target_indicator: tuple[int, int] | None = None
    # 目标接近度 ∈ [0, 1]：1 表示目标就在邻格，0 表示在地图另一端。
    # 这是「越接近目标光点越亮」的数据源——只透露相对远近，不透露坐标。
    target_proximity: float = 0.0
    # 当前目标的种类（sprint / shield / lantern / gold）：
    # 视野边缘光点的颜色来源（玩家看到的光点颜色即目标果子颜色）。
    target_kind: str | None = None
    # 视野内的果子 / 金苹果（在可见范围内才出现，否则为 None）。
    # 果子可见时附带类型（颜色是公开信息：吃掉时双方都会收到提示）。
    visible_fruit: dict[str, object] | None = None
    visible_gold: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, object]:
        """转成可 JSON 序列化的字典。

        注意：坐标一律编码成 "x,y" 字符串 —— JSON 的对象 key 只能是字符串，
        直接用 tuple 作 key 会在编码时抛 TypeError。
        """
        return {
            "player": self.player,
            "phase": self.phase,
            "own_body": [list(c) for c in self.own_body],
            "own_head": list(self.own_head),
            "own_direction": list(self.own_direction),
            "own_length": self.own_length,
            "own_gold_count": self.own_gold_count,
            "visible_brightness": {
                _cell_key(x, y): round(float(v), 6)
                for (x, y), v in self.visible_brightness.items()
            },
            "visible_enemy_cells": [list(c) for c in self.visible_enemy_cells],
            "enemy_head_visible": self.enemy_head_visible,
            "enemy_direction_visible": (
                list(self.enemy_direction_visible)
                if self.enemy_direction_visible is not None
                else None
            ),
            "enemy_length_visible": self.enemy_length_visible,
            "enemy_gold_count": self.enemy_gold_count,
            "abilities": {
                k: round(float(v), 3) for k, v in self.abilities.items()
            },
            "boosting": self.boosting,
            "view_radius": self.view_radius,
            "reveal_active": self.reveal_active,
            "reveal_remaining": round(float(self.reveal_remaining), 3),
            "events": self.events,
            "winner": self.winner,
            "draw": self.draw,
            "clock": round(float(self.clock), 4),
            "countdown_remaining": round(float(self.countdown_remaining), 3),
            "enemy_alive": self.enemy_alive,
            "target_indicator": (
                list(self.target_indicator)
                if self.target_indicator is not None
                else None
            ),
            "target_proximity": round(float(self.target_proximity), 4),
            "target_kind": self.target_kind,
            "visible_fruit": (
                {
                    "cell": list(self.visible_fruit["cell"]),
                    "type": self.visible_fruit["type"],
                }
                if self.visible_fruit is not None
                else None
            ),
            "visible_gold": (
                list(self.visible_gold) if self.visible_gold is not None else None
            ),
        }


@dataclass
class _PendingSpawn:
    cell: Cell
    direction: Direction


class Game:
    """一局《黑暗森林贪吃蛇》。"""

    def __init__(
        self,
        *,
        width: int = C.MAP_WIDTH,
        height: int = C.MAP_HEIGHT,
        seed: int | None = None,
        debug: bool = False,
        initial_length: int = C.INITIAL_SNAKE_LENGTH,
    ) -> None:
        self.width = width
        self.height = height
        self.debug = debug
        self.initial_length = initial_length
        self.rng = random.Random(seed)
        self.seed = seed

        self.clock = 0.0
        # 每条蛇独立的移动计时器：疾跑只让自己变快，不再拖着对方一起加速
        self._move_acc: dict[int, float] = {P1: 0.0, P2: 0.0}
        self.state = GameStateMachine(GamePhase.MENU)

        self.snakes: dict[int, Snake] = {}
        self.abilities = AbilitySystem(list(PLAYER_IDS))
        self.fruits = FruitSystem(self.rng, width, height)
        self.visibility = VisibilitySystem(width, height)

        self.gold_counts: dict[int, int] = {P1: 0, P2: 0}
        self.gold_trigger: int = 0            # 隐藏阈值，绝不外发
        self.normal_eaten_this_round: int = 0  # 本轮全场吃掉的普通果子数
        self.round_index: int = 0

        self.reveal_expiries = _new_reveal_map()
        self.events: list[GameEvent] = []
        self._event_log: list[GameEvent] = []

        self.countdown_remaining = 0.0
        self.last_tick_time = 0.0
        self.tick_count = 0
        self.draw = False
        self.winner: int | None = None

        # 每个玩家的输入意图（由 UI / 网络层注入）
        self.sprint_input: dict[int, bool] = {P1: False, P2: False}

    # ================================================================ 生命周期
    def new_round_setup(self, *, announce: bool = True) -> None:
        """生成两条蛇的合法出生位置，重置本轮所有状态。"""
        spawns = self._generate_spawns()
        self.snakes = {}
        for pid in PLAYER_IDS:
            sp = spawns[pid]
            body = self._build_body(sp.cell, sp.direction)
            self.snakes[pid] = Snake(body, sp.direction, name=f"P{pid + 1}")

        self.abilities.reset()
        self.reveal_expiries = _new_reveal_map()
        self.fruits.clear_gold()
        self.fruits.clear_fruit()
        self.normal_eaten_this_round = 0
        self.gold_trigger = self.rng.randint(C.GOLD_TRIGGER_MIN, C.GOLD_TRIGGER_MAX)
        self.round_index += 1
        self.winner = None
        self.draw = False
        self.tick_count = 0
        self._move_acc = {P1: 0.0, P2: 0.0}
        self._next_round_at = None
        self._spawn_normal_fruit()
        if announce:
            self.emit(
                f"第 {self.round_index} 轮开始，隐藏阈值为 {self.gold_trigger}"
                if self.debug
                else f"第 {self.round_index} 轮开始"
            )

    def _build_body(self, head: Cell, direction: Direction) -> list[Cell]:
        """按初始长度沿反方向铺开身体，确保整条蛇都在合法区域内。"""
        body = [head]
        back = Direction.UP if direction is Direction.DOWN else (
            Direction.DOWN if direction is Direction.UP else (
                Direction.RIGHT if direction is Direction.LEFT else Direction.LEFT
            )
        )
        cur = head
        for _ in range(self.initial_length - 1):
            cur = cur.step(back)
            if not (0 <= cur.x < self.width and 0 <= cur.y < self.height):
                # 后退越界：翻转方向重新铺（贴墙出生保护）
                back = direction
                cur = head
                for _ in range(self.initial_length - 2):
                    cur = cur.step(back)
                body = [head]
                for _ in range(self.initial_length - 2):
                    body.append(body[-1].step(back))
                break
            body.append(cur)
        return body

    def _generate_spawns(self) -> dict[int, _PendingSpawn]:
        """两条蛇在较远位置随机出生，不重叠、不在墙边、朝向不撞墙。"""
        for _ in range(500):
            a_head = Cell(
                self.rng.randint(2, self.width - 3),
                self.rng.randint(2, self.height - 3),
            )
            b_head = Cell(
                self.rng.randint(2, self.width - 3),
                self.rng.randint(2, self.height - 3),
            )
            if a_head.manhattan(b_head) < C.MIN_SPAWN_DISTANCE:
                continue
            a_dir = self._safe_direction(a_head)
            b_dir = self._safe_direction(b_head, avoid_near=[a_head, b_head])
            if a_dir is None or b_dir is None:
                continue
            a_body = self._build_body(a_head, a_dir)
            b_body = self._build_body(b_head, b_dir)
            if set(a_body) & set(b_body):
                continue
            if not self._body_in_bounds(a_body) or not self._body_in_bounds(b_body):
                continue
            return {
                P1: _PendingSpawn(a_head, a_dir),
                P2: _PendingSpawn(b_head, b_dir),
            }
        # 极端退化（地图过小）：退回到明确的固定布局
        a_head = Cell(2, self.height // 2)
        b_head = Cell(self.width - 3, self.height // 2)
        return {
            P1: _PendingSpawn(a_head, Direction.RIGHT),
            P2: _PendingSpawn(b_head, Direction.LEFT),
        }

    def _safe_direction(
        self, head: Cell, avoid_near: list[Cell] | None = None
    ) -> Direction | None:
        """选一个不会立刻撞墙、且有一定活动空间的初始方向。"""
        opts: list[Direction] = []
        for d in (Direction.RIGHT, Direction.LEFT, Direction.UP, Direction.DOWN):
            nxt = head.step(d)
            if not (0 <= nxt.x < self.width and 0 <= nxt.y < self.height):
                continue
            # 需要至少 2 格缓冲，避免开局就贴墙
            nxt2 = nxt.step(d)
            if not (0 <= nxt2.x < self.width and 0 <= nxt2.y < self.height):
                continue
            opts.append(d)
        if not opts:
            return None
        self.rng.shuffle(opts)
        return opts[0]

    def _body_in_bounds(self, body: list[Cell]) -> bool:
        return all(0 <= c.x < self.width and 0 <= c.y < self.height for c in body)

    def start_match(self, *, countdown: float = C.COUNTDOWN_DURATION) -> None:
        """从 MENU / GAME_OVER 进入一局。"""
        if self.state.phase in (GamePhase.GAME_OVER, GamePhase.DRAW_RESTART, GamePhase.MENU):
            self.state.transition(GamePhase.COUNTDOWN)
        self.new_round_setup()
        self.gold_counts = {P1: 0, P2: 0}
        self.round_index = 1
        self.countdown_remaining = countdown
        self.events.clear()
        self._event_log.clear()
        if countdown <= 0:
            self._finish_countdown()

    def _finish_countdown(self) -> None:
        if self.state.phase is GamePhase.COUNTDOWN:
            self.state.transition(GamePhase.PLAYING_NORMAL)

    def restart_after_draw(self) -> None:
        self.state.transition(GamePhase.COUNTDOWN)
        self.start_match()

    def full_reset(self) -> None:
        self.state.reset(GamePhase.MENU)
        self.snakes = {}
        self.gold_counts = {P1: 0, P2: 0}
        self.abilities.reset()
        self.reveal_expiries = _new_reveal_map()
        self.fruits.clear_fruit()
        self.fruits.clear_gold()
        self.events.clear()
        self._event_log.clear()
        self.winner = None
        self.draw = False
        self.round_index = 0

    # ================================================================ 输入
    def input_direction(self, pid: int, direction: Direction) -> bool:
        if not self.state.phase.is_playing:
            return False
        snake = self.snakes.get(pid)
        if snake is None or not snake.alive:
            return False
        return snake.enqueue_direction(direction)

    def input_sprint(self, pid: int, held: bool) -> None:
        self.sprint_input[pid] = held
        self.abilities[pid].sprint_held = held

    # ================================================================ 时间推进
    def update(self, dt: float) -> None:
        """按注入的 dt 推进游戏。dt 为真实经过秒数。"""
        if dt < 0:
            dt = 0.0
        self.clock += dt

        # 能力过期检查（任何阶段都推进，保证 UI 读数是准的）
        self.abilities.tick(self.clock)
        for _rs in self.reveal_expiries.values():
            _rs.cleanup(self.clock)

        if self.state.phase is GamePhase.COUNTDOWN:
            self.countdown_remaining -= dt
            if self.countdown_remaining <= 0:
                self.countdown_remaining = 0.0
                self._finish_countdown()
            return

        if not self.state.phase.is_playing:
            return

        # 金苹果拿到后：3 秒全图照亮结束 → 地图重新黑暗 + 生成普通果子 + 计数归零
        nxt = getattr(self, "_next_round_at", None)
        if nxt is not None and self.clock >= nxt and self.state.phase is GamePhase.PLAYING_GOLDEN:
            self._next_round_at = None
            self._start_next_round()

        # 每条蛇独立累积自己的移动时间；同一帧内到点的蛇组成一个批次，
        # 批次内仍然「快照 → 统一判定 → 统一提交」，公平性与原同步 Tick 一致。
        for pid in PLAYER_IDS:
            if pid in self.snakes and self.snakes[pid].alive:
                self._move_acc[pid] += dt

        guard = 0
        while guard < 8:
            movers = [
                pid
                for pid in PLAYER_IDS
                if pid in self.snakes
                and self.snakes[pid].alive
                and self._move_acc[pid]
                >= self.abilities[pid].effective_interval(self.clock)
            ]
            if not movers:
                break
            for pid in movers:
                self._move_acc[pid] -= self.abilities[pid].effective_interval(
                    self.clock
                )
            self._tick(movers)
            guard += 1
            if not self.state.phase.is_playing:
                break
        if guard >= 8:
            self._move_acc = {P1: 0.0, P2: 0.0}

    # ================================================================ Tick
    def _tick(self, movers: list[int] | None = None) -> None:
        """一个完整 Tick：快照 → 计划 → 统一判定 → 统一提交。

        ``movers`` 是本批次实际移动的蛇（各自计时到点）。不到点的蛇保持不动，
        但其身体（含头部）仍然参与占位与头对头判定。
        """
        self.tick_count += 1
        alive_pids = [pid for pid in PLAYER_IDS if self.snakes[pid].alive]
        if not alive_pids:
            return
        if movers is None:
            movers = alive_pids
        movers = [pid for pid in movers if self.snakes[pid].alive]
        if not movers:
            return
        stationary = [pid for pid in alive_pids if pid not in movers]

        # ---- 1. 快照旧状态，计算 nextHead ----
        planned: dict[int, Cell] = {}
        for pid in movers:
            planned[pid] = self.snakes[pid].plan_move()
        # 不动的蛇：占位格就是当前蛇头（撞上它按头对头处理）
        for pid in stationary:
            planned[pid] = self.snakes[pid].head

        # ---- 2. 判断本 Tick 谁会吃到东西（决定是否成长） ----
        grow_flags: dict[int, bool] = {}
        eat_normal: dict[int, Fruit] = {}
        eat_gold: dict[int, GoldApple] = {}

        for pid in movers:
            head = planned[pid]
            grow_flags[pid] = False
            if self.fruits.gold is not None and head == self.fruits.gold.cell:
                grow_flags[pid] = True
                eat_gold[pid] = self.fruits.gold
            elif self.fruits.fruit is not None and head == self.fruits.fruit.cell:
                grow_flags[pid] = True
                eat_normal[pid] = self.fruits.fruit
        for pid in stationary:
            # 不动的蛇尾巴不会腾空：碰撞判定时按全身占位
            grow_flags[pid] = True

        # 两个蛇头抢同一个果子：都算吃到（各自成长），由碰撞规则裁决生死。
        # 若其中一个因碰撞死亡，其成长不提交。

        # ---- 3. 统一碰撞判定 ----
        shield_charges = {
            pid: self.abilities[pid].shield_charges for pid in PLAYER_IDS
        }
        report = resolve_tick(
            snakes=self.snakes,
            planned_heads=planned,
            grow_flags=grow_flags,
            shield_charges=shield_charges,
            width=self.width,
            height=self.height,
            movers=set(movers),
        )

        # ---- 4. 统一提交状态 ----
        for pid in alive_pids:
            res = report.results.get(pid)
            if res is None:
                continue
            if res.shield_consumed:
                self.abilities[pid].consume_shield()
                self.emit(f"P{pid + 1} 的护盾破裂了！", player=pid)

            if res.outcome is CollisionOutcome.DEAD:
                self.snakes[pid].kill(res.reason.value if res.reason else "unknown")
                continue

            if res.blocked:
                # 被护盾挡下 → 本 Tick 不前进（回弹）
                continue

            if pid not in movers:
                continue
            snake = self.snakes[pid]
            # move(grow=...) 一次到位：成长时加入新蛇头且不删蛇尾。
            snake.move(grow=grow_flags.get(pid, False))

        # ---- 5. 处理进食效果 ----
        for pid, fruit in eat_normal.items():
            if self.snakes[pid].alive:
                self._on_eat_normal(pid, fruit)
        for pid in eat_gold:
            if self.snakes[pid].alive:
                self._on_eat_gold(pid)

        # ---- 6. 死亡结算 ----
        if report.any_death:
            self._resolve_deaths(report)

    # ---------------------------------------------------------------- 进食
    def _on_eat_normal(self, pid: int, fruit: Fruit) -> None:
        self.abilities[pid].grant(fruit.type.value, self.clock)
        self.normal_eaten_this_round += 1
        self.emit(f"P{pid + 1} 吃到了{fruit.type.label}", player=pid)

        # 本轮普通果子阶段 → 检查隐藏阈值
        if (
            self.state.phase is GamePhase.PLAYING_NORMAL
            and self.normal_eaten_this_round >= self.gold_trigger
        ):
            self._enter_golden_phase()
        elif self.state.phase is GamePhase.PLAYING_NORMAL:
            self._spawn_normal_fruit()

    def _on_eat_gold(self, pid: int) -> None:
        self.gold_counts[pid] += 1
        self.abilities[pid].grant_all(self.clock)
        self.fruits.clear_gold()
        self.reveal_expiries[pid].grant(REVEAL, self.clock, C.FULL_REVEAL_DURATION)
        self.emit(f"P{pid + 1} 获得了金苹果！", player=pid)

        if self.gold_counts[pid] >= C.GOLD_TO_WIN:
            self._end_game(winner=pid, reason="gold")
            return

        # 3 秒全图照亮 → 之后进入下一轮
        self.state.transition(GamePhase.PLAYING_GOLDEN)
        # 不立刻开新一轮：等 3 秒 Reveal 结束由 update 触发
        self._next_round_at = self.clock + C.FULL_REVEAL_DURATION

    def _spawn_normal_fruit(self) -> None:
        blocked = self._all_occupied_cells()
        avoid = self.snakes[P1].head if P1 in self.snakes else None
        self.fruits.spawn_fruit(blocked, avoid_near=avoid)

    def _all_occupied_cells(self) -> set[Cell]:
        cells: set[Cell] = set()
        for snake in self.snakes.values():
            cells |= set(snake.body)
        cells |= self.fruits.all_occupied()
        return cells

    # ---------------------------------------------------------------- 金苹果
    def _enter_golden_phase(self) -> None:
        self.fruits.clear_fruit()
        blocked = self._all_occupied_cells()
        self.fruits.spawn_gold(blocked)
        self.state.transition(GamePhase.PLAYING_GOLDEN)
        self._next_round_at = None
        self.emit("金苹果出现了！")

    def _start_next_round(self) -> None:
        """金苹果 3 秒全图结束后：地图重新黑暗、生成普通果子、计数归零、重掷阈值。

        注意：新一轮**不重新生成蛇的出生位置**，两条蛇保持原位继续对抗，
        否则 3 秒信息优势会被出生点洗牌抹掉。这里只重置「本轮」的资源状态。
        """
        self.state.transition(GamePhase.PLAYING_NORMAL)
        self.normal_eaten_this_round = 0
        self.gold_trigger = self.rng.randint(C.GOLD_TRIGGER_MIN, C.GOLD_TRIGGER_MAX)
        self.fruits.clear_gold()
        self.fruits.clear_fruit()
        self.reveal_expiries = _new_reveal_map()
        self._spawn_normal_fruit()
        self.round_index += 1
        self._next_round_at = None
        self.emit(f"第 {self.round_index} 轮开始")

    # ---------------------------------------------------------------- 结算
    def _resolve_deaths(self, report) -> None:
        dead = [pid for pid in PLAYER_IDS if report.died(pid)]
        if not dead:
            return

        for pid in dead:
            reason = self.snakes[pid].death_reason or "unknown"
            self.emit(f"P{pid + 1} 死亡（{self._reason_label(reason)}）", player=pid)

        if report.head_to_head_draw or report.both_dead or len(dead) == 2:
            self.draw = True
            self.state.transition(GamePhase.DRAW_RESTART)
            self.emit("平局，整局重新开始")
            return

        loser = dead[0]
        self._end_game(winner=1 - loser, reason=f"kill:{self.snakes[loser].death_reason}")

    def _end_game(self, *, winner: int, reason: str) -> None:
        self.winner = winner
        self.draw = False
        if self.state.phase in (GamePhase.PLAYING_NORMAL, GamePhase.PLAYING_GOLDEN):
            self.state.transition(GamePhase.GAME_OVER, winner=winner, reason=reason)
        if reason == "gold":
            self.emit(f"P{winner + 1} 集齐 3 个金苹果，获胜！", player=winner)
        else:
            self.emit(f"P{winner + 1} 获胜！", player=winner)

    @staticmethod
    def _reason_label(reason: str) -> str:
        return {
            "wall": "撞墙",
            "self": "撞到自己",
            "enemy_body": "撞上对方身体",
            "head_to_head": "头对头",
            "trap": "被困死",
        }.get(reason, reason)

    # ================================================================ 事件
    def emit(self, text: str, player: int | None = None) -> GameEvent:
        ev = GameEvent(kind="info", text=text, player=player, at=self.clock)
        self.events.append(ev)
        self._event_log.append(ev)
        if len(self.events) > 8:
            self.events = self.events[-8:]
        return ev

    @property
    def event_log(self) -> list[GameEvent]:
        return list(self._event_log)

    # ================================================================ 视角
    def view_for(self, pid: int) -> PlayerViewState:
        """为某个玩家生成被裁剪过的视角状态。

        **绝不包含：果子坐标、金苹果坐标、敌人完整身体、隐藏阈值。**
        """
        snake = self.snakes.get(pid)
        reveal_active = self.reveal_expiries[pid].active(REVEAL, self.clock)
        lantern = self.abilities[pid].has_lantern(self.clock) if snake else False

        if snake is None:
            # 尚未开局
            return PlayerViewState(
                player=pid,
                phase=self.state.phase.value,
                own_body=[],
                own_head=(0, 0),
                own_direction=Direction.RIGHT.delta,
                own_length=0,
                own_gold_count=self.gold_counts[pid],
                visible_brightness={},
                visible_enemy_cells=[],
                enemy_head_visible=False,
                enemy_direction_visible=None,
                enemy_length_visible=None,
                enemy_gold_count=self.gold_counts[1 - pid],
                abilities={"sprint": 0.0, "shield": 0.0, "lantern": 0.0},
                boosting=False,
                view_radius=C.NORMAL_VIEW_RADIUS,
                reveal_active=False,
                reveal_remaining=0.0,
                events=[],
                winner=self.winner,
                draw=self.draw,
                clock=self.clock,
                countdown_remaining=max(0.0, self.countdown_remaining),
                enemy_alive=False,
            )

        enemy_pid = 1 - pid
        enemy = self.snakes.get(enemy_pid)

        vis = self.visibility.compute(
            head=snake.head,
            lantern_active=lantern,
            enemy_body=enemy.body if enemy is not None and enemy.alive else [],
            reveal_all=reveal_active,
        )

        # 八方向目标指示：方向信息的唯一出口，量化到 (sx, sy)。
        # game_target 在普通/金苹果阶段自动切换，因此指示自动跟随当前阶段目标。
        # target_proximity 只透露「相对远近」（供光带随接近变亮），不透露坐标。
        tgt = self.fruits.game_target
        indicator: tuple[int, int] | None = None
        proximity = 0.0
        target_kind: str | None = None
        if tgt is not None:
            d = indicator_direction(snake.head, tgt)
            if d != (0, 0):
                indicator = d
            max_dist = max(1, max(self.width, self.height))
            proximity = max(0.0, 1.0 - snake.head.chebyshev(tgt) / max_dist)
            target_kind = (
                "gold" if self.fruits.gold is not None else self.fruits.fruit.type.value
            )

        # 果子 / 金苹果只在进入可见范围时才会被看到（坐标已裁剪到视野内）。
        visible_fruit: dict[str, object] | None = None
        if self.fruits.fruit is not None and self.fruits.fruit.cell in vis.visible_cells:
            visible_fruit = {
                "cell": self.fruits.fruit.cell.as_tuple(),
                "type": self.fruits.fruit.type.value,
            }
        visible_gold: tuple[int, int] | None = None
        if self.fruits.gold is not None and self.fruits.gold.cell in vis.visible_cells:
            visible_gold = self.fruits.gold.cell.as_tuple()

        enemy_visible_cells = sorted(vis.visible_enemy_cells, key=lambda c: (c.y, c.x))
        enemy_head_visible = bool(
            enemy is not None and enemy.alive and enemy.head in vis.visible_cells
        )

        ab = self.abilities[pid]
        return PlayerViewState(
            player=pid,
            phase=self.state.phase.value,
            own_body=[c.as_tuple() for c in snake.body],
            own_head=snake.head.as_tuple(),
            own_direction=snake.direction.delta,
            own_length=snake.length,
            own_gold_count=self.gold_counts[pid],
            visible_brightness={c.as_tuple(): b for c, b in vis.brightness.items()},
            visible_enemy_cells=[c.as_tuple() for c in enemy_visible_cells],
            enemy_head_visible=enemy_head_visible,
            enemy_direction_visible=(
                enemy.direction.delta
                if enemy_head_visible and enemy is not None
                else None
            ),
            enemy_length_visible=(
                enemy.length if enemy_head_visible and enemy is not None else None
            ),
            enemy_gold_count=self.gold_counts[enemy_pid],
            abilities={
                "sprint": ab.sprint_remaining(self.clock) if ab.has_sprint(self.clock) else 0.0,
                "shield": ab.shield_remaining(self.clock) if ab.shield_charges > 0 else 0.0,
                "lantern": ab.lantern_remaining(self.clock) if ab.has_lantern(self.clock) else 0.0,
            },
            boosting=ab.is_boosting(self.clock),
            view_radius=self.visibility.view_radius(lantern, reveal_active),
            reveal_active=reveal_active,
            reveal_remaining=self.reveal_expiries[pid].remaining(REVEAL, self.clock),
            events=[
                {"text": e.text, "player": e.player, "at": e.at}
                for e in self.events[-5:]
            ],
            winner=self.winner,
            draw=self.draw,
            clock=self.clock,
            countdown_remaining=max(0.0, self.countdown_remaining),
            enemy_alive=bool(enemy is not None and enemy.alive),
            target_indicator=indicator,
            target_proximity=proximity,
            target_kind=target_kind,
            visible_fruit=visible_fruit,
            visible_gold=visible_gold,
        )

    # ================================================================ debug
    def debug_snapshot(self) -> dict[str, object]:
        """仅 DEBUG 模式使用。包含全部隐藏信息。"""
        return {
            "phase": self.state.phase.value,
            "clock": self.clock,
            "tick_count": self.tick_count,
            "gold_trigger": self.gold_trigger,
            "normal_eaten": self.normal_eaten_this_round,
            "round_index": self.round_index,
            "fruit": (
                {"cell": self.fruits.fruit.cell.as_tuple(), "type": self.fruits.fruit.type.value}
                if self.fruits.fruit
                else None
            ),
            "gold": self.fruits.gold.cell.as_tuple() if self.fruits.gold else None,
            "gold_counts": dict(self.gold_counts),
            "snakes": {
                pid: {
                    "body": [c.as_tuple() for c in s.body],
                    "direction": s.direction.delta,
                    "alive": s.alive,
                    "reason": s.death_reason,
                    "length": s.length,
                }
                for pid, s in self.snakes.items()
            },
            "winner": self.winner,
            "draw": self.draw,
        }

    # ================================================================ 便利
    def is_over(self) -> bool:
        return self.state.phase in (GamePhase.GAME_OVER, GamePhase.DRAW_RESTART)

    def tick_deadline_passed(self) -> bool:
        """是否已到下一轮切换时刻（金苹果 3 秒后）。"""
        nxt = getattr(self, "_next_round_at", None)
        return nxt is not None and self.clock >= nxt
