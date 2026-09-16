"""游戏状态机。

刻意使用单一 ``GamePhase`` 枚举，避免 is_started / is_playing /
gold_active / is_dead 这类松散布尔状态互相冲突。
"""

from __future__ import annotations

from enum import Enum


class GamePhase(Enum):
    MENU = "menu"
    WAITING = "waiting"          # 等待第二个玩家加入（LAN）
    COUNTDOWN = "countdown"      # 开局倒计时
    PLAYING_NORMAL = "playing_normal"
    PLAYING_GOLDEN = "playing_golden"
    GAME_OVER = "game_over"
    DRAW_RESTART = "draw_restart"  # 平局，整局重开

    @property
    def is_playing(self) -> bool:
        return self in (GamePhase.PLAYING_NORMAL, GamePhase.PLAYING_GOLDEN)

    @property
    def is_finished(self) -> bool:
        return self in (GamePhase.GAME_OVER, GamePhase.DRAW_RESTART)


# 合法转移表：任何未列出的转移都会抛错，防止状态机被随意绕过。
TRANSITIONS: dict[GamePhase, frozenset[GamePhase]] = {
    GamePhase.MENU: frozenset({GamePhase.WAITING, GamePhase.COUNTDOWN, GamePhase.MENU}),
    GamePhase.WAITING: frozenset({GamePhase.COUNTDOWN, GamePhase.MENU}),
    GamePhase.COUNTDOWN: frozenset({GamePhase.PLAYING_NORMAL, GamePhase.MENU}),
    GamePhase.PLAYING_NORMAL: frozenset(
        {
            GamePhase.PLAYING_GOLDEN,
            GamePhase.GAME_OVER,
            GamePhase.DRAW_RESTART,
        }
    ),
    GamePhase.PLAYING_GOLDEN: frozenset(
        {
            GamePhase.PLAYING_NORMAL,
            GamePhase.GAME_OVER,
            GamePhase.DRAW_RESTART,
        }
    ),
    GamePhase.GAME_OVER: frozenset({GamePhase.MENU, GamePhase.COUNTDOWN}),
    GamePhase.DRAW_RESTART: frozenset({GamePhase.MENU, GamePhase.COUNTDOWN}),
}


class InvalidTransition(RuntimeError):
    pass


class GameStateMachine:
    __slots__ = ("_phase", "_winner", "_reason", "_history")

    def __init__(self, phase: GamePhase = GamePhase.MENU) -> None:
        self._phase = phase
        self._winner: int | None = None
        self._reason: str | None = None
        self._history: list[GamePhase] = [phase]

    @property
    def phase(self) -> GamePhase:
        return self._phase

    @property
    def winner(self) -> int | None:
        return self._winner

    @property
    def reason(self) -> str | None:
        return self._reason

    @property
    def history(self) -> list[GamePhase]:
        return list(self._history)

    def can_transition(self, target: GamePhase) -> bool:
        return target in TRANSITIONS.get(self._phase, frozenset())

    def transition(
        self,
        target: GamePhase,
        *,
        winner: int | None = None,
        reason: str | None = None,
    ) -> GamePhase:
        if target is self._phase:
            return self._phase
        if not self.can_transition(target):
            raise InvalidTransition(f"{self._phase.value} -> {target.value} 不合法")
        self._phase = target
        self._history.append(target)
        if target in (GamePhase.GAME_OVER, GamePhase.DRAW_RESTART):
            self._winner = winner
            self._reason = reason
        elif target in (GamePhase.COUNTDOWN, GamePhase.MENU):
            self._winner = None
            self._reason = None
        return self._phase

    def reset(self, phase: GamePhase = GamePhase.MENU) -> None:
        self._phase = phase
        self._winner = None
        self._reason = None
        self._history = [phase]
