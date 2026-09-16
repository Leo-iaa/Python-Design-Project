"""客户端：连接 Host 的权威服务器，只负责发输入、收视角。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from enum import Enum

from dark_forest_snake.core.geometry import Direction
from dark_forest_snake.network import protocol as proto
from dark_forest_snake.network.protocol import Message, ProtocolError

log = logging.getLogger("dark_forest_snake.client")


class ClientStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WAITING = "waiting"      # 已连接，等对手
    PLAYING = "playing"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ClientError(Exception):
    pass


class GameClient:
    """LAN 客户端。

    客户端**不运行** Game Engine，也不持有任何隐藏目标坐标。
    它只：
      - 上行 Direction / SprintPressed
      - 下行接收已裁剪的 PlayerViewState 并交给渲染层
    """

    def __init__(
        self,
        host: str,
        port: int = 8765,
        *,
        on_view: Callable[[dict], None] | None = None,
        on_status: Callable[[ClientStatus, str], None] | None = None,
        on_event: Callable[[str, int | None], None] | None = None,
        connect_timeout: float = 8.0,
    ) -> None:
        self.host = host
        self.port = port
        self.player_id: int | None = None
        self.status = ClientStatus.IDLE
        self.last_error: str | None = None
        self.latest_view: dict | None = None
        self.phase: str = "menu"
        self.winner: int | None = None
        self.draw: bool = False
        self.map_width: int = 0
        self.map_height: int = 0

        self._on_view = on_view
        self._on_status = on_status
        self._on_event = on_event
        self._ws = None
        self._recv_task: asyncio.Task | None = None
        self._connect_timeout = connect_timeout
        self._closing = False

    # ================================================================ 状态
    def _set_status(self, st: ClientStatus, text: str = "") -> None:
        self.status = st
        if st is ClientStatus.ERROR and text:
            self.last_error = text
        if self._on_status:
            with contextlib.suppress(Exception):
                self._on_status(st, text)
        log.info("status=%s %s", st.value, text)

    # ================================================================ 连接
    async def connect(self) -> None:
        import websockets

        self._set_status(ClientStatus.CONNECTING, f"{self.host}:{self.port}")
        url = f"ws://{self.host}:{self.port}"
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(url, ping_interval=10, ping_timeout=20),
                timeout=self._connect_timeout,
            )
        except asyncio.TimeoutError:
            self._set_status(
                ClientStatus.ERROR,
                f"连接超时：{self.host}:{self.port} 无响应，请检查 IP 与防火墙",
            )
            raise ClientError(self.last_error or "连接超时") from None
        except OSError as exc:
            self._set_status(
                ClientStatus.ERROR,
                f"无法连接到 {self.host}:{self.port}（{exc}）。请确认 Host 已启动、IP 正确、防火墙已放行",
            )
            raise ClientError(self.last_error or "连接失败") from exc
        except Exception as exc:
            self._set_status(ClientStatus.ERROR, f"连接失败: {exc}")
            raise ClientError(f"连接失败: {exc}") from exc

        self._set_status(ClientStatus.CONNECTED, "已连接，等待分配席位")
        # 发送加入请求
        await self._send(Message(proto.MsgType.JOIN.value, {"name": ""}))
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self) -> None:
        self._closing = True
        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._set_status(ClientStatus.DISCONNECTED, "已断开")

    # ================================================================ 接收
    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = Message.decode(raw)
                except ProtocolError as exc:
                    log.warning("收到非法消息: %s", exc)
                    continue
                self._dispatch(msg)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not self._closing:
                self._set_status(ClientStatus.ERROR, f"连接中断: {exc}")
                await self._notify_disconnect("与 Host 的连接已断开")
        finally:
            if not self._closing and self.status not in (
                ClientStatus.ERROR,
                ClientStatus.DISCONNECTED,
            ):
                self._set_status(ClientStatus.DISCONNECTED, "服务器已关闭")

    def _dispatch(self, msg: Message) -> None:
        p = msg.payload
        if msg.type == proto.MsgType.WELCOME.value:
            self.player_id = int(p["player"])
            self.map_width = int(p.get("width", 0))
            self.map_height = int(p.get("height", 0))
            self._set_status(ClientStatus.WAITING, f"已加入，你是 P{self.player_id + 1}")
        elif msg.type == proto.MsgType.STATE.value:
            self.latest_view = p.get("view")
            if self.status is ClientStatus.WAITING:
                self._set_status(ClientStatus.PLAYING, "对局开始")
            if self._on_view and self.latest_view is not None:
                with contextlib.suppress(Exception):
                    self._on_view(self.latest_view)
        elif msg.type == proto.MsgType.PHASE.value:
            self.phase = str(p.get("phase", ""))
            self.winner = p.get("winner")
            self.draw = bool(p.get("draw"))
        elif msg.type == proto.MsgType.EVENT.value:
            if self._on_event:
                with contextlib.suppress(Exception):
                    self._on_event(str(p.get("text", "")), p.get("player"))
        elif msg.type == proto.MsgType.ROOM_FULL.value:
            self._set_status(ClientStatus.ERROR, "房间已满（最多 2 人）")
            asyncio.create_task(self._notify_disconnect("房间已满"))
        elif msg.type == proto.MsgType.PEER_LEFT.value:
            self._set_status(ClientStatus.ERROR, str(p.get("text", "对方已离开")))
            asyncio.create_task(self._notify_disconnect(str(p.get("text", "对方已离开"))))
        elif msg.type == proto.MsgType.ERROR.value:
            self._set_status(ClientStatus.ERROR, str(p.get("text", "服务器错误")))

    async def _notify_disconnect(self, text: str) -> None:
        if self._on_status:
            with contextlib.suppress(Exception):
                self._on_status(ClientStatus.ERROR, text)

    # ================================================================ 发送
    async def _send(self, msg: Message) -> None:
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            await self._ws.send(msg.encode())

    async def send_direction(self, direction: Direction) -> None:
        """上行转向意图。注意：只发方向，绝不发坐标。"""
        await self._send(
            Message(proto.MsgType.DIRECTION.value, {"direction": direction.name})
        )

    async def send_sprint(self, pressed: bool) -> None:
        await self._send(Message(proto.MsgType.SPRINT.value, {"pressed": bool(pressed)}))

    async def request_restart(self) -> None:
        await self._send(Message(proto.MsgType.RESTART.value, {}))

    async def send_leave(self) -> None:
        await self._send(Message(proto.MsgType.LEAVE.value, {}))
