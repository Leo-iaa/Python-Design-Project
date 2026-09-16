"""视觉主题：色彩与字体。

基调：黑暗 / 克制 / 危险 / 森林 / 微光。
刻意不使用普通贪吃蛇的高饱和彩色。
"""

from __future__ import annotations

import os

import pygame

# ---------------------------------------------------------------- 背景
BG_DARK = (7, 9, 12)
BG_PANEL = (13, 16, 21)
GRID_COLOR = (64, 76, 92)
GRID_DARK = (44, 53, 66)

# ---------------------------------------------------------------- 环境光（视野内格子的底色）
# 灰 → 暖黄的渐变：蛇头附近偏暖黄，视野边缘偏灰。
AMBIENT_NEAR = (168, 158, 118)
AMBIENT_FAR = (85, 90, 100)

# ---------------------------------------------------------------- 墙体 / 棋盘边缘
WALL_GLOW = (72, 88, 84)
WALL_CORE = (34, 42, 48)
# 棋盘可玩区域的内沿描边：撞墙前的最后一道视觉提醒
BOARD_EDGE = (110, 142, 130)

# ---------------------------------------------------------------- 蛇
OWN_HEAD = (150, 230, 190)
OWN_BODY = (58, 120, 100)
OWN_BODY_DIM = (46, 90, 76)
OWN_HEAD_GLOW = (140, 226, 186)
ENEMY_BODY = (206, 94, 94)
ENEMY_HEAD = (226, 130, 120)
ENEMY_GLOW = (230, 80, 80)
ENEMY_EDGE = (255, 158, 148)

# ---------------------------------------------------------------- 果子
FRUIT_COLORS = {
    "sprint": (86, 214, 214),    # 青色
    "shield": (168, 122, 214),   # 紫色
    "lantern": (108, 156, 240),  # 蓝色
}
GOLD_COLOR = (232, 192, 92)

# ---------------------------------------------------------------- 视野边缘光点（方向指示）
# 可见范围最外圈上、指向目标方向的那一个点发光：
# 颜色就是目标本身的颜色（疾跑青/护盾紫/灯笼蓝/金苹果金），
# 亮度随接近目标而增强。光点小而集中，不干扰整片视野。
INDICATOR_COLOR_NORMAL = (96, 214, 140)    # 兜底色（正常不会用到）
INDICATOR_COLOR_GOLD = GOLD_COLOR
INDICATOR_MIN_ALPHA = 80                   # 距目标最远时仍清晰可辨
INDICATOR_MAX_ALPHA = 185                  # 贴近目标时的峰值亮度
INDICATOR_GOLD_BONUS = 20                  # 金苹果阶段额外提亮

# ---------------------------------------------------------------- 文字
TEXT_PRIMARY = (206, 216, 226)
TEXT_DIM = (120, 132, 146)
TEXT_ACCENT = (150, 230, 190)
TEXT_WARN = (226, 132, 120)
TEXT_GOLD = (232, 192, 92)

# ---------------------------------------------------------------- 效果
VIGNETTE = (0, 0, 0, 200)
REVEAL_TINT = (58, 72, 92)

# ---------------------------------------------------------------- 字体
_CJK_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Heiti SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
]

_font_cache: dict[tuple[int, bool], pygame.font.Font] = {}
_resolved_name: str | None = None


def _pick_font(size: int) -> pygame.font.Font:
    """挑一个真正能渲染中文的字体。

    注意：``font.metrics("贪")[0] is not None`` 永远为 True —— 即使字体缺字，
    pygame 也会返回一个 6 元组，只是 advance_x 很小。必须用 advance 宽度判断，
    否则会静默选中一个把所有中文渲染成方框（tofu）的字体。
    """
    global _resolved_name
    threshold = size * 0.5

    if _resolved_name is not None:
        f = pygame.font.SysFont(_resolved_name, size)
        if _renders_cjk(f, threshold):
            return f
        _resolved_name = None

    for name in _CJK_CANDIDATES:
        try:
            f = pygame.font.SysFont(name, size)
        except Exception:
            continue
        if _renders_cjk(f, threshold):
            _resolved_name = name
            return f

    # 退回到系统默认（英文仍可读）
    return pygame.font.SysFont(None, size)


def _renders_cjk(font: pygame.font.Font, threshold: float) -> bool:
    try:
        m = font.metrics("贪吃蛇")
    except Exception:
        return False
    if not m or m[0] is None:
        return False
    return m[0][4] >= threshold


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    f = _pick_font(size)
    if bold:
        f.set_bold(True)
    _font_cache[key] = f
    return f


def font_ok() -> bool:
    """供启动自检：确认中文能正常渲染。"""
    f = get_font(24)
    return _renders_cjk(f, 12)


def render_text(
    surface: pygame.Surface,
    text: str,
    pos: tuple[int, int],
    *,
    size: int = 20,
    color: tuple[int, int, int] = TEXT_PRIMARY,
    center: bool = False,
    bold: bool = False,
) -> pygame.Rect:
    font = get_font(size, bold)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surface.blit(img, rect)
    return rect


def text_width(text: str, size: int = 20, bold: bool = False) -> int:
    return get_font(size, bold).size(text)[0]
