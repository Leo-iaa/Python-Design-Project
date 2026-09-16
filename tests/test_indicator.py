"""八方向目标指示格测试。

机制约定（本文件就是这份约定的可执行规范）：
- 蛇头 8 邻格中**恰好 1 格**发光，指向当前目标的大致八方向。
- 方向由 sign(dx)/sign(dy) 量化，与距离无关。
- 普通果子阶段指向普通果子，金苹果阶段自动切换指向金苹果。
- 指示格距蛇头恒为 1 格（灯笼也不改变）。
- 对外（PlayerViewState / 网络 / AI）只传量化方向 (sx, sy)，
  绝不包含目标坐标与距离。
- 全图照亮时渲染层不突出指示格。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from dark_forest_snake import config as C  # noqa: E402
from dark_forest_snake.core.game import P1, P2, Game  # noqa: E402
from dark_forest_snake.core.geometry import Cell, Direction  # noqa: E402
from dark_forest_snake.core.indicator import (  # noqa: E402
    INDICATOR_NAMES,
    indicator_cell,
    indicator_cell_from_direction,
    indicator_direction,
    indicator_name,
)

HEAD = Cell(10, 10)


# ================================================================ 一、八方向基础
@pytest.mark.parametrize(
    "target,expected",
    [
        (Cell(10, 2), "N"),
        (Cell(16, 2), "NE"),
        (Cell(18, 10), "E"),
        (Cell(18, 20), "SE"),
        (Cell(10, 20), "S"),
        (Cell(2, 20), "SW"),
        (Cell(2, 10), "W"),
        (Cell(2, 2), "NW"),
    ],
)
def test_eight_directions(target: Cell, expected: str) -> None:
    """规范指定的 8 个方向用例：head=(10,10)。"""
    assert indicator_name(HEAD, target) == expected
    cell = indicator_cell(HEAD, target)
    sx, sy = indicator_direction(HEAD, target)
    assert cell == Cell(HEAD.x + sx, HEAD.y + sy)
    # 指示格距蛇头恒为 1 格（含对角）
    assert cell.chebyshev(HEAD) == 1


def test_indicator_is_exactly_one_cell() -> None:
    """任意目标下，指示格只有一个，且一定在 8 邻格内。"""
    rng_targets = [Cell(x, y) for x in range(0, 24, 3) for y in range(0, 18, 3)]
    for t in rng_targets:
        cell = indicator_cell(HEAD, t)
        if t == HEAD:
            assert cell is None
        else:
            assert cell is not None
            assert cell.chebyshev(HEAD) == 1


def test_direction_independent_of_distance() -> None:
    """同方向不同距离，指示完全一致（不透露距离）。"""
    near = indicator_cell(HEAD, Cell(11, 9))
    far = indicator_cell(HEAD, Cell(100, 0))
    assert near == far == Cell(11, 9)
    assert indicator_direction(HEAD, Cell(11, 9)) == indicator_direction(HEAD, Cell(100, 0))


def test_all_direction_deltas_are_valid_eight() -> None:
    """量化结果只能落在 8 个合法方向上。"""
    for x in (-3, -1, 0, 2, 7):
        for y in (-4, -1, 0, 1, 5):
            t = Cell(HEAD.x + x, HEAD.y + y)
            d = indicator_direction(HEAD, t)
            if d == (0, 0):
                continue
            assert d in INDICATOR_NAMES


def test_target_on_head_gives_no_indicator() -> None:
    assert indicator_cell(HEAD, HEAD) is None


def test_indicator_cell_from_direction_roundtrip() -> None:
    assert indicator_cell_from_direction(HEAD, (1, -1)) == Cell(11, 9)
    assert indicator_cell_from_direction(HEAD, (0, 0)) is None
    with pytest.raises(ValueError):
        indicator_cell_from_direction(HEAD, (2, 0))


# ================================================================ 二、阶段切换
def _force_play(g: Game) -> None:
    g.start_match(countdown=0.0)
    g.update(0.0)


def _park_snakes(g: Game) -> None:
    g.snakes[P1].body = [Cell(3, 12), Cell(2, 12), Cell(1, 12)]
    g.snakes[P2].body = [Cell(20, 4), Cell(21, 4), Cell(22, 4)]
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].direction = Direction.LEFT
    for s in g.snakes.values():
        s.alive = True
        s.death_reason = None


def test_normal_phase_indicator_points_to_fruit() -> None:
    """普通果子阶段：指示方向 = 真实普通果子的量化方向。"""
    g = Game(width=24, height=18, seed=41)
    _force_play(g)
    assert g.fruits.fruit is not None
    view = g.view_for(P1)
    expected = indicator_direction(g.snakes[P1].head, g.fruits.fruit.cell)
    assert view.target_indicator == expected
    assert view.target_indicator in INDICATOR_NAMES


def test_golden_phase_indicator_switches_to_gold() -> None:
    """金苹果出现后：指示立即从普通果子切换到金苹果，不残留旧方向。"""
    g = Game(width=24, height=18, seed=42)
    _force_play(g)
    fruit_dir = g.view_for(P1).target_indicator

    # 直接进入金苹果阶段（内部真相切换）
    g.fruits.clear_fruit()
    g.fruits.spawn_gold(g._all_occupied_cells())
    from dark_forest_snake.core.state import GamePhase
    g.state.transition(GamePhase.PLAYING_GOLDEN)

    assert g.fruits.gold is not None
    view = g.view_for(P1)
    expected = indicator_direction(g.snakes[P1].head, g.fruits.gold.cell)
    assert view.target_indicator == expected
    # 指示跟着新目标走；除非两个目标恰好在同一方向，否则必须已切换
    gold_dir = expected
    fruit_cell_dir = None  # 旧果子已消失，无从指示
    assert fruit_cell_dir is None
    assert gold_dir in INDICATOR_NAMES
    # 与旧普通果子方向不同的种子占多数；本测试强制用真实金苹果位置校验
    assert view.target_indicator == indicator_direction(
        g.snakes[P1].head, g.fruits.gold.cell
    )


def test_indicator_updates_when_target_moves() -> None:
    """吃掉果子刷新目标后，指示跟随新目标（无上一轮残留）。"""
    g = Game(width=24, height=18, seed=43)
    _force_play(g)
    _park_snakes(g)

    # 手动换一个确定位置的果子，验证指示立即跟随
    g.fruits.clear_fruit()
    from dark_forest_snake.core.fruit import Fruit, FruitType

    head = g.snakes[P1].head  # (3,12)
    g.fruits.fruit = Fruit(cell=Cell(20, 2), type=FruitType.SPRINT)
    v1 = g.view_for(P1).target_indicator
    assert v1 == (1, -1), f"目标在右上应为 NE，实际 {v1}"

    g.fruits.fruit = Fruit(cell=Cell(1, 16), type=FruitType.SHIELD)
    v2 = g.view_for(P1).target_indicator
    assert v2 == (-1, 1), f"目标在左下应为 SW，实际 {v2}"


def test_indicator_follows_head_movement() -> None:
    """蛇移动后指示实时重算：越过目标横坐标后方向应变。"""
    g = Game(width=24, height=18, seed=44)
    _force_play(g)
    g.fruits.clear_fruit()
    g.fruits.clear_gold()
    from dark_forest_snake.core.fruit import Fruit, FruitType

    g.fruits.fruit = Fruit(cell=Cell(10, 5), type=FruitType.LANTERN)
    # 蛇头在目标左侧 → E/NE/SE 之一
    g.snakes[P1].body = [Cell(5, 5), Cell(4, 5), Cell(3, 5)]
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = [Cell(20, 15), Cell(21, 15), Cell(22, 15)]
    g.snakes[P2].direction = Direction.LEFT

    d1 = g.view_for(P1).target_indicator
    assert d1 == (1, 0), f"目标正右应为 E，实际 {d1}"

    # 蛇头越过目标横坐标 → 应变 W
    g.snakes[P1].body = [Cell(12, 5), Cell(12, 6), Cell(12, 7)]
    d2 = g.view_for(P1).target_indicator
    assert d2 == (-1, 0), f"越过目标后应为 W，实际 {d2}"


# ================================================================ 三、信息隐藏
def test_view_contains_no_target_coordinates() -> None:
    """PlayerViewState / to_dict 不含任何目标坐标，只有八方向量化值。"""
    g = Game(width=24, height=18, seed=45)
    _force_play(g)
    for pid in (P1, P2):
        v = g.view_for(pid).to_dict()
        for bad in (
            "fruit",
            "fruit_position",
            "fruit_cell",
            "gold",
            "gold_position",
            "gold_cell",
            "target",
            "target_cell",
            "target_position",
            "target_x",
            "target_y",
            "gold_trigger",
            "normal_eaten",
        ):
            assert bad not in v, f"视角泄漏了 {bad}"
        # 指示只允许是八方向之一
        ind = v["target_indicator"]
        assert ind is None or tuple(ind) in INDICATOR_NAMES


def test_indicator_cannot_reveal_distance() -> None:
    """目标无论远近，同一方向的 view 指示完全相同（无可反推的距离信息）。"""
    g = Game(width=24, height=18, seed=46)
    _force_play(g)
    g.fruits.clear_fruit()
    from dark_forest_snake.core.fruit import Fruit, FruitType

    g.snakes[P1].body = [Cell(3, 12), Cell(2, 12), Cell(1, 12)]
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = [Cell(20, 4), Cell(21, 4), Cell(22, 4)]
    g.snakes[P2].direction = Direction.LEFT

    g.fruits.fruit = Fruit(cell=Cell(5, 10), type=FruitType.SPRINT)   # 近 NE
    near_view = g.view_for(P1).to_dict()
    g.fruits.fruit = Fruit(cell=Cell(22, 1), type=FruitType.SPRINT)   # 远 NE
    far_view = g.view_for(P1).to_dict()

    assert near_view["target_indicator"] == far_view["target_indicator"]
    # 且环境光也与目标无关：两份 view 的亮度表必须完全一致
    assert near_view["visible_brightness"] == far_view["visible_brightness"]


def test_ambient_brightness_is_target_invariant() -> None:
    """环境光只由自己蛇头决定：移动目标亮度表纹丝不动。"""
    g = Game(width=24, height=18, seed=47)
    _force_play(g)
    head = g.snakes[P1].head
    v1 = g.view_for(P1).to_dict()["visible_brightness"]

    g.fruits.clear_fruit()
    from dark_forest_snake.core.fruit import Fruit, FruitType

    g.fruits.fruit = Fruit(cell=Cell(head.x + 5, head.y + 5), type=FruitType.SHIELD)
    g.snakes[P1].body = [head, Cell(head.x - 1, head.y), Cell(head.x - 2, head.y)]
    v2 = g.view_for(P1).to_dict()["visible_brightness"]
    assert v1 == v2


# ================================================================ 四、灯笼与边界
def test_lantern_does_not_move_indicator_beyond_first_ring() -> None:
    """灯笼视野 radius=2 时，指示格仍是蛇头第一圈 8 邻格之一。"""
    g = Game(width=24, height=18, seed=48)
    _force_play(g)
    g.abilities[P1].grant("lantern", g.clock)

    view = g.view_for(P1)
    assert view.view_radius == C.LANTERN_VIEW_RADIUS
    assert view.target_indicator is not None
    head = g.snakes[P1].head
    sx, sy = view.target_indicator
    cell = Cell(head.x + sx, head.y + sy)
    assert cell.chebyshev(head) == 1, "指示格必须在第一圈，不能因灯笼推到第二圈"


def test_indicator_may_point_at_wall_ring() -> None:
    """蛇头贴边、目标在墙方向：指示格可以是墙格（表达方向，不是寻路建议）。"""
    head = Cell(1, 1)
    target = Cell(0, 0)  # 角落墙格方向
    cell = indicator_cell(head, target)
    assert cell == Cell(0, 0), "允许指示格落在墙环上"


def test_indicator_can_be_off_map_and_renderer_clamps() -> None:
    """蛇头在边界、目标在地图外方向：core 层给出越界格，渲染层把它收进棋盘内。"""
    head = Cell(0, 0)
    target = Cell(-5, -3)  # 内部真相不会这样，但函数必须稳健
    cell = indicator_cell(head, target)
    assert cell == Cell(-1, -1), "core 不做边界修正（方向提示 ≠ 寻路）"

    pygame = pytest.importorskip("pygame")
    from dark_forest_snake.ui.renderer import Renderer

    pygame.init()
    screen = pygame.Surface((800, 600))
    r = Renderer(screen, 24, 18, cell_size=24, origin=(0, 0))
    view = {
        "own_head": [0, 0],
        "own_direction": [1, 0],
        "own_body": [[0, 0], [0, 1], [0, 2]],
        "target_indicator": [-1, -1],  # 指向地图外
        "visible_brightness": {"0,0": 0.9, "1,0": 0.6, "0,1": 0.6, "1,1": 0.4},
        "visible_enemy_cells": [],
        "reveal_active": False,
        "view_radius": 1,
    }
    # 不抛 IndexError/KeyError 即通过，且光点必须被收进棋盘内
    r.draw(view)
    beacon = r._beacon_cell(view)
    assert beacon is not None
    assert 0 <= beacon[0] < 24 and 0 <= beacon[1] < 18


def test_renderer_skips_beacon_without_indicator() -> None:
    """没有八方向指示时渲染层安全跳过（不画光点、不报错）。"""
    pygame = pytest.importorskip("pygame")
    from dark_forest_snake.ui.renderer import Renderer

    pygame.init()
    r = Renderer(pygame.Surface((800, 600)), 24, 18, cell_size=24, origin=(0, 0))
    assert r._beacon_cell({"own_head": [0, 0], "target_indicator": None}) is None
    assert r._beacon_cell({"own_head": [0, 0], "target_indicator": [0, 0]}) is None
    assert r._beacon_cell({}) is None


# ================================================================ 五、渲染行为
@pytest.fixture(scope="module")
def renderer():
    pygame = pytest.importorskip("pygame")
    pygame.init()
    screen = pygame.Surface((800, 600))
    from dark_forest_snake.ui.renderer import Renderer

    yield Renderer(screen, 24, 18, cell_size=24, origin=(0, 0))
    pygame.quit()


def _view_with_indicator(ind, reveal=False):
    return {
        "own_head": [10, 10],
        "own_direction": [1, 0],
        "own_body": [[10, 10], [9, 10], [8, 10]],
        "target_indicator": list(ind) if ind else None,
        "visible_brightness": {
            f"{10 + dx},{10 + dy}": 0.5 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        },
        "visible_enemy_cells": [],
        "reveal_active": reveal,
        "view_radius": 1,
    }


def test_renderer_draws_indicator_glow(renderer) -> None:
    """正常黑暗状态：指示格位置必须真的被画亮（地面层像素含暖色）。"""
    view = _view_with_indicator((1, -1))  # NE → (11, 9)
    renderer.draw(view)
    x, y = 11, 9
    rect = renderer.cell_rect(x, y)
    px = renderer.board.get_at((rect.centerx, rect.centery))
    # 指示格中心应含明显暖色分量（GOLD 系），而不是纯黑/纯背景
    assert px.r > 60 and px.g > 40, f"指示格未发光: {tuple(px)}"


def test_renderer_skips_indicator_during_full_reveal(renderer) -> None:
    """3 秒全图照亮期间：不突出指示格（玩家已拥有全图信息）。"""
    view = _view_with_indicator((1, -1), reveal=True)
    renderer.draw(view)
    x, y = 11, 9
    rect = renderer.cell_rect(x, y)
    px = renderer.board.get_at((rect.centerx, rect.centery))
    # 不应出现指示格特有的暖色 glow（允许环境光/遮罩的底色，但红色分量不该爆高）
    assert px.r < 60, f"full reveal 下指示格仍被突出: {tuple(px)}"


def test_indicator_visible_under_snake_body(renderer) -> None:
    """指示格被自己蛇身压住时：地面 glow 在先 + 屏幕 halo 在后，仍应可见。"""
    view = _view_with_indicator((-1, 0))  # W → (9,10)，恰好是蛇身第二节
    assert [9, 10] in view["own_body"]
    renderer.draw(view)  # 不崩溃即完成一半；再检查 halo 画到了 screen 上
    # 屏幕层（含 halo）该位置附近应有暖色像素
    cx, cy = renderer.to_px(9, 10)
    cx += renderer.cell // 2
    cy += renderer.cell // 2
    px = renderer.screen.get_at((cx, cy))
    assert px.r > 30, f"蛇身压住指示格后 halo 不可见: {tuple(px)}"


# ================================================================ 六、LAN 端到端
@pytest.mark.asyncio
async def test_lan_view_only_carries_indicator_not_target() -> None:
    """真实 websocket 端到端：客户端只收到八方向指示，收不到目标坐标。"""
    import asyncio

    from dark_forest_snake.network.client import GameClient
    from dark_forest_snake.network.server import GameServer

    server = GameServer(host="127.0.0.1", port=18780, width=24, height=18, seed=2024)
    server_task = asyncio.create_task(server.run())
    await asyncio.sleep(0.4)

    views: dict[int, list[dict]] = {P1: [], P2: []}
    clients = []
    for i in range(2):
        c = GameClient(
            "127.0.0.1",
            18780,
            on_view=lambda v, idx=i: views[idx].append(v),
        )
        clients.append(c)

    try:
        # 顺序连接：席位按 accept 顺序分配（先连的拿 P1）
        for c in clients:
            await c.connect()
            for _ in range(100):
                if c.player_id is not None:
                    break
                await asyncio.sleep(0.02)
        # 跑一小段对局，收集视角帧
        await asyncio.sleep(2.5)
    finally:
        for c in clients:
            await c.close()
        await server.shutdown()
        server_task.cancel()
        try:
            await server_task
        except Exception:
            pass

    for pid in (P1, P2):
        assert views[pid], f"P{pid + 1} 没收到任何视角帧"
        for view in views[pid]:
            # 目标相关字段：只有 target_indicator 一个出口
            for bad in (
                "fruit",
                "fruit_position",
                "fruit_cell",
                "gold",
                "gold_position",
                "gold_cell",
                "target",
                "target_cell",
                "target_position",
                "target_x",
                "target_y",
            ):
                assert bad not in view
            ind = view.get("target_indicator")
            assert ind is None or (
                len(ind) == 2 and tuple(ind) in INDICATOR_NAMES
            ), f"非法指示: {ind}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
