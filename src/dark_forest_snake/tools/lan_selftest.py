"""LAN 自测工具：在本机启动 1 个服务器 + 2 个客户端，验证整条链路。

用法：
    uv run python -m dark_forest_snake.tools.lan_selftest
    uv run python -m dark_forest_snake.tools.lan_selftest --seconds 8

它会（可选地）用两个 AI 通过真实 websocket 打一小局，并打印：
- 双方各自收到的视角帧数
- 是否泄漏隐藏目标坐标
- 最终比分 / 阶段

这是用来在没有第二台电脑时验证 LAN 模式的实用工具。
"""

from __future__ import annotations

import argparse
import asyncio
import random

from dark_forest_snake import config as C
from dark_forest_snake.ai.snake_ai import SnakeAI, perception_from_dict
from dark_forest_snake.core.geometry import Direction
from dark_forest_snake.network.client import ClientStatus, GameClient
from dark_forest_snake.network.server import GameServer, find_lan_ip

FORBIDDEN_KEYS = ("fruit", "gold", "target", "gold_trigger", "normal_eaten", "round_index")


async def main() -> None:
    ap = argparse.ArgumentParser(description="LAN 链路自测")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18899)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--with-ai", action="store_true", default=True, help="用 AI 驱动两个客户端")
    ap.add_argument("--width", type=int, default=C.MAP_WIDTH)
    ap.add_argument("--height", type=int, default=C.MAP_HEIGHT)
    args = ap.parse_args()

    print(f"本机局域网 IP（Host 应把这个告诉 Client）: {find_lan_ip()}")

    server = GameServer(
        host=args.host,
        port=args.port,
        width=args.width,
        height=args.height,
        seed=2024,
        on_log=lambda t: print(f"  [server] {t}"),
    )
    server_task = asyncio.create_task(server.run())
    await asyncio.sleep(0.5)

    frames: dict[int, int] = {}
    leaks: list[str] = []
    statuses: dict[int, ClientStatus] = {}

    def make_on_view(idx: int):
        def _on_view(view: dict) -> None:
            frames[idx] = frames.get(idx, 0) + 1
            for bad in FORBIDDEN_KEYS:
                if bad in view:
                    leaks.append(f"P{idx + 1} 收到禁止字段 {bad}")
            # 坐标 key 必须是 "x,y" 字符串，而不是交给画面遮挡
            for k in view.get("visible_brightness", {}):
                if not isinstance(k, str):
                    leaks.append(f"P{idx + 1} 亮度 key 类型错误 {type(k)}")
        return _on_view

    def make_on_status(idx: int):
        def _on_status(st: ClientStatus, text: str) -> None:
            statuses[idx] = st
            if st is ClientStatus.ERROR:
                print(f"  [client{idx + 1}] 错误: {text}")
        return _on_status

    clients = [
        GameClient(
            args.host,
            args.port,
            on_view=make_on_view(i),
            on_status=make_on_status(i),
        )
        for i in range(2)
    ]

    try:
        await asyncio.gather(*(c.connect() for c in clients))
        await asyncio.sleep(0.6)
        pids = [c.player_id for c in clients]
        print(f"已分配席位: {pids}  (map {args.width}x{args.height})")
        if None in pids:
            print("!! 有客户端没拿到席位，自测失败")
            return

        bots = {
            pid: SnakeAI(pid, random.Random(1000 + pid), aggression=0.6)
            for pid in pids
            if pid is not None
        }
        by_pid = {c.player_id: c for c in clients if c.player_id is not None}

        loop = asyncio.get_event_loop()
        deadline = loop.time() + args.seconds
        tick = 0
        while loop.time() < deadline:
            for pid, bot in bots.items():
                c = by_pid[pid]
                if c.latest_view is None:
                    continue
                perc = perception_from_dict(c.latest_view, (args.width, args.height))
                action = bot.decide(perc)
                if action.direction is not None:
                    await c.send_direction(action.direction)
                await c.send_sprint(action.sprint)
            tick += 1
            await asyncio.sleep(C.BASE_MOVE_INTERVAL)

        print(f"\n自测结果：")
        print(f"  驱动 tick 数: {tick}")
        for i, pid in enumerate(pids):
            print(f"  P{pid + 1}: 收到 {frames.get(i, 0)} 帧视角, 最终状态 {statuses.get(i, ClientStatus.IDLE).value}")
        g = server.room.game
        if g is not None:
            print(f"  服务器阶段: {g.state.phase.value}  金苹果: {g.gold_counts}  轮次: {g.round_index}")
            print(f"  蛇长: {[s.length for s in g.snakes.values()]}")
        if leaks:
            print(f"  !! 发现 {len(leaks)} 处信息泄漏: {leaks[:5]}")
        else:
            print("  信息隔离检查: 通过（未发现隐藏目标泄漏）")
    finally:
        for c in clients:
            try:
                await c.close()
            except Exception:
                pass
        await server.shutdown()
        server_task.cancel()
        try:
            await server_task
        except Exception:
            pass
        print("已关闭服务器与客户端")


if __name__ == "__main__":
    asyncio.run(main())
