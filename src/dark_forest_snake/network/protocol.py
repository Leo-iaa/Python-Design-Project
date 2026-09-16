"""网络协议：消息格式定义与编解码。

设计原则：
- 客户端**只能**发送 Direction 与 SprintPressed，绝不能上报自己的坐标。
- 服务端**只**下发 PlayerViewState（已裁剪），绝不下发隐藏目标坐标。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MsgType(str, Enum):
    # ---- 客户端 → 服务端 ----
    JOIN = "join"                # 请求加入房间
    DIRECTION = "direction"      # 转向意图
    SPRINT = "sprint"            # 疾跑按住/松开
    READY = "ready"
    RESTART = "restart"
    PING = "ping"
    LEAVE = "leave"

    # ---- 服务端 → 客户端 ----
    WELCOME = "welcome"          # 加入成功，分配 pid
    STATE = "state"              # PlayerViewState（已裁剪）
    PHASE = "phase"              # 阶段变化
    EVENT = "event"              # 公共事件
    ERROR = "error"
    PONG = "pong"
    PEER_LEFT = "peer_left"
    ROOM_FULL = "room_full"


# 客户端允许发送的消息类型白名单。任何不在此列的入站消息都会被拒绝。
CLIENT_ALLOWED_TYPES = frozenset(
    {
        MsgType.JOIN.value,
        MsgType.DIRECTION.value,
        MsgType.SPRINT.value,
        MsgType.READY.value,
        MsgType.RESTART.value,
        MsgType.PING.value,
        MsgType.LEAVE.value,
    }
)

# 客户端消息允许携带的字段白名单（禁止任何形如 x/y/position 的上报）
CLIENT_ALLOWED_FIELDS = frozenset({"type", "direction", "pressed", "name", "token"})

DIRECTION_NAMES = frozenset({"UP", "DOWN", "LEFT", "RIGHT"})


class ProtocolError(Exception):
    pass


@dataclass
class Message:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> str:
        return json.dumps({"type": self.type, **self.payload}, ensure_ascii=False)

    @staticmethod
    def decode(raw: str | bytes) -> "Message":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"非法 JSON: {exc}") from exc
        if not isinstance(data, dict) or "type" not in data:
            raise ProtocolError("消息缺少 type 字段")
        mtype = data.pop("type")
        return Message(type=str(mtype), payload=data)


def validate_client_message(msg: Message) -> None:
    """严格校验客户端消息，拒绝越权上报。"""
    if msg.type not in CLIENT_ALLOWED_TYPES:
        raise ProtocolError(f"客户端不允许发送 {msg.type}")
    extra = set(msg.payload.keys()) - CLIENT_ALLOWED_FIELDS
    if extra:
        raise ProtocolError(f"客户端消息包含非法字段: {sorted(extra)}")

    if msg.type == MsgType.DIRECTION.value:
        d = msg.payload.get("direction")
        if d not in DIRECTION_NAMES:
            raise ProtocolError(f"非法方向: {d!r}")

    if msg.type == MsgType.SPRINT.value:
        if not isinstance(msg.payload.get("pressed"), bool):
            raise ProtocolError("sprint.pressed 必须是 bool")


# ---------------------------------------------------------------- 构造函数
def welcome(player_id: int, width: int, height: int, seed: int | None) -> Message:
    return Message(
        MsgType.WELCOME.value,
        {"player": player_id, "width": width, "height": height, "seed": seed},
    )


def state(view_dict: dict[str, Any]) -> Message:
    return Message(MsgType.STATE.value, {"view": view_dict})


def phase(name: str, extra: dict[str, Any] | None = None) -> Message:
    return Message(MsgType.PHASE.value, {"phase": name, **(extra or {})})


def event(text: str, player: int | None = None) -> Message:
    return Message(MsgType.EVENT.value, {"text": text, "player": player})


def error(text: str) -> Message:
    return Message(MsgType.ERROR.value, {"text": text})


def room_full() -> Message:
    return Message(MsgType.ROOM_FULL.value, {"text": "房间已满"})


def peer_left(text: str = "对方已离开") -> Message:
    return Message(MsgType.PEER_LEFT.value, {"text": text})


def pong() -> Message:
    return Message(MsgType.PONG.value, {})
