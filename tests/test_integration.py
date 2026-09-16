"""阶段 8：完整对局集成测试。

回答"这局游戏能不能从头玩到尾"：
- 三金苹果胜利路径真正走完
- PvP 撞死 / 头对头平局正确终结
- 死亡后重开回到可玩状态
- 相同 seed 完全可复现
- 对外结构无隐藏信息泄漏
- 多局长时间运行稳定

全部使用项目真实接口与真实类型（Cell / Direction / g.state.phase /
g.gold_counts / input_direction / SnakeAI(pid, rng=...)）。
"""

from __future__ import annotations

import random

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.ai.snake_ai import (
    FORBIDDEN_FIELD_NAMES,
    AIPerception,
    SnakeAI,
    perception_from_view,
)
from dark_forest_snake.core.game import P1, P2, PLAYER_IDS, Game
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.state import GamePhase


def _ph(g: Game) -> GamePhase:
    return g.state.phase


def _cells(body: list[tuple[int, int]]) -> list[Cell]:
    return [Cell(x, y) for (x, y) in body]


def _park_snakes(g: Game) -> None:
    """把两条蛇拉到互不相干的安全位，避免辅助操作意外撞死。"""
    g.snakes[P1].body = _cells([(3, 12), (2, 12), (1, 12)])
    g.snakes[P2].body = _cells([(20, 4), (21, 4), (22, 4)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].direction = Direction.LEFT
    for s in g.snakes.values():
        s.alive = True
        s.death_reason = None


def _force_play(g: Game) -> None:
    g.start_match(countdown=0.0)
    g.update(0.0)
    assert _ph(g) in (GamePhase.PLAYING_NORMAL, GamePhase.PLAYING_GOLDEN)


def _give_gold(g: Game, pid: int, count: int) -> None:
    for _ in range(count):
        _park_snakes(g)
        g._on_eat_gold(pid)


# ================================================================ 胜利路径
def test_three_gold_apples_ends_the_match() -> None:
    g = Game(width=24, height=18, seed=11)
    _force_play(g)

    _give_gold(g, P1, 1)
    assert _ph(g) is GamePhase.PLAYING_GOLDEN
    assert g.gold_counts[P1] == 1

    _give_gold(g, P1, 1)
    assert g.gold_counts[P1] == 2

    _give_gold(g, P1, 1)
    assert g.gold_counts[P1] == C.GOLD_TO_WIN
    assert _ph(g) is GamePhase.GAME_OVER
    assert g.winner == P1


def test_gold_progress_tracked_per_player() -> None:
    g = Game(width=24, height=18, seed=12)
    _force_play(g)
    _give_gold(g, P1, 2)
    _give_gold(g, P2, 1)
    assert g.gold_counts[P1] == 2
    assert g.gold_counts[P2] == 1
    assert _ph(g) is GamePhase.PLAYING_GOLDEN
    assert g.winner is None


def test_second_player_can_win_too() -> None:
    g = Game(width=24, height=18, seed=13)
    _force_play(g)
    _give_gold(g, P2, C.GOLD_TO_WIN)
    assert g.winner == P2
    assert _ph(g) is GamePhase.GAME_OVER


# ================================================================ 死亡路径
def test_wall_death_ends_match() -> None:
    g = Game(width=24, height=18, seed=14)
    _force_play(g)
    _park_snakes(g)
    g.snakes[P1].body = _cells([(23, 12), (22, 12), (21, 12)])
    g.snakes[P1].direction = Direction.RIGHT
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert not g.snakes[P1].alive
    assert _ph(g) is GamePhase.GAME_OVER
    assert g.winner == P2


def test_pvp_collision_kills_the_rammer() -> None:
    g = Game(width=24, height=18, seed=15)
    _force_play(g)
    g.snakes[P1].body = _cells([(10, 10), (9, 10), (8, 10)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = _cells([(11, 10), (12, 10), (13, 10), (14, 10)])
    g.snakes[P2].direction = Direction.UP
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert not g.snakes[P1].alive
    assert _ph(g) is GamePhase.GAME_OVER
    assert g.winner == P2


def test_head_to_head_equal_length_is_draw() -> None:
    g = Game(width=24, height=18, seed=16)
    _force_play(g)
    g.snakes[P1].body = _cells([(10, 10), (9, 10), (8, 10)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = _cells([(12, 10), (13, 10), (14, 10)])
    g.snakes[P2].direction = Direction.LEFT
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert not g.snakes[P1].alive
    assert not g.snakes[P2].alive
    assert _ph(g) is GamePhase.DRAW_RESTART


def test_head_to_head_longer_wins() -> None:
    g = Game(width=24, height=18, seed=17)
    _force_play(g)
    g.snakes[P1].body = _cells([(10, 10), (9, 10), (8, 10)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = _cells([(12, 10), (13, 10), (14, 10), (15, 10)])
    g.snakes[P2].direction = Direction.LEFT
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert g.snakes[P1].alive is False
    assert g.snakes[P2].alive is True
    assert _ph(g) is GamePhase.GAME_OVER
    assert g.winner == P2


def test_shield_blocks_one_lethal_hit() -> None:
    g = Game(width=24, height=18, seed=18)
    _force_play(g)
    g.abilities[P1].grant("shield", g.clock)

    g.snakes[P1].body = _cells([(23, 12), (22, 12), (21, 12)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = _cells([(5, 5), (4, 5), (3, 5)])
    g.snakes[P2].direction = Direction.UP
    g.update(C.BASE_MOVE_INTERVAL + 0.01)

    assert g.snakes[P1].alive is True, "第一次致死应被护盾挡住"
    assert not g.abilities[P1].has_shield(g.clock), "护盾应被消耗"
    assert _ph(g) is not GamePhase.GAME_OVER

    g.snakes[P1].body = _cells([(23, 12), (22, 12), (21, 12)])
    g.snakes[P1].direction = Direction.RIGHT
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert not g.snakes[P1].alive
    assert _ph(g) is GamePhase.GAME_OVER


# ================================================================ 重开路径
def test_restart_returns_to_playable_state() -> None:
    g = Game(width=24, height=18, seed=19)
    _force_play(g)
    _give_gold(g, P1, C.GOLD_TO_WIN)
    assert _ph(g) is GamePhase.GAME_OVER

    g.start_match(countdown=0.0)
    g.update(0.0)
    assert _ph(g) in (GamePhase.PLAYING_NORMAL, GamePhase.PLAYING_GOLDEN)
    assert g.winner is None
    assert all(s.alive for s in g.snakes.values())
    assert g.gold_counts[P1] == 0 and g.gold_counts[P2] == 0


def test_draw_restart_resets_both_snakes() -> None:
    g = Game(width=24, height=18, seed=20)
    _force_play(g)
    g.snakes[P1].body = _cells([(10, 10), (9, 10), (8, 10)])
    g.snakes[P1].direction = Direction.RIGHT
    g.snakes[P2].body = _cells([(12, 10), (13, 10), (14, 10)])
    g.snakes[P2].direction = Direction.LEFT
    g.update(C.BASE_MOVE_INTERVAL + 0.01)
    assert _ph(g) is GamePhase.DRAW_RESTART

    g.restart_after_draw()
    g.update(0.0)
    assert all(s.alive for s in g.snakes.values())


# ================================================================ 确定性
def _run_seeded_match(seed: int, steps: int = 400) -> dict:
    g = Game(width=24, height=18, seed=seed)
    g.start_match(countdown=0.0)
    g.update(0.0)

    dirs = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
    fingerprint = []
    for i in range(steps):
        if g.is_over():
            break
        for pid in PLAYER_IDS:
            g.input_direction(pid, dirs[(i // 7 + pid * 2) % 4])
        g.update(C.BASE_MOVE_INTERVAL + 0.001)
        fingerprint.append(
            (
                _ph(g).value,
                tuple(c.as_tuple() for c in g.snakes[P1].body),
                tuple(c.as_tuple() for c in g.snakes[P2].body),
                g.gold_counts[P1],
                g.gold_counts[P2],
            )
        )
    return {"fingerprint": fingerprint, "phase": _ph(g).value, "winner": g.winner}


def test_same_seed_reproduces_identical_match() -> None:
    a = _run_seeded_match(seed=1234)
    b = _run_seeded_match(seed=1234)
    assert a["fingerprint"] == b["fingerprint"], "相同 seed 出现分歧，随机性未完全注入"
    assert a["phase"] == b["phase"]
    assert a["winner"] == b["winner"]


def test_different_seed_diverges() -> None:
    a = _run_seeded_match(seed=1)
    b = _run_seeded_match(seed=2)
    assert a["fingerprint"] != b["fingerprint"], "换 seed 结果不变，说明 seed 没被使用"


# ================================================================ 信息隔离
def test_view_state_never_exposes_hidden_targets() -> None:
    g = Game(width=24, height=18, seed=21)
    _force_play(g)
    forbidden = ("fruit", "gold", "target", "gold_trigger", "normal_eaten", "gold_counts")
    for _ in range(60):
        for pid in PLAYER_IDS:
            v = g.view_for(pid).to_dict()
            for key in forbidden:
                assert key not in v, f"视角泄漏了隐藏字段 {key}"
            assert isinstance(v["visible_brightness"], dict)
            for k in v["visible_brightness"]:
                assert isinstance(k, str), "亮度表 key 必须是字符串坐标"
        g.update(C.BASE_MOVE_INTERVAL + 0.001)


def test_ai_perception_has_no_forbidden_fields() -> None:
    g = Game(width=24, height=18, seed=22)
    _force_play(g)
    for _ in range(40):
        for pid in PLAYER_IDS:
            view = g.view_for(pid)
            p = perception_from_view(view, (g.width, g.height))
            assert isinstance(p, AIPerception)
            for name in FORBIDDEN_FIELD_NAMES:
                assert not hasattr(p, name), f"AI 感知暴露了禁用字段 {name}"
        g.update(C.BASE_MOVE_INTERVAL + 0.001)


def test_ai_decision_is_only_direction_and_sprint() -> None:
    g = Game(width=24, height=18, seed=23)
    _force_play(g)
    ai = SnakeAI(P1, rng=random.Random(5))
    p = perception_from_view(g.view_for(P1), (g.width, g.height))
    d = ai.decide(p)
    assert d.direction is None or isinstance(d.direction, Direction)
    assert isinstance(d.sprint, bool)


# ================================================================ 稳定性
def test_many_full_matches_do_not_crash() -> None:
    finished = 0
    for seed in range(40):
        g = Game(width=20, height=15, seed=seed)
        g.start_match(countdown=0.0)
        g.update(0.0)
        ais = {pid: SnakeAI(pid, rng=random.Random(seed * 10 + pid)) for pid in PLAYER_IDS}

        for _ in range(1500):
            if g.is_over():
                break
            for pid in PLAYER_IDS:
                act = ais[pid].decide(
                    perception_from_view(g.view_for(pid), (g.width, g.height))
                )
                if act.direction is not None:
                    g.input_direction(pid, act.direction)
                g.input_sprint(pid, act.sprint)
            g.update(C.BASE_MOVE_INTERVAL + 0.001)

        assert _ph(g) in (
            GamePhase.PLAYING_NORMAL,
            GamePhase.PLAYING_GOLDEN,
            GamePhase.GAME_OVER,
            GamePhase.DRAW_RESTART,
        ), f"seed={seed} 进入了非法状态 {_ph(g)}"
        if _ph(g) is GamePhase.GAME_OVER:
            finished += 1

    assert finished >= 5, f"40 局里只有 {finished} 局正常分出胜负，AI 可能卡住了"


def test_long_run_keeps_visible_area_bounded() -> None:
    g = Game(width=24, height=18, seed=24)
    _force_play(g)
    for _ in range(1500):
        for pid in PLAYER_IDS:
            g.input_direction(pid, Direction.RIGHT)
        g.update(C.BASE_MOVE_INTERVAL + 0.001)
        if g.is_over():
            g.start_match(countdown=0.0)
            g.update(0.0)

    for pid in PLAYER_IDS:
        v = g.view_for(pid).to_dict()
        max_cells = (C.LANTERN_VIEW_RADIUS * 2 + 1) ** 2
        assert len(v["visible_brightness"]) <= max_cells, (
            f"可见格数 {len(v['visible_brightness'])} 超过灯笼视野上限 {max_cells}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
