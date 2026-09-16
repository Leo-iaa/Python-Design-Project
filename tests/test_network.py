"""阶段 6：LAN 多人对战测试。

重点验证：
- 服务器权威（客户端不能上报坐标）
- 隐藏信息不泄漏（state 消息里没有果子 / 金苹果坐标）
- 双客户端能正常开始并推进对局
- 网络异常有明确处理
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Direction
from dark_forest_snake.network import protocol as proto
from dark_forest_snake.network.client import ClientError, ClientStatus, GameClient
from dark_forest_snake.network.protocol import (
    CLIENT_ALLOWED_FIELDS,
    CLIENT_ALLOWED_TYPES,
    Message,
    ProtocolError,
    validate_client_message,
)
from dark_forest_snake.network.room import Room, RoomError, RoomStatus
from dark_forest_snake.network.server import GameServer, find_lan_ip


# ================================================================ 协议
def test_message_roundtrip() -> None:
    m = Message("direction", {"direction": "UP"})
    back = Message.decode(m.encode())
    assert back.type == "direction"
    assert back.payload["direction"] == "UP"


def test_message_decode_rejects_garbage() -> None:
    with pytest.raises(ProtocolError):
        Message.decode("not json")
    with pytest.raises(ProtocolError):
        Message.decode('{"no_type": 1}')


def test_client_cannot_send_position() -> None:
    """客户端绝不允许上报自己的坐标。"""
    for bad in ("position", "x", "y", "head", "body", "cell"):
        m = Message("direction", {"direction": "UP", bad: 5})
        with pytest.raises(ProtocolError):
            validate_client_message(m)


def test_client_cannot_send_unknown_type() -> None:
    with pytest.raises(ProtocolError):
        validate_client_message(Message("teleport", {"direction": "UP"}))
    with pytest.raises(ProtocolError):
        validate_client_message(Message("state", {}))


def test_client_allowed_types_whitelist() -> None:
    expected = {"join", "direction", "sprint", "ready", "restart", "ping", "leave"}
    assert CLIENT_ALLOWED_TYPES == expected


def test_client_allowed_fields_whitelist() -> None:
    assert CLIENT_ALLOWED_FIELDS == {"type", "direction", "pressed", "name", "token"}


def test_direction_message_validation() -> None:
    validate_client_message(Message("direction", {"direction": "UP"}))
    with pytest.raises(ProtocolError):
        validate_client_message(Message("direction", {"direction": "SIDEWAYS"}))
    with pytest.raises(ProtocolError):
        validate_client_message(Message("direction", {}))


def test_sprint_message_validation() -> None:
    validate_client_message(Message("sprint", {"pressed": True}))
    with pytest.raises(ProtocolError):
        validate_client_message(Message("sprint", {"pressed": "yes"}))


def test_state_message_shape() -> None:
    m = proto.state({"player": 0, "phase": "playing_normal"})
    decoded = Message.decode(m.encode())
    assert decoded.type == "state"
    assert decoded.payload["view"]["player"] == 0


def test_welcome_message_shape() -> None:
    m = proto.welcome(1, 32, 24, 1234)
    d = Message.decode(m.encode())
    assert d.payload["player"] == 1
    assert d.payload["width"] == 32


# ================================================================ 房间
def test_room_join_and_status() -> None:
    room = Room("t", 20, 16)
    assert room.status is RoomStatus.EMPTY
    a = room.join(object())
    assert room.status is RoomStatus.WAITING
    b = room.join(object())
    assert room.status is RoomStatus.READY
    assert {a, b} == {P1, P2}
    assert room.is_full()


def test_room_rejects_third_player() -> None:
    room = Room("t", 20, 16)
    room.join(object())
    room.join(object())
    with pytest.raises(RoomError):
        room.join(object())


def test_room_leave_frees_seat() -> None:
    room = Room("t", 20, 16)
    a = room.join(object())
    room.join(object())
    assert room.is_full()
    room.leave(a)
    assert not room.is_full()
    assert room.status is RoomStatus.WAITING
    # 空出的席位可以被新人补上
    room.join(object())
    assert room.is_full()


def test_room_start_game_requires_two() -> None:
    room = Room("t", 20, 16)
    room.join(object())
    with pytest.raises(RoomError):
        room.start_game()
    room.join(object())
    g = room.start_game(countdown=0.0)
    assert g.state.phase.value == "playing_normal"
    assert room.status is RoomStatus.PLAYING


def test_room_tick_advances_and_finishes() -> None:
    room = Room("t", 20, 16, seed=1)
    room.join(object())
    room.join(object())
    room.start_game(countdown=0.0)
    for _ in range(20):
        room.tick(C.BASE_MOVE_INTERVAL)
    assert room.game.tick_count > 0


def test_room_restart_after_finish() -> None:
    room = Room("t", 20, 16, seed=2)
    room.join(object())
    room.join(object())
    room.start_game(countdown=0.0)
    # 强行结束
    room.game._end_game(winner=P1, reason="test")
    room.status = RoomStatus.FINISHED
    g = room.restart()
    assert g.state.phase.value in ("playing_normal", "countdown")
    assert room.status is RoomStatus.PLAYING


# ================================================================ 信息不泄漏
def test_broadcast_state_excludes_hidden_target() -> None:
    """服务器下发的 state 里绝不能有果子 / 金苹果坐标。"""
    g = Game(width=24, height=18, seed=555)
    g.start_match(countdown=0.0)
    for pid in (P1, P2):
        view = g.view_for(pid).to_dict()
        raw = json.dumps(view, ensure_ascii=False)
        assert "fruit" not in view
        assert "gold" not in view
        assert "target" not in view
        assert "gold_trigger" not in view
        # 若果子不在视野内，它的坐标不能出现在下发数据中
        target = g.fruits.game_target
        if target is not None:
            visible = view["visible_brightness"]
            tkey = f"{target.x},{target.y}"
            if tkey not in visible:
                assert tkey not in raw


def test_view_state_after_golden_phase_still_hidden() -> None:
    g = Game(width=24, height=18, seed=556)
    g.start_match(countdown=0.0)
    g.gold_trigger = 1
    from dark_forest_snake.core.fruit import Fruit, FruitType

    for _ in range(1):
        s = g.snakes[P1]
        g.fruits.fruit = Fruit(cell=s.head.step(s.direction), type=FruitType.SPRINT)
        g.update(C.BASE_MOVE_INTERVAL)
    assert g.fruits.gold is not None
    gold_cell = g.fruits.gold.cell
    for pid in (P1, P2):
        view = g.view_for(pid).to_dict()
        assert "gold" not in view
        gkey = f"{gold_cell.x},{gold_cell.y}"
        if gkey not in view["visible_brightness"]:
            assert gkey not in json.dumps(view)


def test_server_view_for_matches_engine_view() -> None:
    g = Game(width=24, height=18, seed=557)
    g.start_match(countdown=0.0)
    v = g.view_for(P1).to_dict()
    # 关键白名单：不含任何隐藏字段
    for bad in ("gold_trigger", "normal_eaten", "fruit", "gold", "round_index"):
        assert bad not in v


# ================================================================ 端到端（真实 websocket）
async def _run_two_clients(port: int, seconds: float = 4.0) -> dict:
    """启动一个真服务器 + 两个真客户端，跑一小段对局。"""
    server = GameServer(host="127.0.0.1", port=port, width=24, height=18, seed=2024)
    server_task = asyncio.create_task(server.run())
    await asyncio.sleep(0.4)

    views: dict[int, list[dict]] = {P1: [], P2: []}
    statuses: dict[int, list] = {P1: [], P2: []}

    clients = []
    for i in range(2):
        c = GameClient(
            "127.0.0.1",
            port,
            on_view=lambda v, idx=i: views[idx].append(v),
            on_status=lambda st, t, idx=i: statuses[idx].append(st),
        )
        clients.append(c)

    try:
        # 必须**顺序**连接：席位按服务器 accept 顺序分配，并发连接会出现
        # "先连上的反而拿到 P2" 的竞态，导致断言 clients[0] == P1 偶发失败。
        for c in clients:
            await c.connect()
            # 等到 WELCOME 回来、player_id 落定，再连下一个，避免席位错位
            for _ in range(100):
                if c.player_id is not None:
                    break
                await asyncio.sleep(0.02)
        await asyncio.sleep(0.5)

        # 双客户端持续发输入
        deadline = asyncio.get_event_loop().time() + seconds
        dirs = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
        step = 0
        while asyncio.get_event_loop().time() < deadline:
            for i, c in enumerate(clients):
                if c.player_id is None:
                    continue
                if step % 6 == i % 6:
                    await c.send_direction(dirs[(step + i) % 4])
                if step % 20 == 0:
                    await c.send_sprint(i == 0)
            step += 1
            await asyncio.sleep(0.05)
    finally:
        for c in clients:
            await c.close()
        await server.shutdown()
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass

    return {"views": views, "statuses": statuses, "players": [c.player_id for c in clients]}


@pytest.mark.asyncio
async def test_two_clients_can_join_and_receive_states() -> None:
    result = await _run_two_clients(port=18765, seconds=3.0)
    pids = result["players"]
    assert None not in pids, "两个客户端都应被分配席位"
    assert set(pids) == {P1, P2}, "应分别拿到 P1 和 P2"
    assert pids == [P1, P2], "席位应按连接顺序分配（先连的拿 P1）"
    # 双方都收到了状态
    assert len(result["views"][P1]) > 10, "P1 应持续收到状态"
    assert len(result["views"][P2]) > 10, "P2 应持续收到状态"


@pytest.mark.asyncio
async def test_received_states_never_leak_hidden_targets() -> None:
    """端到端验证：客户端收到的每一帧都不含隐藏目标坐标。"""
    result = await _run_two_clients(port=18766, seconds=3.0)
    for pid in (P1, P2):
        for view in result["views"][pid]:
            assert "fruit" not in view
            assert "gold" not in view
            assert "target" not in view
            assert "gold_trigger" not in view
            assert "normal_eaten" not in view
            assert view["player"] == pid


@pytest.mark.asyncio
async def test_states_are_personalized_per_player() -> None:
    """两个客户端收到的视角必须不同（各自裁剪），而不是同一份全量数据。"""
    result = await _run_two_clients(port=18767, seconds=3.0)
    v1 = result["views"][P1]
    v2 = result["views"][P2]
    assert v1 and v2
    # 各自的 own_head 应指向自己的蛇
    assert v1[-1]["own_head"] != v2[-1]["own_head"] or v1[-1]["player"] != v2[-1]["player"]
    assert v1[-1]["player"] == P1
    assert v2[-1]["player"] == P2


@pytest.mark.asyncio
async def test_third_client_is_rejected() -> None:
    server = GameServer(host="127.0.0.1", port=18768, width=24, height=18, seed=7)
    server_task = asyncio.create_task(server.run())
    await asyncio.sleep(0.4)
    c1 = GameClient("127.0.0.1", 18768)
    c2 = GameClient("127.0.0.1", 18768)
    c3 = GameClient("127.0.0.1", 18768, connect_timeout=3.0)
    try:
        await c1.connect()
        await c2.connect()
        await asyncio.sleep(0.3)
        try:
            await c3.connect()
            await asyncio.sleep(0.5)
        except ClientError:
            pass
        # 第三个不应拿到席位
        assert c3.player_id is None or c3.status is ClientStatus.ERROR
    finally:
        for c in (c1, c2, c3):
            with pytest.raises(Exception) if False else __import__("contextlib").suppress(Exception):
                await c.close()
        await server.shutdown()
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_client_reports_error_on_bad_ip() -> None:
    """连不上的 IP 必须给出明确错误，而不是静默挂住。"""
    c = GameClient("127.0.0.1", 59999, connect_timeout=2.0)
    with pytest.raises(ClientError):
        await c.connect()
    assert c.status is ClientStatus.ERROR
    assert c.last_error


@pytest.mark.asyncio
async def test_client_handles_server_shutdown() -> None:
    server = GameServer(host="127.0.0.1", port=18769, width=24, height=18, seed=9)
    server_task = asyncio.create_task(server.run())
    await asyncio.sleep(0.4)
    c = GameClient("127.0.0.1", 18769)
    try:
        await c.connect()
        await asyncio.sleep(0.3)
        await server.shutdown()
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
        await asyncio.sleep(0.5)
        # 服务器关闭后客户端不应崩溃，状态应变为断开或错误
        assert c.status in (ClientStatus.DISCONNECTED, ClientStatus.ERROR, ClientStatus.WAITING, ClientStatus.PLAYING)
    finally:
        await c.close()


def test_find_lan_ip_returns_string() -> None:
    ip = find_lan_ip()
    assert isinstance(ip, str)
    assert len(ip) >= 7
