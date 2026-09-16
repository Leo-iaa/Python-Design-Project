"""房间：管理一局的玩家席位与连接。

房间状态机：
    EMPTY → WAITING（1 人）→ READY（2 人）→ PLAYING → FINISHED
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.state import GamePhase


class RoomStatus(str, Enum):
    EMPTY = "empty"
    WAITING = "waiting"     # 只有 1 人
    READY = "ready"         # 2 人齐了，等待开始
    PLAYING = "playing"
    FINISHED = "finished"


class RoomError(Exception):
    pass


@dataclass
class Seat:
    """一个玩家席位。connection 由 server 层注入（可能是 websocket 或内存对象）。"""

    player_id: int
    connection: object | None = None
    name: str = ""
    ready: bool = False
    connected: bool = True

    @property
    def occupied(self) -> bool:
        return self.connection is not None and self.connected


@dataclass
class Room:
    room_id: str
    width: int
    height: int
    seed: int | None = None
    maximal_players: int = 2

    seats: dict[int, Seat] = field(default_factory=dict)
    status: RoomStatus = RoomStatus.EMPTY
    game: Game | None = None
    _closed: bool = False

    # ------------------------------------------------------------ 席位管理
    def join(self, connection: object, name: str = "") -> int:
        """加入房间，返回分配的 player_id。房间满则抛 RoomError。"""
        if self._closed:
            raise RoomError("房间已关闭")
        for pid in (P1, P2):
            seat = self.seats.get(pid)
            if seat is None or not seat.occupied:
                self.seats[pid] = Seat(
                    player_id=pid, connection=connection, name=name or f"P{pid + 1}"
                )
                self._refresh_status()
                return pid
        raise RoomError("房间已满")

    def leave(self, player_id: int) -> None:
        seat = self.seats.get(player_id)
        if seat is not None:
            seat.connected = False
            seat.connection = None
        self._refresh_status()
        if self.status in (RoomStatus.PLAYING, RoomStatus.READY):
            self.status = RoomStatus.WAITING

    def close(self) -> None:
        self._closed = True
        for seat in self.seats.values():
            seat.connected = False
            seat.connection = None

    def _refresh_status(self) -> None:
        count = self.players_in_room()
        if count == 0:
            self.status = RoomStatus.EMPTY
        elif count == 1:
            self.status = RoomStatus.WAITING
        else:
            if self.status not in (RoomStatus.PLAYING, RoomStatus.FINISHED):
                self.status = RoomStatus.READY

    def players_in_room(self) -> int:
        return sum(1 for s in self.seats.values() if s.occupied)

    def connected_players(self) -> list[int]:
        return sorted(pid for pid, s in self.seats.items() if s.occupied)

    def is_full(self) -> bool:
        return self.players_in_room() >= self.maximal_players

    def connection_of(self, player_id: int) -> object | None:
        seat = self.seats.get(player_id)
        return seat.connection if seat else None

    # ------------------------------------------------------------ 游戏控制
    def start_game(self, *, countdown: float = 0.0) -> Game:
        if self.players_in_room() < self.maximal_players:
            raise RoomError("人数不足，无法开始")
        seed = self.seed if self.seed is not None else random.randrange(1 << 30)
        self.game = Game(width=self.width, height=self.height, seed=seed)
        self.game.start_match(countdown=countdown)
        self.status = RoomStatus.PLAYING
        return self.game

    def restart(self) -> Game:
        if self.game is None:
            return self.start_game(countdown=0.0)
        if self.game.state.phase is GamePhase.DRAW_RESTART:
            self.game.restart_after_draw()
        else:
            self.game.full_reset()
            self.game.start_match(countdown=0.0)
        self.status = RoomStatus.PLAYING
        return self.game

    def tick(self, dt: float) -> None:
        if self.game is None:
            return
        self.game.update(dt)
        if self.game.is_over():
            self.status = RoomStatus.FINISHED
