"""主菜单与各种界面（玩法说明、LAN 输入、胜负画面）。"""

from __future__ import annotations

import pygame

from dark_forest_snake import config as C
from dark_forest_snake.ui import theme as T


def result_subtitle(winner: int, view: dict | None) -> str:
    """结算副标题：按**真实获胜方式**区分集齐金苹果与击杀获胜。

    依据是胜者自己的金苹果数（view 里的 own/enemy gold count，
    是公开信息，单机和 LAN 都能拿到），而不是无条件写死
    "集齐了 3 个金苹果"——后者会把撞死对手的胜利也误报成集苹果。
    """
    who = f"P{winner + 1}"
    winner_gold = 0
    if view is not None:
        if view.get("player") == winner:
            winner_gold = int(view.get("own_gold_count", 0) or 0)
        else:
            winner_gold = int(view.get("enemy_gold_count", 0) or 0)
    if winner_gold >= C.GOLD_TO_WIN:
        return f"{who} 集齐了 3 个金苹果"
    return f"{who} 击杀对手获胜"


class Menu:
    """一个通用的纵向菜单。"""

    def __init__(
        self,
        screen: pygame.Surface,
        title: str,
        items: list[str],
        *,
        subtitle: str = "",
        footer: str = "",
    ) -> None:
        self.screen = screen
        self.title = title
        self.items = items
        self.subtitle = subtitle
        self.footer = footer
        self.index = 0

    def move(self, delta: int) -> None:
        if not self.items:
            return
        self.index = (self.index + delta) % len(self.items)

    def selected(self) -> str:
        return self.items[self.index]

    def draw(self) -> None:
        self.screen.fill(T.BG_DARK)
        rect = self.screen.get_rect()
        cx = rect.centerx

        T.render_text(self.screen, self.title, (cx, rect.top + 90), size=46, color=T.TEXT_ACCENT, center=True, bold=True)
        if self.subtitle:
            T.render_text(
                self.screen, self.subtitle, (cx, rect.top + 142), size=19, color=T.TEXT_DIM, center=True
            )

        start_y = rect.top + 240
        for i, item in enumerate(self.items):
            y = start_y + i * 58
            active = i == self.index
            if active:
                box = pygame.Rect(0, 0, 380, 46)
                box.center = (cx, y)
                pygame.draw.rect(self.screen, (22, 30, 28), box, border_radius=6)
                pygame.draw.rect(self.screen, T.TEXT_ACCENT, box, width=1, border_radius=6)
            color = T.TEXT_ACCENT if active else T.TEXT_PRIMARY
            prefix = "▸ " if active else "  "
            T.render_text(
                self.screen, prefix + item, (cx, y), size=24, color=color, center=True, bold=active
            )

        if self.footer:
            T.render_text(
                self.screen, self.footer, (cx, rect.bottom - 46), size=17, color=T.TEXT_DIM, center=True
            )


class TextScreen:
    """纯文本信息页（玩法说明、帮助等）。"""

    def __init__(
        self,
        screen: pygame.Surface,
        title: str,
        lines: list[str],
        *,
        footer: str = "按 ESC / Enter 返回",
    ) -> None:
        self.screen = screen
        self.title = title
        self.lines = lines
        self.footer = footer

    def draw(self) -> None:
        self.screen.fill(T.BG_DARK)
        rect = self.screen.get_rect()
        T.render_text(self.screen, self.title, (rect.centerx, rect.top + 56), size=36, color=T.TEXT_ACCENT, center=True, bold=True)
        y = rect.top + 118
        for line in self.lines:
            if line.startswith("##"):
                T.render_text(self.screen, line[2:].strip(), (rect.left + 90, y), size=21, color=T.TEXT_ACCENT, bold=True)
                y += 32
                continue
            color = T.TEXT_PRIMARY if line else T.TEXT_DIM
            T.render_text(self.screen, line, (rect.left + 90, y), size=18, color=color)
            y += 25
        T.render_text(self.screen, self.footer, (rect.centerx, rect.bottom - 40), size=17, color=T.TEXT_DIM, center=True)


