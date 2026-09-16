"""主程序：菜单、单机对战 AI、局域网对战。

运行：
    uv run python -m dark_forest_snake
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time

import pygame

from dark_forest_snake import config as C
from dark_forest_snake.ai.snake_ai import (
    AIState,
    SnakeAI,
    perception_from_dict,
    perception_from_view,
)
from dark_forest_snake.core.fruit import FruitType
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.state import GamePhase
from dark_forest_snake.network.client import ClientError, ClientStatus, GameClient
from dark_forest_snake.network.server import GameServer, find_lan_ip
from dark_forest_snake.ui import theme as T
from dark_forest_snake.ui.hud import HUD
from dark_forest_snake.ui.input import read_input
from dark_forest_snake.ui.menu import (
    CountdownOverlay,
    GameOverScreen,
    Menu,
    TextInputScreen,
    TextScreen,
)
from dark_forest_snake.ui.renderer import Renderer
from dark_forest_snake.ui.sound import get_sounds

MIN_WINDOW_W = 1280
MIN_WINDOW_H = 820
CELL_SIZE = 28


class Screen(  # noqa: D101
    str
):
    pass


class App:
    """整个应用的顶层状态机。"""

    def __init__(self, *, start_mode: str | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("黑暗森林贪吃蛇  ·  Dark Forest Snake")

        self.width = max(MIN_WINDOW_W, C.MAP_WIDTH * CELL_SIZE + 320)
        self.height = max(MIN_WINDOW_H, C.MAP_HEIGHT * CELL_SIZE + 80)
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.sounds = get_sounds()

        self.mode = "menu"           # menu | solo | lan_host | lan_client | help
        self.debug = C.DEBUG

        self.game: Game | None = None
        self.ai: SnakeAI | None = None
        board_w = C.MAP_WIDTH * CELL_SIZE
        board_h = C.MAP_HEIGHT * CELL_SIZE
        self.renderer = Renderer(
            self.screen, C.MAP_WIDTH, C.MAP_HEIGHT, cell_size=CELL_SIZE, origin=(24, 40)
        )
        self.hud = HUD(self.screen, pygame.Rect(board_w + 30, 40, self.width - board_w - 54, board_h))
        self.overlay = CountdownOverlay(self.screen)
        self.gameover = GameOverScreen(self.screen)

        # LAN
        self.client: GameClient | None = None
        self.server: GameServer | None = None
        self.host_task: asyncio.Task | None = None
        self.lan_error = ""
        self.lan_status = ""
        self.lan_view: dict | None = None
        self.lan_player: int | None = None
        self.lan_phase: str = ""

        self._seen_events: set[str] = set()
        self._last_phase: str | None = None
        self._banner: tuple[str, float] | None = None
        # 顶部吃果横幅： (文字, 颜色, 过期时刻)
        self._eat_banner: tuple[str, tuple[int, int, int], float] | None = None
        self._banner_seen: set[str] = set()

        self._build_menus()
        if start_mode:
            self._enter_mode(start_mode)

    # ================================================================ 菜单
    def _build_menus(self) -> None:
        self.main_menu = Menu(
            self.screen,
            "黑暗森林贪吃蛇",
            ["单机对战 AI", "局域网双人", "玩法说明", "退出"],
            subtitle="你只能通过光的强弱，感觉出目标的方向",
            footer="↑↓ 选择    Enter 确认    F1 调试视图",
        )
        self.lan_menu = Menu(
            self.screen,
            "局域网双人",
            ["创建房间（我是 Host）", "加入房间（我是 Client）", "返回"],
            subtitle="两台电脑处于同一局域网即可对战",
        )
        self.help_screen = TextScreen(
            self.screen,
            "玩法说明",
            [
                "## 目标",
                "先获得 3 个金苹果，或让对方死亡。",
                "",
                "## 黑暗视野",
                "地图是黑的。你只能看到蛇头周围半径 5 格的微光区域。",
                "视野之外：看不见果子、看不见金苹果、看不见敌人。",
                "果子与金苹果进入你的可见范围时，会直接显形。",
                "",
                "## 亮度导航（核心）",
                "没有箭头，没有坐标，没有小地图。",
                "可见范围最外圈会有一个光点指向目标方向；",
                "光点颜色就是目标果子的颜色，越接近目标光点越亮。",
                "你只能读光。",
                "",
                "## 普通果子（场上同时只有 1 个）",
                "  青色 · 疾跑果   10 秒内按住 Shift 才能加速",
                "  紫色 · 护盾果   抵挡 1 次致死撞击",
                "  蓝色 · 灯笼果   视野半径 5 → 6",
                "吃掉任意果子：获得能力 + 长度 +1",
                "",
                "## 隐藏金苹果",
                "每轮开始时会随机一个 3~6 的隐藏阈值（不会告诉你）。",
                "全场累计吃掉的普通果子达到阈值，金苹果出现。",
                "普通果子消失，地图上只剩那个同样看不见的金苹果。",
                "",
                "## 3 秒全图",
                "吃到金苹果的人独享 3 秒全图照亮，能看到对手。",
                "另一方只会收到“对方获得了金苹果”。",
                "",
                "## 操作",
                "W A S D / ↑ ↓ ← →   移动（不能 180° 掉头）",
                "Shift               疾跑（需先吃到疾跑果）",
                "F1                  调试视图（默认关闭）",
                "ESC                 返回        R  重开",
            ],
        )
        self.lan_client_input = TextInputScreen(
            self.screen,
            "加入房间",
            "输入 Host 的局域网 IP",
            initial="127.0.0.1",
            hint="例如 192.168.1.10（可在 Host 的“创建房间”界面看到）",
        )

    # ================================================================ 主循环
    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            events = pygame.event.get()
            inp = read_input(events)

            if inp.quit:
                running = False
                break
            if inp.debug_toggle:
                self.debug = not self.debug

            if self.mode == "menu":
                running = self._update_menu(events, inp)
            elif self.mode == "lan_input":
                self._update_lan_input(events, dt)
            elif self.mode == "help":
                if inp.back or inp.confirm:
                    self.mode = "menu"
                self.help_screen.draw()
            elif self.mode == "solo":
                self._update_solo(dt, inp)
            elif self.mode in ("lan_host", "lan_client"):
                self._update_lan(dt, inp)
            else:
                self.mode = "menu"

            pygame.display.flip()

        self._shutdown()
        pygame.quit()

    # ================================================================ 菜单
    def _update_menu(self, events, inp) -> bool:
        if self.mode == "menu" and getattr(self, "_menu_page", "main") == "lan":
            self.lan_menu.draw()
            if inp.back:
                self._menu_page = "main"
            else:
                self._menu_nav(events, self.lan_menu)
                if inp.confirm:
                    choice = self.lan_menu.selected()
                    self.sounds.play("menu")
                    if choice.startswith("创建"):
                        self._enter_mode("lan_host")
                    elif choice.startswith("加入"):
                        self.mode = "lan_input"
                    else:
                        self._menu_page = "main"
            return True

        self.main_menu.draw()
        self._menu_nav(events, self.main_menu)
        if inp.confirm:
            choice = self.main_menu.selected()
            self.sounds.play("menu")
            if choice == "单机对战 AI":
                self._enter_mode("solo")
            elif choice == "局域网双人":
                self._menu_page = "lan"
            elif choice == "玩法说明":
                self.mode = "help"
            else:
                return False
        return True

    def _menu_nav(self, events, menu: Menu) -> None:
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_UP, pygame.K_w):
                    menu.move(-1)
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    menu.move(1)

    # ================================================================ 模式进入
    def _enter_mode(self, mode: str) -> None:
        self._menu_page = "main"
        if mode == "solo":
            self.mode = "solo"
            seed = random.randrange(1 << 30)
            self.game = Game(seed=seed, debug=self.debug)
            self.game.start_match(countdown=C.COUNTDOWN_DURATION)
            self.ai = SnakeAI(P2, random.Random(seed + 999), aggression=0.55)
            self._seen_events.clear()
            self._banner_seen.clear()
            self._eat_banner = None
            self._last_phase = None
            self.lan_view = None
            self.lan_player = None
        elif mode == "lan_host":
            self.mode = "lan_host"
            self.lan_view = None
            self.lan_player = None
            self.lan_error = ""
            self.lan_status = f"正在启动服务器… 局域网 IP: {find_lan_ip()}"
            self._start_host()
        elif mode == "lan_client":
            self.mode = "lan_client"
            self.lan_view = None
            self.lan_player = None
            self._seen_events.clear()

    # ================================================================ 单机
    def _update_solo(self, dt: float, inp) -> None:
        assert self.game is not None
        g = self.game

        if inp.restart and g.is_over():
            seed = random.randrange(1 << 30)
            self.game = Game(seed=seed, debug=self.debug)
            self.game.start_match(countdown=C.COUNTDOWN_DURATION)
            self.ai = SnakeAI(P2, random.Random(seed + 999), aggression=0.55)
            self._seen_events.clear()
            self._banner_seen.clear()
            self._eat_banner = None
            g = self.game
        elif inp.back:
            self.mode = "menu"
            self.game = None
            return

        # 玩家输入 → 只登记意图
        if g.state.phase.is_playing:
            for d in inp.directions:
                g.input_direction(P1, d)
            g.input_sprint(P1, inp.sprint)

        # AI 输入：完全基于受限视野
        if self.ai is not None and g.state.phase.is_playing:
            view = g.view_for(P2)
            perc = perception_from_view(view, (g.width, g.height))
            action = self.ai.decide(perc)
            if action.direction is not None:
                g.input_direction(P2, action.direction)
            g.input_sprint(P2, action.sprint)

        g.update(dt)
        self._play_new_events(g.event_log)

        view = g.view_for(P1).to_dict()
        self._draw_board(view, g, local_player=P1)

    # ================================================================ LAN
    def _start_host(self) -> None:
        ip = find_lan_ip()
        self.server = GameServer(
            host="0.0.0.0",
            port=PORT,
            width=C.MAP_WIDTH,
            height=C.MAP_HEIGHT,
            seed=None,
        )
        self.lan_status = f"房间已创建 · 局域网 IP: {ip} · 端口 {PORT}　等待对手加入…"
        loop = asyncio.new_event_loop()

        async def _serve() -> None:
            assert self.server is not None
            await self.server.run()

        # 服务器跑在后台线程的独立事件循环里（避免阻塞 pygame 主循环）
        import threading

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_serve())
            except Exception:
                pass

        self._host_thread = threading.Thread(target=_runner, daemon=True)
        self._host_thread.start()

        # Host 自己也是一个客户端（本地直连）
        self._connect_client("127.0.0.1")

    def _connect_client(self, host_ip: str) -> None:
        loop = asyncio.new_event_loop()
        self._client_loop = loop
        client = GameClient(
            host_ip,
            PORT,
            on_view=self._on_lan_view,
            on_status=self._on_lan_status,
            on_event=self._on_lan_event,
        )
        self.client = client

        import threading

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(client.connect())
            except ClientError as exc:
                self.lan_error = str(exc)
                return
            except Exception as exc:
                self.lan_error = f"连接失败: {exc}"
                return
            loop.run_until_complete(self._client_forever())

        self._client_thread = threading.Thread(target=_runner, daemon=True)
        self._client_thread.start()

    async def _client_forever(self) -> None:
        try:
            while self.client is not None and self.client.status not in (
                ClientStatus.ERROR,
                ClientStatus.DISCONNECTED,
            ):
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            return

    def _on_lan_view(self, view: dict) -> None:
        self.lan_view = view

    def _on_lan_status(self, status: ClientStatus, text: str) -> None:
        if status is ClientStatus.ERROR:
            self.lan_error = text
        elif status is ClientStatus.WAITING:
            self.lan_status = text + "　等待对手加入…"
        elif status is ClientStatus.PLAYING:
            self.lan_status = "对局进行中"
        elif status is ClientStatus.CONNECTED:
            self.lan_status = "已连接 Host"

    def _on_lan_event(self, text: str, player) -> None:
        if text not in self._seen_events:
            self._seen_events.add(text)
            mine = self.client is not None and player == self.client.player_id
            self.sounds.play_for_event(text, mine=mine)

    def _update_lan(self, dt: float, inp) -> None:
        if inp.back:
            self._close_lan()
            self.mode = "menu"
            return

        if self.lan_error:
            self._draw_lan_error()
            return

        view = self.lan_view
        if view is None or self.client is None or self.client.player_id is None:
            self._draw_lan_waiting()
            return

        self.lan_player = self.client.player_id
        phase = str(view.get("phase", ""))

        if phase in ("playing_normal", "playing_golden", "countdown"):
            for d in inp.directions:
                self._post(self.client.send_direction(d))
            self._post(self.client.send_sprint(inp.sprint))
        if inp.restart and phase in ("game_over", "draw_restart"):
            self._post(self.client.request_restart())

        # LAN 模式下客户端不做本地模拟：画面完全来自服务器的权威视角
        fake_game = _ViewBackedGame(view, self.client.map_width, self.client.map_height)
        self._draw_board(view, fake_game, local_player=self.client.player_id, lan=True)

    def _post(self, coro) -> None:
        loop = getattr(self, "_client_loop", None)
        if loop is None or loop.is_closed():
            coro.close()
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            coro.close()

    def _close_lan(self) -> None:
        if self.client is not None:
            try:
                asyncio.run_coroutine_threadsafe(self.client.close(), self._client_loop)
            except Exception:
                pass
            self.client = None
        if self.server is not None:
            try:
                asyncio.run_coroutine_threadsafe(self.server.shutdown(), self._host_loop())
            except Exception:
                pass
            self.server = None
        self.lan_view = None
        self.lan_player = None
        self.lan_error = ""
        self.lan_status = ""

    def _host_loop(self):
        return getattr(self, "_client_loop", None)

    # ================================================================ 绘制
    def _draw_board(self, view: dict, game, *, local_player: int | None, lan: bool = False) -> None:
        self.screen.fill(T.BG_DARK)
        self.renderer.draw(view, debug=self.debug)
        enemy_label = "对手"
        self.hud.draw(view, enemy_label=enemy_label)

        self._update_eat_banner(view, local_player)
        self._draw_eat_banner()

        if self.debug:
            self._draw_debug(view, game)

        phase = str(view.get("phase", ""))
        if phase == "countdown":
            self.overlay.draw_countdown(view.get("countdown_remaining", 0.0))
        if phase == "playing_golden" and view.get("reveal_active"):
            self.overlay.draw_banner("金苹果 · 全图照亮", color=T.TEXT_GOLD, y_ratio=0.10, size=28)

        if lan:
            self._draw_lan_footer(view)

        if phase in ("game_over", "draw_restart"):
            self.gameover.draw(
                winner=view.get("winner"),
                draw=bool(view.get("draw")),
                local_player=local_player,
                view=view,
            )

    # ================================================================ 吃果横幅
    def _update_eat_banner(self, view: dict, local_player: int | None) -> None:
        """监视事件流：谁吃到果子 / 金苹果，就在窗口顶部弹一条彩色横幅。"""
        for ev in view.get("events", []) or []:
            text = str(ev.get("text", ""))
            key = f"{ev.get('at')}:{text}"
            if key in self._banner_seen:
                continue
            self._banner_seen.add(key)
            if "吃到了" not in text and "获得了金苹果" not in text:
                continue
            who = "你" if ev.get("player") == local_player else "对手"
            if "吃到了" in text:
                msg = f"{who}吃到了{text.split('吃到了', 1)[1]}！"
            else:
                msg = f"{who}获得了金苹果！"
            color = T.TEXT_PRIMARY
            for k, c in (
                ("疾跑", T.FRUIT_COLORS["sprint"]),
                ("护盾", T.FRUIT_COLORS["shield"]),
                ("灯笼", T.FRUIT_COLORS["lantern"]),
                ("金苹果", T.TEXT_GOLD),
            ):
                if k in text:
                    color = c
                    break
            self._eat_banner = (msg, color, time.time() + 2.6)
        if len(self._banner_seen) > 400:
            self._banner_seen = set(list(self._banner_seen)[-200:])

    def _draw_eat_banner(self) -> None:
        """棋盘上方居中的药丸式横幅，最后 0.6 秒渐隐。"""
        if not self._eat_banner:
            return
        msg, color, expire = self._eat_banner
        remain = expire - time.time()
        if remain <= 0:
            self._eat_banner = None
            return
        alpha = 255 if remain > 0.6 else max(0, int(255 * remain / 0.6))

        font = T.get_font(24, bold=True)
        w, h = font.size(msg)
        pad_x, pad_y = 28, 11
        bw, bh = w + pad_x * 2, h + pad_y * 2
        surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(surf, (10, 13, 17, int(alpha * 0.85)), surf.get_rect(), border_radius=bh // 2)
        pygame.draw.rect(surf, (*color, alpha), surf.get_rect(), width=1, border_radius=bh // 2)
        img = font.render(msg, True, color)
        img.set_alpha(alpha)
        surf.blit(img, (pad_x, pad_y))

        board_cx = self.renderer.ox + self.renderer.width * self.renderer.cell // 2
        self.screen.blit(surf, (board_cx - bw // 2, 8))

    def _draw_lan_footer(self, view: dict) -> None:
        rect = self.screen.get_rect()
        text = f"LAN · P{(self.lan_player or 0) + 1} · {self.lan_status or view.get('phase', '')}"
        T.render_text(self.screen, text, (rect.left + 24, rect.bottom - 30), size=16, color=T.TEXT_DIM)

    def _draw_lan_waiting(self) -> None:
        self.screen.fill(T.BG_DARK)
        rect = self.screen.get_rect()
        title = "等待对手加入…" if self.mode == "lan_host" else "正在连接 Host…"
        T.render_text(self.screen, title, (rect.centerx, rect.centery - 90), size=40, color=T.TEXT_ACCENT, center=True, bold=True)
        T.render_text(self.screen, self.lan_status or "", (rect.centerx, rect.centery - 20), size=20, color=T.TEXT_PRIMARY, center=True)
        if self.mode == "lan_host":
            T.render_text(
                self.screen,
                f"局域网 IP: {find_lan_ip()}    端口: {PORT}",
                (rect.centerx, rect.centery + 30),
                size=22,
                color=T.TEXT_GOLD,
                center=True,
            )
            T.render_text(
                self.screen,
                "在另一台电脑上选择「局域网双人 → 加入房间」并输入上面的 IP",
                (rect.centerx, rect.centery + 70),
                size=18,
                color=T.TEXT_DIM,
                center=True,
            )
            T.render_text(
                self.screen,
                "若对方连不上，请允许 Windows 防火墙的 Python 入站连接（或放行端口 " + str(PORT) + "）",
                (rect.centerx, rect.centery + 104),
                size=16,
                color=T.TEXT_WARN,
                center=True,
            )
        T.render_text(self.screen, "ESC 返回主菜单", (rect.centerx, rect.bottom - 50), size=18, color=T.TEXT_DIM, center=True)

    def _draw_lan_error(self) -> None:
        self.screen.fill(T.BG_DARK)
        rect = self.screen.get_rect()
        T.render_text(self.screen, "连接出现问题", (rect.centerx, rect.centery - 80), size=42, color=T.TEXT_WARN, center=True, bold=True)
        _wrap(self.screen, self.lan_error, (rect.centerx, rect.centery - 10), 760, size=20, color=T.TEXT_PRIMARY)
        T.render_text(
            self.screen,
            "排查建议：确认 Host 已启动「创建房间」、IP 输入正确、两台电脑在同一局域网、防火墙已放行",
            (rect.centerx, rect.centery + 90),
            size=17,
            color=T.TEXT_DIM,
            center=True,
        )
        T.render_text(self.screen, "ESC 返回主菜单", (rect.centerx, rect.bottom - 50), size=18, color=T.TEXT_DIM, center=True)

    def _draw_debug(self, view: dict, game) -> None:
        """DEBUG 视图：显示全地图与隐藏信息。默认关闭。"""
        if isinstance(game, _ViewBackedGame):
            return
        snap = game.debug_snapshot()
        lines = [
            f"DEBUG  phase={snap['phase']}",
            f"clock={snap['clock']:.2f} ticks={snap['tick_count']}",
            f"gold_trigger={snap['gold_trigger']} eaten={snap['normal_eaten']} round={snap['round_index']}",
            f"fruit={snap['fruit']}",
            f"gold={snap['gold']}",
            f"gold_counts={snap['gold_counts']}",
            f"ai_state={self.ai.state.value if self.ai else '-'}",
        ]
        y = 40
        for line in lines:
            T.render_text(self.screen, line, (24, y), size=15, color=(230, 180, 120))
            y += 18

        # 把隐藏目标用极小标记画出来（仅调试）
        if snap["fruit"]:
            self._debug_mark(snap["fruit"]["cell"], (0, 200, 255))
        if snap["gold"]:
            self._debug_mark(snap["gold"], (255, 200, 0))

    def _debug_mark(self, cell, color) -> None:
        r = self.renderer.cell_rect(cell[0], cell[1])
        pygame.draw.rect(self.screen, color, r, width=1)

    # ================================================================ 事件音效
    def _play_new_events(self, events) -> None:
        for ev in events:
            key = f"{ev.at:.2f}:{ev.text}"
            if key not in self._seen_events:
                self._seen_events.add(key)
                self.sounds.play_for_event(ev.text, mine=(ev.player == P1))
        if len(self._seen_events) > 400:
            self._seen_events = set(list(self._seen_events)[-200:])

    # ================================================================ LAN 输入页
    def _update_lan_input(self, events, dt: float) -> None:
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                res = self.lan_client_input.handle_event(ev)
                if res == "ok":
                    ip = self.lan_client_input.value.strip()
                    if not ip:
                        return
                    self._enter_mode("lan_client")
                    self.lan_status = f"正在连接 {ip}:{PORT} …"
                    self._connect_client(ip)
                    return
                if res == "cancel":
                    self.mode = "menu"
                    return
        self.lan_client_input.update(dt)
        self.lan_client_input.draw(error="", status="")

    # ================================================================ 收尾
    def _shutdown(self) -> None:
        self._close_lan()


class _ViewBackedGame:
    """给渲染层用的最小替身：LAN 客户端不需要本地 Game Engine。

    它只保存地图尺寸，供 HUD / debug 读取，**不持有任何游戏真值**。
    """

    def __init__(self, view: dict, width: int, height: int) -> None:
        self.width = width or C.MAP_WIDTH
        self.height = height or C.MAP_HEIGHT
        self._view = view

    def debug_snapshot(self) -> dict:
        return {"phase": self._view.get("phase", ""), "fruit": None, "gold": None}


def _wrap(
    surface: pygame.Surface,
    text: str,
    center: tuple[int, int],
    max_width: int,
    *,
    size: int = 20,
    color=None,
) -> None:
    """简单的中文换行绘制。"""
    from dark_forest_snake.ui.theme import render_text, text_width

    font_w = None
    words: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if text_width(trial, size) > max_width and cur:
            words.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        words.append(cur)
    y = center[1]
    for line in words:
        render_text(surface, line, (center[0], y), size=size, color=color or T.TEXT_PRIMARY, center=True)
        y += size + 6


PORT = 8765


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="黑暗森林贪吃蛇")
    ap.add_argument("--mode", choices=["solo", "lan_host", "lan_client"], default=None, help="跳过菜单直接进入某模式")
    ap.add_argument("--debug", action="store_true", help="开启调试视图（显示隐藏信息）")
    ap.add_argument("--port", type=int, default=8765, help="LAN 服务器端口")
    ap.add_argument("--headless-check", action="store_true", help="只做启动自检然后退出")
    args = ap.parse_args(argv)

    global PORT
    PORT = args.port

    if args.headless_check:
        return _headless_check()

    C.DEBUG = args.debug
    app = App(start_mode=args.mode)
    app.debug = args.debug
    app.run()
    return 0


def _headless_check() -> int:
    """无窗口自检：验证 pygame、字体、核心引擎、音效都能初始化。"""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    try:
        pygame.display.set_mode((640, 480))
    except Exception:
        pass

    problems: list[str] = []
    if not T.font_ok():
        problems.append("中文字体渲染异常（会显示为方框）")

    g = Game(width=20, height=16, seed=1)
    g.start_match(countdown=0.0)
    for _ in range(30):
        g.update(C.BASE_MOVE_INTERVAL)
    if g.tick_count == 0:
        problems.append("游戏引擎没有推进 Tick")

    from dark_forest_snake.ui.sound import get_sounds

    sb = get_sounds()
    if not sb.enabled:
        problems.append("音效不可用（不影响玩法）")

    print("启动自检结果：")
    print(f"  pygame: {pygame.version.ver}")
    print(f"  中文字体: {'OK' if T.font_ok() else '异常'}")
    print(f"  游戏引擎 Tick: {g.tick_count}")
    print(f"  音效: {'可用' if sb.enabled else '不可用'}")
    if problems:
        for p in problems:
            print(f"  ! {p}")
        return 1
    print("  全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
