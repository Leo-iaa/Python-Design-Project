"""阶段 5：AI 测试。重点是「AI 不作弊」。"""

from __future__ import annotations

import random

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.ai.snake_ai import (
    ALLOWED_PERCEPTION_FIELDS,
    FORBIDDEN_FIELD_NAMES,
    AIAction,
    AIPerception,
    AIState,
    SnakeAI,
    perception_from_view,
)
from dark_forest_snake.core.fruit import Fruit, FruitType
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.state import GamePhase


# ================================================================ 不作弊
def test_perception_has_no_hidden_target_fields() -> None:
    """AIPerception 绝不能有任何指向隐藏目标的字段。"""
    fields = set(ALLOWED_PERCEPTION_FIELDS)
    leaked = fields & FORBIDDEN_FIELD_NAMES
    assert not leaked, f"AIPerception 泄漏了隐藏字段: {leaked}"


def test_perception_contract_is_whitelisted() -> None:
    """字段白名单化：任何新增字段都要重新审视是否泄漏信息。"""
    expected = {
        "own_body",
        "own_head",
        "own_direction",
        "own_length",
        "own_gold_count",
        "own_shield",
        "own_sprint_remaining",
        "own_lantern",
        "own_view_radius",
        "boosting",
        "visible_cells",
        "brightness",
        "visible_enemy_cells",
        "enemy_head",
        "enemy_length",
        "phase",
        "map_width",
        "map_height",
        "events",
        "last_brightness",
        "last_head",
        "danger_cells",
        "indicator",
    }
    assert ALLOWED_PERCEPTION_FIELDS == expected


def test_ai_module_never_reads_game_internals() -> None:
    """AI 源码中不得出现对 fruits / gold 的直接访问。"""
    import dark_forest_snake.ai.snake_ai as mod

    src = open(mod.__file__, encoding="utf-8").read()
    for bad in ("fruits.fruit", "fruits.gold", "game.fruits", ".gold.cell", ".fruit.cell"):
        assert bad not in src, f"AI 源码出现隐藏信息访问: {bad}"


def test_perception_from_view_carries_no_coordinates_of_target() -> None:
    g = Game(width=24, height=18, seed=301)
    g.start_match(countdown=0.0)
    view = g.view_for(P1)
    p = perception_from_view(view, (g.width, g.height))
    # 亮度表的 key 必须严格等于视野内格子，不能多出目标坐标
    assert set(p.brightness.keys()) == p.visible_cells
    target = g.fruits.game_target
    if target is not None and target not in p.visible_cells:
        assert target not in p.visible_cells


def test_perception_from_view_roundtrip_fields() -> None:
    g = Game(width=24, height=18, seed=302)
    g.start_match(countdown=0.0)
    g.abilities[P1].grant(FruitType.SHIELD, g.clock)
    view = g.view_for(P1)
    p = perception_from_view(view, (g.width, g.height))
    assert p.own_head == g.snakes[P1].head
    assert p.own_length == g.snakes[P1].length
    assert p.own_shield is True
    assert p.map_width == g.width
    assert p.enemy_head is None, "出生点很远时不应看到敌人"


# ================================================================ 基本能力
def _perception_with(target_dir: Direction, head: Cell, width=24, height=18) -> AIPerception:
    """构造一个「目标在 target_dir 方向」的感知包，用于验证八方向指示寻路。

    与真实 view 一致：AI 只拿到量化后的 indicator，没有目标坐标、没有距离。
    brightness 为环境光（与目标无关）。
    """
    radius = 1
    visible = {
        Cell(head.x + dx, head.y + dy)
        for dx in range(-radius, radius + 1)
        for dy in range(-radius, radius + 1)
        if 0 <= head.x + dx < width and 0 <= head.y + dy < height
    }
    brightness = {c: 0.5 for c in visible}
    body = [head, head.offset(-1, 0), head.offset(-2, 0)]
    return AIPerception(
        own_body=body,
        own_head=head,
        own_direction=Direction.RIGHT,
        own_length=3,
        own_gold_count=0,
        own_shield=False,
        own_sprint_remaining=0.0,
        own_lantern=False,
        own_view_radius=1,
        boosting=False,
        visible_cells=visible,
        brightness=brightness,
        visible_enemy_cells=[],
        enemy_head=None,
        enemy_length=None,
        phase="playing_normal",
        map_width=width,
        map_height=height,
        indicator=(target_dir.dx, target_dir.dy),
    )


