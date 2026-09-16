"""UI 无头冒烟测试。

沙箱里没有显示器，但可以用 SDL 的 dummy 驱动完整跑通渲染路径：
    SDL_VIDEODRIVER=dummy  +  SDL_AUDIODRIVER=dummy

这个测试会：
- 构建 App（真实 pygame 窗口，dummy 驱动）
- 渲染菜单 / 玩法说明 / LAN 等待页
- 跑一整局单机（玩家输入由脚本注入）
- 检查中文渲染不是 tofu
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from dark_forest_snake import config as C  # noqa: E402
from dark_forest_snake.ui import theme as T  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from dark_forest_snake.main import App

    a = App()
    yield a
    pygame.quit()


def test_pygame_initialises(app) -> None:
    assert pygame.get_init()


def test_cjk_font_is_not_tofu(app) -> None:
    """关键：中文必须真的能渲染，而不是一片方框。

    注意 font.metrics 对缺字也会返回非 None，必须比较 advance 宽度。
    """
    assert T.font_ok(), "中文字体渲染异常"

    font = T.get_font(36)
    m = font.metrics("贪吃蛇")
    assert m and m[0] is not None
    assert m[0][4] >= 18, f"中文 advance 过窄 ({m[0][4]})，可能是 tofu"

    # 整段文案的总宽度也应合理
    text = "黑暗森林贪吃蛇"
    width = font.size(text)[0]
    assert width / len(text) >= 18, f"中文平均字宽过小 ({width / len(text):.1f})，疑似方框"


def test_render_menus(app) -> None:
    app.main_menu.draw()
    app.lan_menu.draw()
    app.help_screen.draw()
    pygame.display.flip()


def test_render_lan_waiting_and_error(app) -> None:
    app.lan_status = "房间已创建"
    app.mode = "lan_host"
    app._draw_lan_waiting()
    app.mode = "lan_client"
    app._draw_lan_waiting()

    app.lan_error = "无法连接到 192.168.1.10:8765。请确认 Host 已启动、IP 正确、防火墙已放行"
    app._draw_lan_error()
    pygame.display.flip()


def test_render_solo_game_for_many_frames(app) -> None:
    """完整跑若干局单机，期间持续渲染，确认不崩溃、不死循环。

    玩家与 AI 都由脚本驱动；若一局结束就立刻重开，保证渲染帧数足够多。
    """
    import random

    from dark_forest_snake.ai.snake_ai import SnakeAI, perception_from_view
    from dark_forest_snake.core.game import P1, P2, Game
    from dark_forest_snake.core.geometry import Direction

    rng = random.Random(7)
    dirs = list(Direction)
    frames = 0
    total_ticks = 0

    for round_no in range(12):
        seed = 1000 + round_no
        g = Game(width=20, height=16, seed=seed, debug=False)
        g.start_match(countdown=0.0)
        ai = SnakeAI(P2, random.Random(seed + 1))
        # 让玩家也交给 AI 代理，避免随机输入把自己立刻撞死
        player_bot = SnakeAI(P1, random.Random(seed + 2))

        for i in range(1200):
            if g.state.phase.is_playing:
                for pid, bot in ((P1, player_bot), (P2, ai)):
                    perc = perception_from_view(g.view_for(pid), (g.width, g.height))
                    act = bot.decide(perc)
                    if act.direction is not None:
                        g.input_direction(pid, act.direction)
                    g.input_sprint(pid, act.sprint)
            g.update(C.BASE_MOVE_INTERVAL)

            view = g.view_for(P1).to_dict()
            app.game = g
            app.mode = "solo"
            app._draw_board(view, g, local_player=P1)
            frames += 1
            if g.is_over():
                break
        total_ticks += g.tick_count

    assert frames > 300, f"渲染帧数过少 ({frames})"
    assert total_ticks > 100, f"引擎推进过少 ({total_ticks})"


def test_render_game_over_screen(app) -> None:
    from dark_forest_snake.core.game import P1, Game

    g = Game(width=20, height=16, seed=5)
    g.start_match(countdown=0.0)
    g._end_game(winner=P1, reason="test")
    view = g.view_for(P1).to_dict()
    app._draw_board(view, g, local_player=P1)
    app._draw_board(view, g, local_player=1 - P1)


def test_render_draw_screen(app) -> None:
    from dark_forest_snake.core.game import Game

    g = Game(width=20, height=16, seed=6)
    g.start_match(countdown=0.0)
    g.draw = True
    g.state.transition(__import__("dark_forest_snake.core.state", fromlist=["GamePhase"]).GamePhase.DRAW_RESTART)
    view = g.view_for(0).to_dict()
    app._draw_board(view, g, local_player=0)


def test_render_debug_view(app) -> None:
    from dark_forest_snake.core.game import Game

    g = Game(width=20, height=16, seed=8, debug=True)
    g.start_match(countdown=0.0)
    view = g.view_for(0).to_dict()
    app.debug = True
    app._draw_board(view, g, local_player=0)
    app.debug = False


def test_render_with_lan_view(app) -> None:
    """用一份（不含隐藏信息的）视角字典走 LAN 渲染路径。"""
    from dark_forest_snake.core.game import Game

    g = Game(width=20, height=16, seed=9)
    g.start_match(countdown=0.0)
    view = g.view_for(0).to_dict()
    app.lan_player = 0
    app.lan_status = "对局进行中"
    app._draw_board(view, None, local_player=0, lan=True)


def test_menus_navigate(app) -> None:
    m = app.main_menu
    m.index = 0
    m.move(1)
    assert m.index == 1
    m.move(-1)
    assert m.index == 0
    m.move(-1)
    assert m.index == len(m.items) - 1, "应循环"
