"""渲染层：黑暗、微光、vignette、glow。

视觉方向：深黑背景 / 极弱网格 / radial lighting / 轻微 glow。
亮度差异要"可读但不明显"。

渲染层只读取「视角状态」——它拿不到目标坐标，因此不可能画出箭头或高亮目标。
"""

from __future__ import annotations

import math

import pygame

from dark_forest_snake import config as C
from dark_forest_snake.ui.theme import (
    AMBIENT_FAR,
    AMBIENT_NEAR,
    BG_DARK,
    BOARD_EDGE,
    GRID_COLOR,
    GRID_DARK,
    INDICATOR_COLOR_NORMAL,
    INDICATOR_GOLD_BONUS,
    INDICATOR_MAX_ALPHA,
    INDICATOR_MIN_ALPHA,
    OWN_BODY,
    OWN_BODY_DIM,
    OWN_HEAD,
    OWN_HEAD_GLOW,
    ENEMY_BODY,
    ENEMY_EDGE,
    ENEMY_GLOW,
    ENEMY_HEAD,
    GOLD_COLOR,
    FRUIT_COLORS,
    TEXT_PRIMARY,
    TEXT_DIM,
    VIGNETTE,
    WALL_CORE,
    WALL_GLOW,
)


class Renderer:
    """负责地图、蛇、光照、vignette 的绘制。"""

    def __init__(
        self,
        screen: pygame.Surface,
        width: int,
        height: int,
        *,
        cell_size: int = 24,
        origin: tuple[int, int] = (0, 0),
    ) -> None:
        self.screen = screen
        self.width = width
        self.height = height
        self.cell = cell_size
        self.ox, self.oy = origin

        self.board = pygame.Surface((width * cell_size, height * cell_size))
        self._vignette_cache: pygame.Surface | None = None
        self._dark = pygame.Surface(self.board.get_size(), pygame.SRCALPHA)

    # ================================================================ 坐标
    def to_px(self, x: int, y: int) -> tuple[int, int]:
        return self.ox + x * self.cell, self.oy + y * self.cell

    def cell_rect(self, x: int, y: int) -> pygame.Rect:
        px, py = self.to_px(x, y)
        return pygame.Rect(px, py, self.cell, self.cell)

    # ================================================================ 主绘制
    def draw(self, view: dict, *, debug: bool = False, hover_cells: dict | None = None) -> None:
        """按视角状态绘制一帧。

        view 就是 PlayerViewState.to_dict() 的结果 —— 不含任何隐藏目标坐标。
        """
        self.board.fill(BG_DARK)
        self._draw_grid()

        brightness: dict[str, float] = view.get("visible_brightness", {}) or {}
        reveal = bool(view.get("reveal_active"))

        self._draw_brightness(brightness, reveal)
        self._draw_walls()
        self._draw_board_edge()

        # 视野边缘光点：指向目标的那一点发目标颜色的光
        if not reveal:
            self._draw_edge_beacon(view)

        # 视野内的果子 / 金苹果（进入可见范围才出现）
        self._draw_fruits(view)

        # 自己的蛇：完整但暗淡的轮廓（降低随机自撞）
        own_body = [tuple(c) for c in view.get("own_body", [])]
        enemy_cells = [tuple(c) for c in view.get("visible_enemy_cells", [])]

        self._draw_snake_body(own_body, ENEMY_BODY if False else OWN_BODY_DIM)
        self._draw_enemy(enemy_cells)
        self._draw_own_head(view)
        self._draw_ability_fx(view, own_body)

        # 黑暗遮罩：把可见区域外的部分压黑
        if not reveal:
            self._apply_darkness(brightness, own_body)

        self._apply_vignette()

        ox, oy = self.ox, self.oy
        self.screen.blit(self.board, (ox, oy))

    # ================================================================ 网格
    def _draw_grid(self) -> None:
        c = self.cell
        w = self.board.get_width()
        h = self.board.get_height()
        for x in range(self.width + 1):
            color = GRID_COLOR if x % 4 == 0 else GRID_DARK
            pygame.draw.line(self.board, color, (x * c, 0), (x * c, h))
        for y in range(self.height + 1):
            color = GRID_COLOR if y % 4 == 0 else GRID_DARK
            pygame.draw.line(self.board, color, (0, y * c), (w, y * c))

    # ================================================================ 亮度
    def _draw_brightness(self, brightness: dict[str, float], reveal: bool) -> None:
        """把可见格铺成柔和的灰→暖黄渐变底色：蛇头最亮最暖，越靠外越暗越灰。"""
        if not brightness:
            return
        lo, hi = C.MIN_BRIGHTNESS, C.MAX_BRIGHTNESS
        for key, value in brightness.items():
            x, y = _parse(key)
            t = (value - lo) / (hi - lo) if hi > lo else 0.0
            t = max(0.0, min(1.0, t))
            alpha = int(14 + 52 * t)
            if reveal:
                alpha = int(alpha * 1.5)
            if alpha <= 0:
                continue
            color = _lerp_color(AMBIENT_FAR, AMBIENT_NEAR, t)
            rect = self.cell_rect(x, y)
            rect.move_ip(-self.ox, -self.oy)
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((*color, alpha))
            self.board.blit(overlay, rect.topleft)

    def _apply_darkness(self, brightness: dict[str, float], own_body: list) -> None:
        """视野之外全黑。

        做法：整体覆盖一层黑幕，再挖出可见格的柔和孔洞。
        """
        self._dark.fill((0, 0, 0, 255))
        for key in brightness:
            x, y = _parse(key)
            rect = self.cell_rect(x, y)
            rect.move_ip(-self.ox, -self.oy)
            # 用渐变孔洞做软边
            hole = pygame.Surface((rect.w + 12, rect.h + 12), pygame.SRCALPHA)
            for i in range(6, 0, -1):
                a = int(255 * (1 - i / 6.0))
                pygame.draw.rect(
                    hole,
                    (0, 0, 0, a),
                    pygame.Rect(6 - i, 6 - i, rect.w + i * 2, rect.h + i * 2),
                    border_radius=3,
                )
            pygame.draw.rect(
                hole, (0, 0, 0, 0), pygame.Rect(6, 6, rect.w, rect.h), border_radius=2
            )
            self._dark.blit(hole, (rect.x - 6, rect.y - 6), special_flags=pygame.BLEND_RGBA_MIN)
        self.board.blit(self._dark, (0, 0))

    def _apply_vignette(self) -> None:
        if self._vignette_cache is None:
            self._vignette_cache = _build_vignette(self.board.get_size())
        self._board_blend()

    def _board_blend(self) -> None:
        if self._vignette_cache is not None:
            self.board.blit(self._vignette_cache, (0, 0))

    # ================================================================ 墙体
    def _draw_walls(self) -> None:
        c = self.cell
        w = self.board.get_width()
        h = self.board.get_height()
        for x in range(self.width):
            self._wall_rect(pygame.Rect(x * c, 0, c, c))
            self._wall_rect(pygame.Rect(x * c, h - c, c, c))
        for y in range(self.height):
            self._wall_rect(pygame.Rect(0, y * c, c, c))
            self._wall_rect(pygame.Rect(w - c, y * c, c, c))

    def _wall_rect(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.board, WALL_GLOW, rect)
        pygame.draw.rect(self.board, WALL_CORE, rect.inflate(-6, -6))

    def _draw_board_edge(self) -> None:
        """可玩区域内沿的亮色描边：撞墙前最醒目的一道提醒。"""
        c = self.cell
        rect = pygame.Rect(c, c, (self.width - 2) * c, (self.height - 2) * c)
        pygame.draw.rect(self.board, BOARD_EDGE, rect, width=2, border_radius=2)

    # ================================================================ 蛇
    def _draw_snake_body(self, body: list, color) -> None:
        for i, (x, y) in enumerate(body):
            if i == 0:
                continue
            rect = self.cell_rect(x, y).inflate(-4, -4)
            rect.move_ip(-self.ox, -self.oy)
            shade = _dim(color, 0.55 + 0.45 * (1 - i / max(1, len(body))))
            pygame.draw.rect(self.board, shade, rect, border_radius=6)
            # 细描边：让身体一格一格更分明
            pygame.draw.rect(self.board, _dim(color, 0.32), rect, width=1, border_radius=6)

    def _draw_enemy(self, cells: list) -> None:
        """对手的蛇：猩红本体 + 红色光晕 + 亮描边，黑暗里一眼可辨。"""
        for (x, y) in cells:
            rect = self.cell_rect(x, y).inflate(-4, -4)
            rect.move_ip(-self.ox, -self.oy)
            # 红色光晕（加法混合）
            glow_r = int(self.cell * 0.52)
            size = glow_r * 2 + 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            center = (size // 2, size // 2)
            for rr in range(glow_r, 0, -1):
                t = rr / glow_r
                a = int(75 * (1 - t) ** 1.5)
                if a > 0:
                    pygame.draw.circle(surf, (*_glow_rgb(ENEMY_GLOW, a), 255), center, rr)
            self.board.blit(
                surf,
                (rect.centerx - center[0], rect.centery - center[1]),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
            pygame.draw.rect(self.board, ENEMY_BODY, rect, border_radius=6)
            pygame.draw.rect(self.board, ENEMY_EDGE, rect, width=1, border_radius=6)

    def _draw_own_head(self, view: dict) -> None:
        head = view.get("own_head")
        if not head:
            return
        x, y = head
        # 蛇头柔光（加法混合）
        glow_r = int(self.cell * 0.55)
        size = glow_r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        for rr in range(glow_r, 0, -1):
            t = rr / glow_r
            a = int(48 * (1 - t) ** 1.6)
            if a > 0:
                pygame.draw.circle(surf, (*_glow_rgb(OWN_HEAD_GLOW, a), 255), center, rr)
        rect = self.cell_rect(x, y)
        rect.move_ip(-self.ox, -self.oy)
        self.board.blit(
            surf,
            (rect.centerx - center[0], rect.centery - center[1]),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
        rect = rect.inflate(-2, -2)
        pygame.draw.rect(self.board, OWN_HEAD, rect, border_radius=7)
        pygame.draw.rect(self.board, _dim(OWN_HEAD, 0.55), rect, width=1, border_radius=7)
        # 蛇头朝向的小亮斑（帮助玩家确认自己的朝向）
        d = view.get("own_direction", [1, 0])
        cx, cy = rect.centerx, rect.centery
        off = self.cell * 0.26
        pygame.draw.circle(
            self.board,
            (255, 255, 255),
            (int(cx + d[0] * off), int(cy + d[1] * off)),
            max(2, self.cell // 9),
        )

    # ================================================================ 能力特效
    def _draw_ability_fx(self, view: dict, own_body: list) -> None:
        """吃到果子后蛇身的持续特效（能力有效期内）：

        - 疾跑果：青色流光沿蛇身向后流动
        - 护盾果：紫色光环包裹全身，随时间脉动
        - 灯笼果：蛇头周围一团温暖的黄光，轻轻呼吸
        金苹果会同时给三种能力，因此三种特效会同时出现。
        """
        ab = view.get("abilities", {}) or {}
        sprint = float(ab.get("sprint", 0.0) or 0.0)
        shield = float(ab.get("shield", 0.0) or 0.0)
        lantern = float(ab.get("lantern", 0.0) or 0.0)
        if not own_body or (sprint <= 0 and shield <= 0 and lantern <= 0):
            return

        now = pygame.time.get_ticks() / 1000.0
        cells = [self.cell_rect(x, y) for (x, y) in own_body]
        for r in cells:
            r.move_ip(-self.ox, -self.oy)

        if lantern > 0:
            self._fx_lantern(cells[0], now)
        if shield > 0:
            self._fx_shield(cells, now)
        if sprint > 0:
            self._fx_sprint(cells, view, now)

    def _fx_lantern(self, head_rect: pygame.Rect, now: float) -> None:
        """灯笼：蛇头周围一团温暖的黄光，缓慢呼吸。

        只用少数几个同心圆叠加，避免逐像素堆环把中心洗成实心圆盘。
        """
        radius = int(self.cell * 1.8)
        pulse = 0.85 + 0.15 * math.sin(now * 2.4)
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for ratio, a in ((1.0, 5), (0.72, 7), (0.45, 9)):
            pygame.draw.circle(
                surf,
                (*_glow_rgb((255, 214, 130), a * pulse), 255),
                (radius, radius),
                int(radius * ratio),
            )
        self.board.blit(
            surf,
            (head_rect.centerx - radius, head_rect.centery - radius),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

    def _fx_shield(self, cells: list[pygame.Rect], now: float) -> None:
        """护盾：全身紫色光环，随时间脉动明暗。"""
        pulse = 0.5 + 0.5 * math.sin(now * 4.0)
        a = int(50 + 80 * pulse)
        color = FRUIT_COLORS["shield"]
        for r in cells:
            halo = pygame.Surface((r.w + 12, r.h + 12), pygame.SRCALPHA)
            pygame.draw.rect(
                halo, (*_glow_rgb(color, a), 255), halo.get_rect(), width=2, border_radius=9
            )
            self.board.blit(
                halo, (r.x - 6, r.y - 6), special_flags=pygame.BLEND_RGBA_ADD
            )

    def _fx_sprint(self, cells: list[pygame.Rect], view: dict, now: float) -> None:
        """疾跑：青色光点沿蛇身从头向尾流动，形成速度流光。"""
        color = FRUIT_COLORS["sprint"]
        n = max(1, len(cells))
        flow = (now * 3.0) % 1.0
        for i, r in enumerate(cells):
            # 每节的亮度随流动相位正弦变化，亮斑从头向尾跑
            phase = (i / n - flow) % 1.0
            a = int(25 + 110 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi)))
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*_glow_rgb(color, a), 255), (4, 4), 3)
            self.board.blit(
                dot, (r.centerx - 4, r.centery - 4), special_flags=pygame.BLEND_RGBA_ADD
            )

    # ================================================================ 视野边缘光点
    def _beacon_cell(self, view: dict) -> tuple[int, int] | None:
        """可见范围最外圈上、指向目标方向的那一格；没有指示时返回 None。

        贴墙时把光点收进棋盘内（光点只是方向提示，不做寻路）。
        渲染层只用到八方向 (sx, sy)，永远接触不到目标坐标。
        """
        head = view.get("own_head")
        d = view.get("target_indicator")
        if not head or not d:
            return None
        sx, sy = int(d[0]), int(d[1])
        if sx == 0 and sy == 0:
            return None

        radius = max(1, int(view.get("view_radius", 1)))
        hx, hy = int(head[0]), int(head[1])
        bx = min(max(hx + sx * radius, 0), self.width - 1)
        by = min(max(hy + sy * radius, 0), self.height - 1)
        return bx, by

    def _draw_edge_beacon(self, view: dict) -> None:
        """可见范围最外圈上、指向目标方向的那一个点发光。

        颜色 = 目标本身的颜色（疾跑青/护盾紫/灯笼蓝/金苹果金），
        亮度随接近目标而增强。
        """
        cell = self._beacon_cell(view)
        if cell is None:
            return
        bx, by = cell

        kind = str(view.get("target_kind") or "")
        color = GOLD_COLOR if kind == "gold" else FRUIT_COLORS.get(kind, INDICATOR_COLOR_NORMAL)

        prox = max(0.0, min(1.0, float(view.get("target_proximity") or 0.0)))
        hi = INDICATOR_MAX_ALPHA + (INDICATOR_GOLD_BONUS if kind == "gold" else 0)
        alpha = INDICATOR_MIN_ALPHA + (hi - INDICATOR_MIN_ALPHA) * prox

        rect = self.cell_rect(bx, by)
        rect.move_ip(-self.ox, -self.oy)
        cx, cy = rect.center

        # 格底柔光（加法混合）：整格染上目标颜色
        cell_glow = pygame.Surface(rect.size, pygame.SRCALPHA)
        cell_glow.fill((*_glow_rgb(color, alpha * 0.55), 255))
        self.board.blit(cell_glow, rect.topleft, special_flags=pygame.BLEND_RGBA_ADD)

        # 光晕：由外到内渐亮的同心圆
        halo_r = int(self.cell * 0.46)
        size = halo_r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        core_r = max(2, int(self.cell * 0.16))
        for i in range(halo_r, core_r, -1):
            t = (i - core_r) / max(1, halo_r - core_r)
            a = int(alpha * 0.75 * (1 - t) ** 1.4)
            if a > 0:
                pygame.draw.circle(surf, (*_glow_rgb(color, a), 255), center, i)
        # 内核亮心
        for i in range(core_r, 0, -1):
            t = i / core_r
            a = int(min(255, alpha + 50) * (1 - t ** 2 * 0.5))
            pygame.draw.circle(surf, (*_glow_rgb(_lighten(color, 0.4), a), 255), center, i)
        self.board.blit(
            surf, (cx - center[0], cy - center[1]), special_flags=pygame.BLEND_RGBA_ADD
        )

    # ================================================================ 果子
    def _draw_fruits(self, view: dict) -> None:
        """视野内的果子与金苹果：彩色圆果 + 光晕，金苹果额外带星芒。"""
        fruit = view.get("visible_fruit")
        if fruit:
            x, y = _parse(fruit["cell"])
            color = FRUIT_COLORS.get(str(fruit.get("type")), (200, 200, 200))
            self._draw_orb(x, y, color, gold=False)
        gold = view.get("visible_gold")
        if gold:
            x, y = _parse(gold)
            self._draw_orb(x, y, GOLD_COLOR, gold=True)

    def _draw_orb(
        self, x: int, y: int, color: tuple[int, int, int], *, gold: bool
    ) -> None:
        rect = self.cell_rect(x, y)
        rect.move_ip(-self.ox, -self.oy)
        cx, cy = rect.center
        r = max(5, int(self.cell * 0.36))

        # 外层光晕（由外到内渐亮的同心圆，加法混合更有发光感）
        halo_r = int(self.cell * 0.58)
        size = halo_r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        for i in range(halo_r, r, -1):
            t = (i - r) / max(1, halo_r - r)
            a = int(110 * (1 - t) ** 1.5)
            if a > 0:
                pygame.draw.circle(surf, (*_glow_rgb(color, a), 255), center, i)
        self.board.blit(
            surf, (cx - center[0], cy - center[1]), special_flags=pygame.BLEND_RGBA_ADD
        )

        # 本体：外圈饱和、内核提亮、左上角高光——立体的小果子
        pygame.draw.circle(self.board, _dim(color, 0.8), (cx, cy), r)
        pygame.draw.circle(self.board, color, (cx, cy), max(2, int(r * 0.82)))
        pygame.draw.circle(self.board, _lighten(color, 0.5), (cx, cy), max(2, int(r * 0.55)))
        pygame.draw.circle(
            self.board,
            (255, 255, 255),
            (cx - r // 3, cy - r // 3),
            max(2, self.cell // 9),
        )
        # 深色描边：把果子从明亮的背景上"勾"出来
        pygame.draw.circle(self.board, _dim(color, 0.35), (cx, cy), r, width=2)

        if gold:
            # 金苹果：果柄 + 叶子 + 十字星芒，和普通果子一眼区分
            pygame.draw.line(
                self.board, (122, 88, 42), (cx, cy - r + 2), (cx + 3, cy - r - 5), 2
            )
            leaf = pygame.Rect(cx + 2, cy - r - 8, 9, 5)
            pygame.draw.ellipse(self.board, (108, 196, 118), leaf)
            arm = int(self.cell * 0.46)
            pygame.draw.line(self.board, (255, 244, 200), (cx - arm, cy), (cx + arm, cy), 1)
            pygame.draw.line(self.board, (255, 244, 200), (cx, cy - arm), (cx, cy + arm), 1)


# ================================================================ 工具
def _parse(key) -> tuple[int, int]:
    if isinstance(key, str):
        x, y = key.split(",", 1)
        return int(x), int(y)
    x, y = key
    return int(x), int(y)


def _dim(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    f = max(0.0, min(1.0, factor))
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


def _glow_rgb(color: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    """把「期望的有效不透明度 a(0~255)」换算成预衰减的 RGB。

    pygame 2.5 的 ``BLEND_RGBA_ADD`` 直接把源 RGB 相加、**不按 alpha 缩放**，
    因此加法混合的发光层必须用预衰减的 RGB 来表达强弱，alpha 没有用。
    """
    f = max(0.0, min(1.0, a / 255.0))
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


def _lerp_color(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """在两个颜色之间线性插值（t=0 取 a，t=1 取 b）。"""
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _lighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """向白色提亮，用于果子的立体内核。"""
    f = max(0.0, min(1.0, factor))
    return (
        int(color[0] + (255 - color[0]) * f),
        int(color[1] + (255 - color[1]) * f),
        int(color[2] + (255 - color[2]) * f),
    )


def _build_vignette(size: tuple[int, int]) -> pygame.Surface:
    """四角压暗的 vignette，强化"黑暗森林"的压迫感。"""
    w, h = size
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    max_d = math.hypot(w / 2, h / 2)
    step = 6
    for i in range(0, int(max_d), step):
        a = int(VIGNETTE[3] * ((i / max_d) ** 2) * 0.7)
        alpha = max(0, VIGNETTE[3] - a)
        # 反向：中心透明，边缘暗
        pygame.draw.ellipse(
            surf,
            (VIGNETTE[0], VIGNETTE[1], VIGNETTE[2], 0),
            pygame.Rect(i, i, w - i * 2, h - i * 2),
            width=step,
        )
    # 叠加由外到内的黑边
    for i in range(0, min(w, h) // 2, step):
        t = 1.0 - (i / (min(w, h) / 2))
        a = int(VIGNETTE[3] * (t ** 2.2))
        pygame.draw.rect(
            surf,
            (VIGNETTE[0], VIGNETTE[1], VIGNETTE[2], a),
            pygame.Rect(i, i, w - i * 2, h - i * 2),
            width=step,
        )
    return surf