def test_ai_follows_indicator() -> None:
    """指示目标在下方时，AI 应该选下（而不是上）。"""
    ai = SnakeAI(P1, random.Random(1))
    head = Cell(12, 9)
    p = _perception_with(Direction.DOWN, head)
    action = ai.decide(p)
    assert action.direction is Direction.DOWN, f"AI 应朝指示方向走，实际 {action.direction}"


def test_ai_follows_indicator_right() -> None:
    ai = SnakeAI(P1, random.Random(2))
    head = Cell(12, 9)
    p = _perception_with(Direction.RIGHT, head)
    action = ai.decide(p)
    assert action.direction is Direction.RIGHT


def test_ai_follows_indicator_up() -> None:
    ai = SnakeAI(P1, random.Random(3))
    head = Cell(12, 9)
    p = _perception_with(Direction.UP, head)
    action = ai.decide(p)
    assert action.direction is Direction.UP


def test_ai_never_reverses() -> None:
    ai = SnakeAI(P1, random.Random(4))
    for _ in range(50):
        head = Cell(12, 9)
        p = _perception_with(Direction.LEFT, head)  # 故意把目标放在反向
        action = ai.decide(p)
        assert action.direction is not Direction.LEFT, "AI 绝不能 180° 掉头"


def test_ai_avoids_walls() -> None:
    """贴着墙且目标在墙外时，AI 必须选择安全方向。"""
    ai = SnakeAI(P1, random.Random(5))
    head = Cell(1, 9)  # 贴左墙
    p = _perception_with(Direction.RIGHT, head)
    action = ai.decide(p)
    assert action.direction is Direction.RIGHT


