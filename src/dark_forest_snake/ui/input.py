"""输入处理：按键 → 游戏意图。

严格分离「登记意图」与「推进世界」：这里只把按键翻译成
Direction / sprint 状态，交给 Game Engine 或 Client 上行。
"""

from __future__ import annotations

import pygame

from dark_forest_snake.core.geometry import Direction

# WASD 与方向键都支持
DIRECTION_KEYS: dict[int, Direction] = {
    pygame.K_w: Direction.UP,
    pygame.K_UP: Direction.UP,
    pygame.K_s: Direction.DOWN,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_a: Direction.LEFT,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_d: Direction.RIGHT,
    pygame.K_RIGHT: Direction.RIGHT,
}

SPRINT_KEYS = (pygame.K_LSHIFT, pygame.K_RSHIFT)


class InputState:
    """一帧的输入快照。"""

    def __init__(self) -> None:
        self.directions: list[Direction] = []   # 本帧登记的转向意图（可能有多个）
        self.sprint = False
        self.quit = False
        self.confirm = False
        self.back = False
        self.pause = False
        self.debug_toggle = False
        self.restart = False


def read_input(events: list[pygame.event.Event]) -> InputState:
    st = InputState()
    pressed = pygame.key.get_pressed()
    st.sprint = any(pressed[k] for k in SPRINT_KEYS)

    for ev in events:
        if ev.type == pygame.QUIT:
            st.quit = True
        elif ev.type == pygame.KEYDOWN:
            if ev.key in DIRECTION_KEYS:
                st.directions.append(DIRECTION_KEYS[ev.key])
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                st.confirm = True
            elif ev.key == pygame.K_ESCAPE:
                st.back = True
            elif ev.key == pygame.K_p:
                st.pause = True
            elif ev.key == pygame.K_F1:
                st.debug_toggle = True
            elif ev.key == pygame.K_r:
                st.restart = True
    return st
