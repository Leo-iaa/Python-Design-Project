"""权威服务器：Host 端运行的 websocket 服务。

职责边界（服务端权威）：
    服务器负责 Tick / Snake / Fruit / Gold Apple / Hidden Trigger /
    Collision / Ability / Score / Winner / Visibility。
    客户端只能发送 Direction 与 SprintPressed。

信息隐藏：
    服务器知道 fruit.position / gold.position / enemy.full_body，
    但**绝不**把它们发给客户端。每个玩家收到的是按自己的视野裁剪过的
    PlayerViewState —— 而不是"发全量再靠画面遮挡"。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable

from dark_forest_snake import config as C
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Direction
from dark_forest_snake.network import protocol as proto
from dark_forest_snake.network.protocol import Message, ProtocolError
from dark_forest_snake.network.room import Room, RoomError, RoomStatus

log = logging.getLogger("dark_forest_snake.server")

# 服务器 Tick 频率（快照发送频率），与游戏内部移动 Tick 解耦
SNAPSHOT_INTERVAL = 1 / 60
RECV_TIMEOUT = 30.0


class ClientSession:
    """一个已连接的客户端。"""

    def __init__(self, websocket, room: Room) -> None:
        self.ws = websocket
        self.room = room
        self.player_id: int | None = None
        self.alive = True
        self._send_lock = asyncio.Lock()

    async def send(self, msg: Message) -> None:
        if not self.alive:
            return
        async with self._send_lock:
            with contextlib.suppress(Exception):
                await self.ws.send(msg.encode())

    async def send_error(self, text: str) -> None:
        await self.send(proto.error(text))


class GameServer:
    """权威游戏服务器。

    用法：
        server = GameServer(host="0.0.0.0", port=8765)
        await server.run()            # 一直服务
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        *,
        width: int = C.MAP_WIDTH,
        height: int = C.MAP_HEIGHT,
        seed: int | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.seed = seed
        self.room = Room(
            room_id="lan",
            width=width,
            height=height,
            seed=seed,
        )
        self.sessions: list[ClientSession] = []
        self._tick_task: asyncio.Task | None = None
        self._auto_start = True
        self._on_log = on_log
        self._closing = False

    def log(self, text: str) -> None:
        log.info(text)
        if self._on_log:
            with contextlib.suppress(Exception):
                self._on_log(text)

    # ================================================================ 生命周期
    async def run(self) -> None:
        import websockets

        self._tick_task = asyncio.create_task(self._tick_loop())
        self.log(f"服务器已启动: ws://{self.host}:{self.port}")
        try:
            async with websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=10,
                ping_timeout=20,
            ):
                await asyncio.Future()  # 一直运行
        except asyncio.CancelledError:
            pass
        finally:
            self._closing = True
            if self._tick_task:
                self._tick_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._tick_task
            self.log("服务器已关闭")

    async def shutdown(self) -> None:
        self._closing = True
        if self._tick_task:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task

    # ================================================================ 连接处理
    async def _handle_client(self, websocket) -> None:
        session = ClientSession(websocket, self.room)
        self.sessions.append(session)
        peer = getattr(websocket, "remote_address", ("?", 0))
        self.log(f"客户端连接: {peer}")

        try:
            if self.room.is_full():
                await session.send(proto.room_full())
                await websocket.close()
                return

            # 只有游戏未开始时才允许加入
            if self.room.status in (RoomStatus.PLAYING, RoomStatus.FINISHED):
                await session.send_error("对局已开始，请等待本局结束")
                await websocket.close()
                return

            try:
                pid = self.room.join(session, name="")
            except RoomError as exc:
                await session.send(proto.room_full())
                await websocket.close()
                self.log(f"加入失败: {exc}")
                return

            session.player_id = pid
            await session.send(
                proto.welcome(pid, self.width, self.height, self.room.game.seed if self.room.game else self.seed)
            )
            self.log(f"玩家 P{pid + 1} 加入，房间人数 {self.room.players_in_room()}")

            # 两人齐了就开局
            if self.room.is_full() and self._auto_start:
                self.room.start_game(countdown=C.COUNTDOWN_DURATION)
                await self._broadcast_phase()
                self.log("两名玩家已就位，对局开始")

            async for raw in websocket:
                await self._on_message(session, raw)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 网络异常不应弄崩服务器
            self.log(f"客户端处理异常: {exc!r}")
        finally:
            await self._drop_session(session)

    async def _drop_session(self, session: ClientSession) -> None:
        session.alive = False
        if session in self.sessions:
            self.sessions.remove(session)
        if session.player_id is not None:
            self.room.leave(session.player_id)
            self.log(f"玩家 P{session.player_id + 1} 断开")
            await self._broadcast(proto.peer_left("对方已离开房间"))

    async def _on_message(self, session: ClientSession, raw) -> None:
        try:
            msg = Message.decode(raw)
            proto.validate_client_message(msg)
        except ProtocolError as exc:
            await session.send_error(f"协议错误: {exc}")
            return

        mtype = msg.type

        if mtype == proto.MsgType.PING.value:
            await session.send(proto.pong())
            return

        if mtype == proto.MsgType.LEAVE.value:
            session.alive = False
            return

        if mtype == proto.MsgType.RESTART.value:
            await self._handle_restart(session)
            return

        if mtype == proto.MsgType.READY.value:
            if session.player_id is not None:
                seat = self.room.seats.get(session.player_id)
                if seat:
                    seat.ready = True
            return

        if session.player_id is None:
            return

        game = self.room.game
        if game is None:
            await session.send_error("对局尚未开始")
            return

        if mtype == proto.MsgType.DIRECTION.value:
            name = msg.payload["direction"]
            try:
                direction = Direction[name]
            except KeyError:
                await session.send_error(f"未知方向 {name}")
                return
            game.input_direction(session.player_id, direction)
            return

        if mtype == proto.MsgType.SPRINT.value:
            game.input_sprint(session.player_id, bool(msg.payload["pressed"]))
            return

    async def _handle_restart(self, session: ClientSession) -> None:
        if self.room.status is RoomStatus.FINISHED:
            try:
                self.room.restart()
            except RoomError as exc:
                await session.send_error(str(exc))
                return
            await self._broadcast_phase()
            self.log("对局重新开始")

    # ================================================================ Tick 与广播
    async def _tick_loop(self) -> None:
        loop = asyncio.get_running_loop()
        last = loop.time()
        try:
            while not self._closing:
                await asyncio.sleep(SNAPSHOT_INTERVAL)
                now = loop.time()
                dt = min(now - last, 0.25)
                last = now

                if self.room.game is not None and self.room.status in (
                    RoomStatus.PLAYING,
                    RoomStatus.FINISHED,
                ):
                    prev_phase = self.room.game.state.phase
                    self.room.tick(dt)
                    await self._broadcast_states()
                    if self.room.game.state.phase is not prev_phase:
                        await self._broadcast_phase()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self.log(f"Tick 循环异常: {exc!r}")

    async def _broadcast_states(self) -> None:
        game = self.room.game
        if game is None:
            return
        for pid in self.room.connected_players():
            session = self._session_for(pid)
            if session is None:
                continue
            # 关键：每个玩家拿到的是**按自己视野裁剪后**的视角，不是全量状态
            view = game.view_for(pid).to_dict()
            await session.send(proto.state(view))

    async def _broadcast_phase(self) -> None:
        game = self.room.game
        if game is None:
            return
        phase = game.state.phase
        extra: dict = {"winner": game.winner, "draw": game.draw}
        msg = proto.phase(phase.value, extra)
        await self._broadcast(msg)

    async def _broadcast(self, msg: Message) -> None:
        for session in list(self.sessions):
            if session.alive:
                await session.send(msg)

    def _session_for(self, pid: int) -> ClientSession | None:
        for s in self.sessions:
            if s.player_id == pid and s.alive:
                return s
        return None


# ---------------------------------------------------------------- CLI 入口
def find_lan_ip() -> str:
    """尽力找出一台机器在局域网中的 IP，供 Host 展示给 Client。"""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        # 不真的发包，只是让系统挑选出默认出口网卡
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


async def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    server = GameServer(host=host, port=port, on_log=lambda t: print(f"[server] {t}"))
    await server.run()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