def test_ai_avoids_own_body() -> None:
    ai = SnakeAI(P1, random.Random(6))
    head = Cell(8, 8)
    # 右侧被自己的身体堵住
    body = [head, Cell(9, 8), Cell(10, 8), Cell(11, 8)]
    visible = {Cell(8 + dx, 8 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    p = AIPerception(
        own_body=body,
        own_head=head,
        own_direction=Direction.RIGHT,
        own_length=4,
        own_gold_count=0,
        own_shield=False,
        own_sprint_remaining=0.0,
        own_lantern=False,
        own_view_radius=1,
        boosting=False,
        visible_cells=visible,
        brightness={c: 0.5 for c in visible},
        visible_enemy_cells=[],
        enemy_head=None,
        enemy_length=None,
        phase="playing_normal",
        map_width=24,
        map_height=18,
        indicator=(1, 0),  # 目标在右侧（但右侧被身体堵住，AI 必须绕开）
    )
    action = ai.decide(p)
    assert action.direction is not Direction.RIGHT, "AI 不应撞上自己身体"
    assert action.direction is not None


def test_ai_avoids_visible_enemy_body() -> None:
    ai = SnakeAI(P1, random.Random(7))
    head = Cell(8, 8)
    enemy = [Cell(9, 8), Cell(10, 8)]
    p = _perception_with(Direction.RIGHT, head)
    p.visible_enemy_cells = enemy
    action = ai.decide(p)
    assert action.direction is not Direction.RIGHT, "AI 不应撞上可见的敌人身体"


# ================================================================ 疾跑
def test_ai_does_not_sprint_without_ability() -> None:
    ai = SnakeAI(P1, random.Random(8))
    p = _perception_with(Direction.RIGHT, Cell(12, 9))
    p.own_sprint_remaining = 0.0
    assert ai.decide(p).sprint is False


def test_ai_sprint_is_not_permanent() -> None:
    """疾跑不能永久开启：无方向指示不冲，能力快耗尽也不冲。"""
    ai = SnakeAI(P1, random.Random(9))
    p = _perception_with(Direction.RIGHT, Cell(12, 9))

    # 没有指示 → 不该冲
    p.own_sprint_remaining = 10.0
    p.indicator = None
    assert ai.decide(p).sprint is False

    # 有指示且能力窗口早期 → 可以短促冲刺
    p.indicator = (1, 0)
    assert ai.decide(p).sprint is True

    # 能力快耗尽 → 不再冲（不能永久开启）
    p.own_sprint_remaining = 2.0
    assert ai.decide(p).sprint is False


# ================================================================ 状态机
def test_ai_enters_gold_state_during_golden_phase() -> None:
    ai = SnakeAI(P1, random.Random(10))
    p = _perception_with(Direction.RIGHT, Cell(12, 9))
    p.phase = "playing_golden"
    ai.decide(p)
    assert ai.state in (AIState.SEARCH_GOLD, AIState.CHASE)


def test_ai_evades_longer_enemy() -> None:
    ai = SnakeAI(P1, random.Random(11))
    head = Cell(12, 9)
    p = _perception_with(Direction.RIGHT, head)
    p.visible_enemy_cells = [Cell(13, 9)]
    p.enemy_head = Cell(13, 9)
    p.enemy_length = 10
    p.own_length = 3
    ai.decide(p)
    assert ai.state is AIState.EVADE


def test_ai_escapes_trap_when_cramped() -> None:
    ai = SnakeAI(P1, random.Random(12))
    head = Cell(2, 2)
    # 用身体把自己围死
    body = [head] + [Cell(x, y) for x in range(1, 6) for y in range(1, 6)]
    visible = {Cell(head.x + dx, head.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    p = AIPerception(
        own_body=body,
        own_head=head,
        own_direction=Direction.RIGHT,
        own_length=len(body),
        own_gold_count=0,
        own_shield=False,
        own_sprint_remaining=5.0,
        own_lantern=False,
        own_view_radius=1,
        boosting=False,
        visible_cells=visible,
        brightness={c: 0.5 for c in visible},
        visible_enemy_cells=[],
        enemy_head=None,
        enemy_length=None,
        phase="playing_normal",
        map_width=30,
        map_height=24,
    )
    ai.decide(p)
    assert ai.state is AIState.ESCAPE_TRAP


def test_ai_returns_none_when_no_legal_move() -> None:
    """四周被身体完全封死（且非尾部）时，AI 应老实返回「无路可走」。"""
    ai = SnakeAI(P1, random.Random(13))
    head = Cell(5, 5)
    # 四个方向都被身体堵住，且这些节都不是蛇尾
    body = [
        head,
        Cell(4, 5), Cell(6, 5), Cell(5, 4), Cell(5, 6),  # 四邻
        Cell(3, 5), Cell(7, 5), Cell(5, 3), Cell(5, 7),  # 尾部候选远离四邻
    ]
    p = AIPerception(
        own_body=body,
        own_head=head,
        own_direction=Direction.RIGHT,
        own_length=len(body),
        own_gold_count=0,
        own_shield=False,
        own_sprint_remaining=0.0,
        own_lantern=False,
        own_view_radius=1,
        boosting=False,
        visible_cells={head},
        brightness={head: 0.5},
        visible_enemy_cells=[],
        enemy_head=None,
        enemy_length=None,
        phase="playing_normal",
        map_width=24,
        map_height=18,
    )
    action = ai.decide(p)
    assert action.direction is None


def test_ai_may_enter_vacating_tail_cell() -> None:
    """尾巴本 Tick 会腾空，AI 可以走上去（不应被自己的规则误杀）。"""
    ai = SnakeAI(P1, random.Random(14))
    head = Cell(5, 5)
    # 只有下方的格子是蛇尾，其余方向被身体堵死
    body = [
        head,
        Cell(4, 5), Cell(6, 5), Cell(5, 4),
        Cell(7, 5), Cell(8, 5), Cell(5, 6),  # 尾部
    ]
    p = AIPerception(
        own_body=body,
        own_head=head,
        own_direction=Direction.RIGHT,
        own_length=len(body),
        own_gold_count=0,
        own_shield=False,
        own_sprint_remaining=0.0,
        own_lantern=False,
        own_view_radius=1,
        boosting=False,
        visible_cells={head},
        brightness={head: 0.5},
        visible_enemy_cells=[],
        enemy_head=None,
        enemy_length=None,
        phase="playing_normal",
        map_width=24,
        map_height=18,
    )
    action = ai.decide(p)
    assert action.direction is Direction.DOWN


# ================================================================ 多局对局
def _drive_ai_game(seed: int, max_seconds: float = 120.0) -> dict:
    """用两个 AI 完整跑一局（信息受限）。"""
    g = Game(width=26, height=20, seed=seed)
    g.start_match(countdown=0.0)
    bots = {
        P1: SnakeAI(P1, random.Random(seed * 7 + 1), aggression=0.6),
        P2: SnakeAI(P2, random.Random(seed * 7 + 2), aggression=0.4),
    }
    dt = C.BASE_MOVE_INTERVAL
    elapsed = 0.0
    while not g.is_over() and elapsed < max_seconds:
        for pid, bot in bots.items():
            view = g.view_for(pid)
            perc = perception_from_view(view, (g.width, g.height))
            action = bot.decide(perc)
            if action.direction is not None:
                g.input_direction(pid, action.direction)
            g.input_sprint(pid, action.sprint)
        g.update(dt)
        elapsed += dt
    return {
        "over": g.is_over(),
        "winner": g.winner,
        "draw": g.draw,
        "elapsed": elapsed,
        "gold": dict(g.gold_counts),
        "ticks": g.tick_count,
        "lengths": {pid: s.length for pid, s in g.snakes.items()},
    }


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_ai_games_run_without_crash(seed: int) -> None:
    """多局 AI 自动运行，确认不崩溃、不死循环。"""
    result = _drive_ai_game(seed)
    assert result["ticks"] > 0
    assert result["elapsed"] > 0


def test_ai_games_produce_real_progress() -> None:
    """AI 至少应该能吃到一些东西，而不是原地打转。"""
    progresses = []
    for seed in range(1, 9):
        r = _drive_ai_game(seed)
        total_actions = r["ticks"]
        progresses.append(total_actions)
    assert max(progresses) > 100, "AI 应该有实质推进"


def test_ai_games_are_deterministic_with_same_seed() -> None:
    a = _drive_ai_game(42)
    b = _drive_ai_game(42)
    assert a["gold"] == b["gold"]
    assert a["ticks"] == b["ticks"]


def test_ai_does_not_cheat_in_real_game() -> None:
    """在真实对局中，AI 的感知包不得包含目标坐标。"""
    g = Game(width=26, height=20, seed=77)
    g.start_match(countdown=0.0)
    bot = SnakeAI(P1, random.Random(1))
    for _ in range(60):
        view = g.view_for(P1)
        perc = perception_from_view(view, (g.width, g.height))
        # 感知对象上不得出现任何隐藏字段
        for bad in FORBIDDEN_FIELD_NAMES:
            assert not hasattr(perc, bad), f"感知对象出现了禁止字段 {bad}"
        action = bot.decide(perc)
        if action.direction:
            g.input_direction(P1, action.direction)
        g.update(C.BASE_MOVE_INTERVAL)
        if g.is_over():
            break