class TextInputScreen:
    """一行文本输入（用于输入 Host IP）。"""

    def __init__(
        self,
        screen: pygame.Surface,
        title: str,
        prompt: str,
        *,
        initial: str = "127.0.0.1",
        hint: str = "",
    ) -> None:
        self.screen = screen
        self.title = title
        self.prompt = prompt
        self.value = initial
        self.hint = hint
        self.cursor_on = True
        self._t = 0.0

    def handle_event(self, ev: pygame.event.Event) -> str | None:
        """返回 'ok' / 'cancel' / None（继续输入）。"""
        if ev.type != pygame.KEYDOWN:
            return None
        if ev.key == pygame.K_RETURN:
            return "ok"
        if ev.key == pygame.K_ESCAPE:
            return "cancel"
        if ev.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
            return None
        ch = ev.unicode
        if ch and (ch.isdigit() or ch == "." or ch == ":"):
            self.value += ch
        return None

    def update(self, dt: float) -> None:
        self._t += dt
        if self._t > 0.5:
            self._t = 0.0
            self.cursor_on = not self.cursor_on

    def draw(self, *, error: str = "", status: str = "") -> None:
        self.screen.fill(T.BG_DARK)
        rect = self.screen.get_rect()
        T.render_text(self.screen, self.title, (rect.centerx, rect.top + 100), size=38, color=T.TEXT_ACCENT, center=True, bold=True)
        T.render_text(self.screen, self.prompt, (rect.centerx, rect.top + 190), size=21, color=T.TEXT_PRIMARY, center=True)

        box = pygame.Rect(0, 0, 460, 56)
        box.center = (rect.centerx, rect.top + 250)
        pygame.draw.rect(self.screen, (16, 20, 25), box, border_radius=6)
        pygame.draw.rect(self.screen, T.TEXT_ACCENT, box, width=2, border_radius=6)
        shown = self.value + ("|" if self.cursor_on else " ")
        T.render_text(self.screen, shown, box.center, size=26, color=T.TEXT_PRIMARY, center=True)

        if self.hint:
            T.render_text(self.screen, self.hint, (rect.centerx, rect.top + 300), size=17, color=T.TEXT_DIM, center=True)
        if status:
            T.render_text(self.screen, status, (rect.centerx, rect.top + 340), size=18, color=T.TEXT_ACCENT, center=True)
        if error:
            T.render_text(self.screen, error, (rect.centerx, rect.top + 374), size=18, color=T.TEXT_WARN, center=True)
        T.render_text(self.screen, "Enter 确认    ESC 返回", (rect.centerx, rect.bottom - 44), size=17, color=T.TEXT_DIM, center=True)


class CountdownOverlay:
    """开局倒计时 + 阶段变化提示。"""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen

    def draw_countdown(self, remaining: float) -> None:
        rect = self.screen.get_rect()
        veil = pygame.Surface(rect.size, pygame.SRCALPHA)
        veil.fill((0, 0, 0, 150))
        self.screen.blit(veil, (0, 0))
        n = max(1, int(remaining + 0.999))
        T.render_text(self.screen, str(n), rect.center, size=120, color=T.TEXT_ACCENT, center=True, bold=True)
        T.render_text(
            self.screen,
            "在黑暗中，只有光会告诉你方向",
            (rect.centerx, rect.centery + 90),
            size=20,
            color=T.TEXT_DIM,
            center=True,
        )

    def draw_banner(self, text: str, *, color=None, y_ratio: float = 0.22, size: int = 34) -> None:
        rect = self.screen.get_rect()
        T.render_text(
            self.screen,
            text,
            (rect.centerx, int(rect.height * y_ratio)),
            size=size,
            color=color or T.TEXT_GOLD,
            center=True,
            bold=True,
        )


class GameOverScreen:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen

    def draw(self, *, winner: int | None, draw: bool, local_player: int | None, view: dict | None) -> None:
        rect = self.screen.get_rect()
        veil = pygame.Surface(rect.size, pygame.SRCALPHA)
        veil.fill((0, 0, 0, 205))
        self.screen.blit(veil, (0, 0))

        if draw:
            title, color = "平局", T.TEXT_PRIMARY
            sub = "整局重新开始"
        elif winner is None:
            title, color = "对局结束", T.TEXT_PRIMARY
            sub = ""
        else:
            who = f"P{winner + 1}"
            if local_player is not None and winner == local_player:
                title, color = "你赢了", T.TEXT_GOLD
            elif local_player is not None:
                title, color = "你输了", T.TEXT_WARN
            else:
                title, color = f"{who} 获胜", T.TEXT_ACCENT
            sub = result_subtitle(winner, view)

        T.render_text(self.screen, title, (rect.centerx, rect.centery - 60), size=62, color=color, center=True, bold=True)
        if sub:
            T.render_text(self.screen, sub, (rect.centerx, rect.centery + 10), size=21, color=T.TEXT_DIM, center=True)

        if view is not None:
            mine = view.get("own_gold_count", 0)
            theirs = view.get("enemy_gold_count", 0)
            T.render_text(
                self.screen,
                f"金苹果  你 {mine}  :  {theirs} 对手",
                (rect.centerx, rect.centery + 56),
                size=22,
                color=T.TEXT_PRIMARY,
                center=True,
            )

        T.render_text(
            self.screen,
            "R 重新开始        ESC 返回主菜单",
            (rect.centerx, rect.bottom - 70),
            size=20,
            color=T.TEXT_DIM,
            center=True,
        )
