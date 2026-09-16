"""碰撞判定。完全确定性，单机与 LAN 服务器共用同一套逻辑。

同步 Tick 的判定流程（绝不「先移动 P1 再移动 P2」）：
    1. 快照旧状态
    2. 分别计算 P1 / P2 的 nextHead
    3. 统一判定所有碰撞，得到每个玩家的事件列表
    4. 统一提交状态

优先级（当多种碰撞同时发生时，按此顺序消费，保证可复现）：
    R1 撞墙              → 该玩家死亡
    R2 头对头 → 同格     → 比长度；长者存活、短者死亡、等长则双方死亡(平局)
    R3 头撞自己身体      → 该玩家死亡
    R4 头撞敌方身体      → 该玩家死亡
    R5 双方同时死亡      → 平局

护盾（shield_charges）在 R1~R4 中抵挡一次致死事件：消耗 1 点护盾，
该玩家本 Tick 不死，并且**视为原地不动/回弹**（蛇头不前进到致死格）。
本 Tick 也不会因为「已用掉的护盾」而被 R2 的对手反杀两次。

判定所需信息全部来自入参，函数本身不读取任何全局可变状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from dark_forest_snake.core.geometry import Cell
from dark_forest_snake.core.snake import Snake


class DeathReason(str, Enum):
    WALL = "wall"
    SELF = "self"
    ENEMY_BODY = "enemy_body"
    HEAD_TO_HEAD = "head_to_head"
    TRAP = "trap"


class CollisionOutcome(str, Enum):
    OK = "ok"
    DEAD = "dead"
    SHIELDED = "shielded"


@dataclass
class PlayerCollisionResult:
    """单个玩家在本次 Tick 的碰撞结论。"""

    outcome: CollisionOutcome = CollisionOutcome.OK
    reason: DeathReason | None = None
    shield_consumed: bool = False
    # 致死时蛇头实际没有推进（回弹），调用方据此不提交 head 位移
    blocked: bool = False


@dataclass
class CollisionReport:
    results: dict[int, PlayerCollisionResult] = field(default_factory=dict)
    # 头对头且等长 → 双方死亡，整局重开
    head_to_head: bool = False
    head_to_head_draw: bool = False
    events: list[str] = field(default_factory=list)

    @property
    def any_death(self) -> bool:
        return any(r.outcome is CollisionOutcome.DEAD for r in self.results.values())

    @property
    def both_dead(self) -> bool:
        return (
            len(self.results) == 2
            and all(r.outcome is CollisionOutcome.DEAD for r in self.results.values())
        )

    def died(self, pid: int) -> bool:
        r = self.results.get(pid)
        return r is not None and r.outcome is CollisionOutcome.DEAD


def _in_bounds(cell: Cell, width: int, height: int) -> bool:
    """地图四周为致死墙体，因此可通行区域是 0..width-1。"""
    return 0 <= cell.x < width and 0 <= cell.y < height


def _blocked_by_body(
    next_head: Cell,
    own: Snake,
    other: Snake | None,
    own_grow: bool,
    other_grow: bool,
) -> tuple[bool, bool]:
    """返回 (撞到自己, 撞到敌方)。

    尾巴腾空规则：本 Tick 若对方不成长，其尾巴会离开原格；
    自己同理（但自己撞自己尾巴永远不可能，因为头追不上尾）。
    """
    own_cells = set(own.body)
    if own_grow:
        # 自己成长时尾巴不动，占满全身
        pass
    else:
        # 自己非成长：头移动后旧尾巴会腾出，但新头不可能等于旧尾巴
        # （长度 ≥ 2 时），故仍按全身判定更严格也更安全。
        pass
    hit_self = next_head in own_cells

    hit_other = False
    if other is not None:
        other_cells = set(other.body)
        tail = other.body[-1]
        if not other_grow:
            # 对方尾巴将腾出这一格
            other_cells.discard(tail)
        hit_other = next_head in other_cells

    return hit_self, hit_other


def resolve_tick(
    snakes: dict[int, Snake],
    planned_heads: dict[int, Cell],
    grow_flags: dict[int, bool],
    shield_charges: dict[int, int],
    width: int,
    height: int,
    movers: set[int] | None = None,
) -> CollisionReport:
    """统一的碰撞判定。

    参数
    ----
    snakes: pid -> 旧状态蛇（未被修改）
    planned_heads: pid -> 本 Tick 想去的蛇头位置
        （不动的蛇传当前蛇头，仅用于占位与头对头判定）
    grow_flags: pid -> 本 Tick 是否成长（不动的蛇传 True：尾巴不腾空）
    shield_charges: pid -> 当前护盾层数（不修改入参，返回消费结果）
    movers: 本 Tick 实际移动的 pid 集合；None 表示全部移动。
        不动的蛇不参与 R1/R3/R4（其 planned_head 就是当前头，
        撞墙/撞己判定会误判），只可能被头对头波及。
    """
    report = CollisionReport()
    pids = sorted(planned_heads.keys())
    for pid in pids:
        report.results[pid] = PlayerCollisionResult()

    def _kill(pid: int, reason: DeathReason) -> bool:
        """尝试杀死某玩家；有护盾则消耗护盾并标记 blocked。返回是否真的死了。"""
        res = report.results[pid]
        if res.outcome is CollisionOutcome.DEAD:
            return True
        if shield_charges.get(pid, 0) > 0 and not res.shield_consumed:
            res.outcome = CollisionOutcome.SHIELDED
            res.shield_consumed = True
            res.blocked = True
            report.events.append(f"shield_break:{pid}")
            return False
        res.outcome = CollisionOutcome.DEAD
        res.reason = reason
        res.blocked = True
        return True

    # ---- R2 先判头对头（需要双方 nextHead 相同，且双方都真的会到达） ----
    if len(pids) == 2:
        a, b = pids
        if planned_heads[a] == planned_heads[b]:
            report.head_to_head = True
            la, lb = snakes[a].length, snakes[b].length
            report.events.append(f"head_to_head:{a}:{b}")
            if la == lb:
                # 等长 → 平局，整局重开。护盾不改变这一结果。
                report.head_to_head_draw = True
                report.events.append(f"head_to_head_draw:{a}:{b}")
                for pid in (a, b):
                    res = report.results[pid]
                    res.outcome = CollisionOutcome.DEAD
                    res.reason = DeathReason.HEAD_TO_HEAD
                    res.blocked = True
                    res.shield_consumed = False
            else:
                loser, winner = (b, a) if la > lb else (a, b)
                # 败者先尝试用护盾抵挡；能挡则双方都不死，各自回弹。
                survived = not _kill(loser, DeathReason.HEAD_TO_HEAD)
                if survived:
                    report.results[winner].outcome = CollisionOutcome.OK
                    report.events.append(f"head_to_head_loser_shielded:{loser}")
                else:
                    report.results[winner].outcome = CollisionOutcome.OK
                    report.events.append(f"head_to_head_win:{winner}")
            return report

    # ---- 单方致死判定：按 pid 顺序，规则完全确定 ----
    for pid in pids:
        if movers is not None and pid not in movers:
            # 不动的蛇：其 planned_head 就是当前头，R1/R3/R4 必然误判，跳过
            continue
        head = planned_heads[pid]
        own = snakes[pid]
        other = next((snakes[o] for o in pids if o != pid), None)

        if not _in_bounds(head, width, height):
            _kill(pid, DeathReason.WALL)
            continue

        own_grow = grow_flags.get(pid, False)
        other_grow = grow_flags.get(other_pid(pid, pids), False) if other is not None else False

        hit_self, hit_other = _blocked_by_body(head, own, other, own_grow, other_grow)
        if hit_self:
            _kill(pid, DeathReason.SELF)
            continue
        if hit_other:
            _kill(pid, DeathReason.ENEMY_BODY)
            continue

    if report.both_dead:
        report.events.append("both_dead")

    return report


def other_pid(pid: int, pids: list[int]) -> int:
    for p in pids:
        if p != pid:
            return p
    return pid


def _force_kill(pid: int, report: CollisionReport, reason: DeathReason) -> None:
    res = report.results[pid]
    if res.outcome is CollisionOutcome.DEAD:
        return
    res.outcome = CollisionOutcome.DEAD
    res.reason = reason
    res.blocked = True


# ------------------------------------------------------------------ 兼容包装
class CollisionSystem:
    """面向对象包装，便于测试与外部调用。"""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def in_bounds(self, cell: Cell) -> bool:
        return _in_bounds(cell, self.width, self.height)

    def resolve(
        self,
        snakes: dict[int, Snake],
        planned_heads: dict[int, Cell],
        grow_flags: dict[int, bool] | None = None,
        shield_charges: dict[int, int] | None = None,
        movers: set[int] | None = None,
    ) -> CollisionReport:
        return resolve_tick(
            snakes=snakes,
            planned_heads=planned_heads,
            grow_flags=grow_flags or {},
            shield_charges=shield_charges or {},
            width=self.width,
            height=self.height,
            movers=movers,
        )
