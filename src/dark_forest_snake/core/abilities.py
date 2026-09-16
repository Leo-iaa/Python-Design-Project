"""能力系统：疾跑 / 护盾 / 灯笼。

关键规则：
- 吃到能力果 → 获得该能力。
- 疾跑 ≠ 自动加速：必须有 ``sprint_held`` 输入才加速。
- 护盾只抵挡 1 次致死撞击，触发后立即消耗。
- 灯笼把 VIEW_RADIUS 从 1 提到 2，到期自动恢复。
所有时间判定走 ExpirySet（绝对过期时刻），不依赖 sleep / Timer。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dark_forest_snake.config import (
    BOOST_MOVE_INTERVAL,
    BASE_MOVE_INTERVAL,
    LANTERN_DURATION,
    SHIELD_CHARGES,
    SHIELD_DURATION,
    SPRINT_DURATION,
)
from dark_forest_snake.core.clock import LANTERN, SHIELD, SPRINT, ExpirySet
from dark_forest_snake.core.fruit import FruitType


@dataclass
class AbilityState:
    """单个玩家的能力状态。"""

    expiries: ExpirySet = field(default_factory=ExpirySet)
    shield_charges: int = 0
    sprint_held: bool = False

    # ------------------------------------------------------------ 授予
    def grant(self, fruit_type: FruitType, now: float) -> None:
        key = fruit_type.value if isinstance(fruit_type, FruitType) else str(fruit_type)
        self.grant_by_key(key, now)

    def grant_by_key(self, key: str, now: float) -> None:
        # 兼容 FruitType 枚举本身或字符串两种入参
        if isinstance(key, FruitType):
            key = key.value
        if key == SPRINT:
            self.expiries.grant(SPRINT, now, SPRINT_DURATION)
        elif key == SHIELD:
            self.expiries.grant(SHIELD, now, SHIELD_DURATION)
            self.shield_charges = max(self.shield_charges, SHIELD_CHARGES)
        elif key == LANTERN:
            self.expiries.grant(LANTERN, now, LANTERN_DURATION)
        else:
            raise ValueError(f"未知能力: {key}")

    def grant_all(self, now: float) -> None:
        """金苹果：同时获得三种能力。"""
        self.grant_by_key(SPRINT, now)
        self.grant_by_key(SHIELD, now)
        self.grant_by_key(LANTERN, now)

    # ------------------------------------------------------------ 查询
    def has_sprint(self, now: float) -> bool:
        return self.expiries.active(SPRINT, now)

    def has_lantern(self, now: float) -> bool:
        return self.expiries.active(LANTERN, now)

    def has_shield(self, now: float) -> bool:
        return self.shield_charges > 0 and self.expiries.active(SHIELD, now)

    def sprint_remaining(self, now: float) -> float:
        return self.expiries.remaining(SPRINT, now)

    def shield_remaining(self, now: float) -> float:
        return self.expiries.remaining(SHIELD, now)

    def lantern_remaining(self, now: float) -> float:
        return self.expiries.remaining(LANTERN, now)

    # ------------------------------------------------------------ 疾跑
    def effective_interval(self, now: float) -> float:
        """当前 Tick 间隔。疾跑必须主动按住，且能力在有效期内。"""
        if self.sprint_held and self.has_sprint(now):
            return BOOST_MOVE_INTERVAL
        return BASE_MOVE_INTERVAL

    def is_boosting(self, now: float) -> bool:
        return self.sprint_held and self.has_sprint(now)

    # ------------------------------------------------------------ 护盾
    def consume_shield(self) -> bool:
        """消耗一层护盾。返回是否成功消耗。"""
        if self.shield_charges > 0:
            self.shield_charges -= 1
            if self.shield_charges <= 0:
                self.expiries.skip(SHIELD)
            return True
        return False

    # ------------------------------------------------------------ 时间
    def tick(self, now: float) -> list[str]:
        """推进时间，返回过期能力列表。护盾过期时同步清零层数。"""
        expired = self.expiries.cleanup(now)
        if SHIELD in expired:
            self.shield_charges = 0
        return expired

    def reset(self) -> None:
        self.expiries = ExpirySet()
        self.shield_charges = 0
        self.sprint_held = False


class AbilitySystem:
    """多玩家能力状态容器。"""

    def __init__(self, player_ids: list[int]) -> None:
        self.states: dict[int, AbilityState] = {pid: AbilityState() for pid in player_ids}

    def __getitem__(self, pid: int) -> AbilityState:
        return self.states[pid]

    def tick(self, now: float) -> dict[int, list[str]]:
        return {pid: st.tick(now) for pid, st in self.states.items()}

    def reset(self) -> None:
        for st in self.states.values():
            st.reset()
