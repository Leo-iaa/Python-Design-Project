"""统一时间管理。

禁止在游戏规则里散落 ``time.sleep()`` / ``Timer``。
所有能力持续时间都用「绝对过期时刻」表示，由 GameClock 推进的
逻辑时间（accumulated）来判定，因此 Game Engine 完全可确定性重放：
注入固定的 dt 序列即可复现任意一局。
"""

from __future__ import annotations


class GameClock:
    """单调递增的逻辑时钟（秒）。

    不使用 time.time()，避免受系统时钟调整影响；dt 由主循环或测试显式注入。
    """

    __slots__ = ("_now",)

    def __init__(self, start: float = 0.0) -> None:
        self._now: float = float(start)

    @property
    def now(self) -> float:
        return self._now

    def advance(self, dt: float) -> float:
        if dt < 0:
            raise ValueError("dt 不能为负")
        self._now += dt
        return self._now

    def reset(self, start: float = 0.0) -> None:
        self._now = float(start)

    def __repr__(self) -> str:  # pragma: no cover
        return f"GameClock(now={self._now:.3f})"


class ExpirySet:
    """一组「能力过期时刻」，统一管理检查与查询。"""

    __slots__ = ("_expiries",)

    def __init__(self) -> None:
        self._expiries: dict[str, float] = {}

    def grant(self, key: str, now: float, duration: float) -> float:
        """授予/刷新某能力，返回过期时刻。

        重复获得同一能力时取「更晚」的过期时刻（叠加而非覆盖），
        避免吃到第二个同类果子反而缩短时间。
        """
        expires = now + duration
        current = self._expiries.get(key)
        if current is None or expires > current:
            self._expiries[key] = expires
        return self._expiries[key]

    def active(self, key: str, now: float) -> bool:
        exp = self._expiries.get(key)
        return exp is not None and now < exp

    def remaining(self, key: str, now: float) -> float:
        exp = self._expiries.get(key)
        if exp is None:
            return 0.0
        return max(0.0, exp - now)

    def skip(self, key: str) -> None:
        """立即清除某能力（未消耗完的护盾被打掉等）。"""
        self._expiries.pop(key, None)

    def cleanup(self, now: float) -> list[str]:
        """清除所有已过期的能力，返回被清除的 key 列表。"""
        expired = [k for k, exp in self._expiries.items() if now >= exp]
        for k in expired:
            del self._expiries[k]
        return expired

    def positions(self) -> dict[str, float]:
        return dict(self._expiries)

    def __contains__(self, key: str) -> bool:
        return key in self._expiries

    def __repr__(self) -> str:  # pragma: no cover
        return f"ExpirySet({self._expiries})"


# ---------------------------------------------------------------- 能力 key
SPRINT = "sprint"
SHIELD = "shield"
LANTERN = "lantern"
REVEAL = "reveal"

ABILITY_KEYS = (SPRINT, SHIELD, LANTERN)
