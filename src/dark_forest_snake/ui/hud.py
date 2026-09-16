"""HUD：金苹果计数、能力倒计时、事件区域。

**禁止显示**：目标坐标、距离数字、箭头、Mini Map。
"""

from __future__ import annotations

import pygame

from dark_forest_snake import config as C
from dark_forest_snake.ui import theme as T


class HUD:
    def __init__(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        self.screen = screen
        self.rect = rect

    # ================================================================ 主入口
    def draw(self, view: dict, *, enemy_label: str = "对手") -> None:
        self._draw_panel_bg()
        self._draw_gold_counts(view, enemy_label)
        self._draw_abilities(view)
        self._draw_round_info(view)
        self._draw_events(view)

    def _draw_panel_bg(self) -> None:
        pygame.draw.rect(self.screen, T.BG_PANEL, self.rect)
        pygame.draw.line(
            self.screen,
            T.GRID_COLOR,
            self.rect.topleft,
            (self.rect.left, self.rect.bottom),
            1,
        )

    # ================================================================ 金苹果
    def _draw_gold_counts(self, view: dict, enemy_label: str) -> None:
        x = self.rect.left + 18
        y = self.rect.top + 16
        T.render_text(self.screen, "金苹果", (x, y), size=17, color=T.TEXT_DIM)

        my = view.get("own_gold_count", 0)
        theirs = view.get("enemy_gold_count", 0)
        y += 26

        me_label = f"你 (P{view.get('player', 0) + 1})"
        T.render_text(self.screen, me_label, (x, y), size=17, color=T.TEXT_ACCENT)
        self._draw_pips(x + 108, y + 2, my)
        y += 24

        T.render_text(self.screen, enemy_label, (x, y), size=17, color=T.TEXT_WARN)
        self._draw_pips(x + 108, y + 2, theirs)

    def _draw_pips(self, x: int, y: int, count: int) -> None:
        """●●○ 形式。总数即获胜所需。"""
        r = 6
        gap = 17
        for i in range(C.GOLD_TO_WIN):
            cx = x + i * gap
            cy = y + r
            if i < count:
                pygame.draw.circle(self.screen, T.GOLD_COLOR, (cx, cy), r)
            else:
                pygame.draw.circle(self.screen, (52, 58, 66), (cx, cy), r, 1)

    # ================================================================ 能力
    def _draw_abilities(self, view: dict) -> None:
        x = self.rect.left + 18
        y = self.rect.top + 122
        T.render_text(self.screen, "能力", (x, y), size=17, color=T.TEXT_DIM)
        y += 26

        abilities = view.get("abilities", {}) or {}
        rows = [
            ("疾跑", abilities.get("sprint", 0.0), T.FRUIT_COLORS["sprint"]),
            ("护盾", abilities.get("shield", 0.0), T.FRUIT_COLORS["shield"]),
            ("灯笼", abilities.get("lantern", 0.0), T.FRUIT_COLORS["lantern"]),
        ]
        for name, remain, color in rows:
            active = remain > 0
            label_color = color if active else (58, 64, 72)
            T.render_text(self.screen, name, (x, y), size=18, color=label_color)
            if active:
                text = f"{remain:4.1f}s"
                T.render_text(self.screen, text, (x + 62, y), size=18, color=T.TEXT_PRIMARY)
                self._draw_bar(x, y + 24, remain / C.ABILITY_DURATION, color)
            else:
                T.render_text(self.screen, "  --  ", (x + 62, y), size=18, color=(52, 58, 66))
            y += 46

        # 疾跑是否正在生效
        if view.get("boosting"):
            T.render_text(
                self.screen, "▶ 疾跑中", (x, y + 2), size=17, color=T.FRUIT_COLORS["sprint"], bold=True
            )

    def _draw_bar(self, x: int, y: int, ratio: float, color) -> None:
        w = 118
        h = 4
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(self.screen, (34, 38, 44), pygame.Rect(x, y, w, h), border_radius=2)
        pygame.draw.rect(
            self.screen, color, pygame.Rect(x, y, int(w * ratio), h), border_radius=2
        )

    # ================================================================ 轮次
    def _draw_round_info(self, view: dict) -> None:
        x = self.rect.left + 18
        y = self.rect.top + 296
        T.render_text(self.screen, "视野", (x, y), size=17, color=T.TEXT_DIM)
        radius = view.get("view_radius", 1)
        label = f"{radius} 格" + ("（灯笼）" if radius > 1 else "")
        T.render_text(self.screen, label, (x + 46, y), size=17, color=T.TEXT_PRIMARY)

        y += 24
        if view.get("reveal_active"):
            remain = view.get("reveal_remaining", 0.0)
            T.render_text(
                self.screen,
                f"✦ 全图照亮 {remain:.1f}s",
                (x, y),
                size=18,
                color=T.TEXT_GOLD,
                bold=True,
            )

    # ================================================================ 事件
    def _draw_events(self, view: dict) -> None:
        events = view.get("events", []) or []
        if not events:
            return
        x = self.rect.left + 18
        y = self.rect.bottom - 22 - len(events[-5:]) * 21
        T.render_text(self.screen, "事件", (x, y - 22), size=16, color=T.TEXT_DIM)
        for ev in events[-5:]:
            text = str(ev.get("text", ""))
            color = T.TEXT_PRIMARY
            if "金苹果" in text:
                color = T.TEXT_GOLD
            elif "护盾" in text:
                color = T.FRUIT_COLORS["shield"]
            elif "疾跑" in text:
                color = T.FRUIT_COLORS["sprint"]
            elif "灯笼" in text:
                color = T.FRUIT_COLORS["lantern"]
            elif "死亡" in text or "获胜" in text:
                color = T.TEXT_WARN
            T.render_text(self.screen, _ellipsize(text, 22), (x, y), size=16, color=color)
            y += 21


def _ellipsize(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
