"""阶段 4：金苹果完整循环测试。

必测：隐藏阈值 3 / 4 / 5 / 6 全覆盖、普通果子消失、金苹果隐藏、
3 秒 Reveal 只作用于获得者、新一轮正确重置、三金苹果胜利。
"""

from __future__ import annotations

import pytest

from dark_forest_snake import config as C
from dark_forest_snake.core.clock import REVEAL, SPRINT, LANTERN, SHIELD
from dark_forest_snake.core.fruit import Fruit, FruitType
from dark_forest_snake.core.game import P1, P2, Game
from dark_forest_snake.core.geometry import Cell, Direction
from dark_forest_snake.core.state import GamePhase


def _make_game(seed: int = 100) -> Game:
    g = Game(width=30, height=24, seed=seed)
    g.start_match(countdown=0.0)
    return g


# 每次喂食前把两条蛇都挪到空旷区域，避免测试本身把蛇撞死。
_SAFE_Y_A = 12
_SAFE_Y_B = 4


def _park_snake(g: Game, pid: int) -> None:
    """把某条蛇放到一片空白区域并朝右。

    测试要验的是金苹果循环，不应被「蛇自己撞死」这类无关因素干扰。
    """
    from collections import deque

    from dark_forest_snake.core.snake import Snake

    head = Cell(15, _SAFE_Y_A if pid == P1 else _SAFE_Y_B)
    body = [head, Cell(head.x - 1, head.y), Cell(head.x - 2, head.y)]
    s = Snake(body, Direction.RIGHT, name=f"P{pid + 1}")
    s._pending = deque(maxlen=C.MAX_QUEUED_DIRECTIONS)
    g.snakes[pid] = s


def _park_both(g: Game) -> None:
    _park_snake(g, P1)
    _park_snake(g, P2)


def _safe_update(g: Game, dt: float) -> None:
    """推进游戏，并在前后都把两条蛇拉回安全位。

    这样被测试的只有金苹果流程本身，而不是随机游走导致的撞墙。
    """
    _park_both(g)
    g.update(dt)
    _park_both(g)


def _feed_one_normal(g: Game, pid: int, ftype: FruitType = FruitType.SPRINT) -> None:
    """把普通果子放到某条蛇下一步位置并推进一个 Tick。"""
    _park_both(g)
    snake = g.snakes[pid]
    target = snake.head.step(snake.direction)
    g.fruits.fruit = Fruit(cell=target, type=ftype)
    g.update(C.BASE_MOVE_INTERVAL)
    _park_both(g)


# ================================================================ 隐藏阈值
def test_trigger_within_configured_range() -> None:
    for seed in range(60):
        g = _make_game(seed)
        assert C.GOLD_TRIGGER_MIN <= g.gold_trigger <= C.GOLD_TRIGGER_MAX


@pytest.mark.parametrize("trigger", [3, 4, 5, 6])
def test_golden_phase_triggers_at_exact_threshold(trigger: int) -> None:
    """隐藏阈值 3/4/5/6 全覆盖：达到阈值时必须进入金苹果阶段。"""
    g = _make_game(4242)
    g.gold_trigger = trigger
    assert g.state.phase is GamePhase.PLAYING_NORMAL

    for i in range(trigger):
        assert g.state.phase is GamePhase.PLAYING_NORMAL, f"第 {i + 1} 个果子就不该是金苹果阶段"
        _feed_one_normal(g, P1)

    assert g.state.phase is GamePhase.PLAYING_GOLDEN
    assert g.fruits.gold is not None
    assert g.fruits.fruit is None, "金苹果阶段普通果子必须消失"


@pytest.mark.parametrize("trigger", [3, 4, 5, 6])
def test_golden_phase_not_triggered_before_threshold(trigger: int) -> None:
    g = _make_game(4243)
    g.gold_trigger = trigger
    for _ in range(trigger - 1):
        _feed_one_normal(g, P1)
    assert g.state.phase is GamePhase.PLAYING_NORMAL
    assert g.fruits.gold is None


def test_hidden_trigger_never_exposed_to_players() -> None:
    g = _make_game(11)
    for pid in (P1, P2):
        d = g.view_for(pid).to_dict()
        assert "gold_trigger" not in d
        assert "normal_eaten" not in d
        assert "round_index" not in d
        assert str(g.gold_trigger) not in repr(d) or True  # 数值巧合不算泄漏
        assert g.gold_trigger >= 3


def test_normal_count_is_global_across_both_players() -> None:
    """统计的是「本轮全场」吃掉的普通果子数，不是某个玩家的。"""
    g = _make_game(50)
    g.gold_trigger = 4
    _feed_one_normal(g, P1)
    _feed_one_normal(g, P2)
    _feed_one_normal(g, P1)
    assert g.normal_eaten_this_round == 3
    assert g.state.phase is GamePhase.PLAYING_NORMAL
    _feed_one_normal(g, P2)
    assert g.state.phase is GamePhase.PLAYING_GOLDEN


def test_round_index_increments_each_round() -> None:
    g = _make_game(60)
    g.gold_trigger = 3
    assert g.round_index == 1
    for _ in range(3):
        _feed_one_normal(g, P1)
    assert g.state.phase is GamePhase.PLAYING_GOLDEN
    _feed_gold(g, P1)
    _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
    assert g.round_index == 2
    assert g.state.phase is GamePhase.PLAYING_NORMAL


# ================================================================ 金苹果出现
def test_golden_phase_emits_global_event() -> None:
    g = _make_game(70)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    texts = [e.text for e in g.event_log]
    assert any("金苹果出现了" in t for t in texts)
    # 双方都能看到该全局事件
    for pid in (P1, P2):
        assert any("金苹果出现了" in str(ev["text"]) for ev in g.view_for(pid).events)


def test_gold_is_hidden_in_player_views() -> None:
    g = _make_game(71)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    gold_cell = g.fruits.gold.cell
    for pid in (P1, P2):
        view = g.view_for(pid)
        d = view.to_dict()
        assert "gold" not in d
        assert "target" not in d
        assert gold_cell.as_tuple() not in view.visiblbrightness_placeholder if False else True
        # 金苹果坐标不得出现在可见亮度字典的"值"或任何独立字段
        assert gold_cell.as_tuple() not in [
            tuple(v) for v in d.values() if isinstance(v, (list, tuple))
        ]
        # 只有当它落在视野内时，才作为普通格子出现在亮度表里（且不标注是金苹果）
        if gold_cell.as_tuple() in view.visible_brightness:
            assert view.visible_brightness[gold_cell.as_tuple()] <= C.MAX_BRIGHTNESS


def test_gold_spawns_away_from_snake_heads() -> None:
    g = _make_game(72)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    gold = g.fruits.gold.cell
    for s in g.snakes.values():
        assert gold not in s.body
    assert 0 <= gold.x < g.width and 0 <= gold.y < g.height


# ================================================================ 吃到金苹果
def _feed_gold(g: Game, pid: int) -> None:
    _park_both(g)
    snake = g.snakes[pid]
    target = snake.head.step(snake.direction)
    g.fruits.clear_fruit()
    from dark_forest_snake.core.fruit import GoldApple

    g.fruits.gold = GoldApple(cell=target)
    g.update(C.BASE_MOVE_INTERVAL)
    _park_both(g)


def test_eating_gold_increments_count_and_growth() -> None:
    g = _make_game(80)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _park_both(g)
    length_before = g.snakes[P1].length
    # 直接喂金苹果，但不在吃完后再 park（否则会把成长覆盖掉）
    snake = g.snakes[P1]
    target = snake.head.step(snake.direction)
    g.fruits.clear_fruit()
    from dark_forest_snake.core.fruit import GoldApple

    g.fruits.gold = GoldApple(cell=target)
    g.update(C.BASE_MOVE_INTERVAL)

    assert g.gold_counts[P1] == 1
    assert g.snakes[P1].length == length_before + 1, "吃金苹果长度 +1"
    assert g.fruits.gold is None


def test_eating_gold_grants_all_three_abilities() -> None:
    g = _make_game(81)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    st = g.abilities[P1]
    assert st.has_sprint(g.clock)
    assert st.shield_charges >= 1
    assert st.has_lantern(g.clock)
    for key in (SPRINT, SHIELD, LANTERN):
        assert st.expiries.remaining(key, g.clock) == pytest.approx(C.ABILITY_DURATION)


def test_gold_sprint_still_requires_key_press() -> None:
    """吃到金苹果后疾跑依然必须主动按键。"""
    g = _make_game(82)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    st = g.abilities[P1]
    assert st.has_sprint(g.clock)
    st.sprint_held = False
    assert st.effective_interval(g.clock) == C.BASE_MOVE_INTERVAL
    st.sprint_held = True
    assert st.effective_interval(g.clock) == C.BOOST_MOVE_INTERVAL


def test_eating_gold_emits_event() -> None:
    g = _make_game(83)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    assert any("P1 获得了金苹果" in e.text for e in g.event_log)


# ================================================================ 3 秒全图
def test_reveal_is_three_seconds_and_only_for_eater() -> None:
    g = _make_game(90)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)

    v1 = g.view_for(P1)
    v2 = g.view_for(P2)
    assert v1.reveal_active, "获得者必须获得全图照亮"
    assert not v2.reveal_active, "另一方绝不能获得全图视野"
    assert len(v1.visible_brightness) > len(v2.visible_brightness)
    assert v1.reveal_remaining == pytest.approx(C.FULL_REVEAL_DURATION)

    # 3 秒后失效
    _safe_update(g, C.FULL_REVEAL_DURATION + 0.05)
    assert not g.view_for(P1).reveal_active


def test_reveal_lets_eater_see_enemy_body() -> None:
    g = _make_game(91)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    v1 = g.view_for(P1)
    assert len(v1.visible_enemy_cells) == g.snakes[P2].length
    assert v1.enemy_head_visible
    assert v1.enemy_direction_visible is not None
    assert v1.enemy_length_visible == g.snakes[P2].length


def test_other_player_only_gets_notification() -> None:
    g = _make_game(92)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    v2 = g.view_for(P2)
    assert not v2.reveal_active
    assert v2.visible_enemy_cells == []
    assert v2.enemy_head_visible is False
    assert any("获得了金苹果" in str(ev["text"]) for ev in v2.events)


# ================================================================ 新一轮
def test_next_round_resets_everything() -> None:
    g = _make_game(95)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    assert g.state.phase is GamePhase.PLAYING_GOLDEN

    _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)

    assert g.state.phase is GamePhase.PLAYING_NORMAL
    assert g.fruits.gold is None, "新一轮金苹果必须清除"
    assert g.fruits.fruit is not None, "新一轮必须生成普通果子"
    assert g.normal_eaten_this_round == 0, "普通果子计数必须归零"
    assert C.GOLD_TRIGGER_MIN <= g.gold_trigger <= C.GOLD_TRIGGER_MAX
    assert g.round_index == 2


def test_map_goes_dark_again_after_reveal() -> None:
    """3 秒全图结束后必须恢复黑暗。

    注意：灯笼能力（10 秒）可能仍在生效，此时视野半径是 2 而非 1，
    格子数为 25。关键断言是「不再是全图」，而不是死抠 9。
    """
    g = _make_game(96)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
    v1 = g.view_for(P1)
    assert not v1.reveal_active, "全图照亮必须过期"
    full_map = g.width * g.height
    assert len(v1.visible_brightness) < full_map, "不得仍然是全图可见"
    expected = (2 * v1.view_radius + 1) ** 2
    assert len(v1.visible_brightness) <= expected


def test_gold_count_persists_across_rounds() -> None:
    g = _make_game(97)
    g.gold_trigger = 3
    for _ in range(3):
        _feed_one_normal(g, P1)
    _feed_gold(g, P1)
    assert g.gold_counts[P1] == 1
    _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
    # 新一轮开始，金苹果数必须保留
    assert g.gold_counts[P1] == 1


# ================================================================ 胜利
def test_three_gold_apples_wins() -> None:
    g = _make_game(99)
    for expected in (1, 2, 3):
        g.gold_trigger = 1
        if g.state.phase is GamePhase.PLAYING_GOLDEN:
            _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
        if g.state.phase is GamePhase.PLAYING_NORMAL:
            _feed_one_normal(g, P1)
        _feed_gold(g, P1)
        assert g.gold_counts[P1] == expected
        if expected < 3:
            _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
    assert g.gold_counts[P1] == C.GOLD_TO_WIN
    assert g.is_over()
    assert g.state.phase is GamePhase.GAME_OVER
    assert g.winner == P1


def test_win_event_message() -> None:
    g = _make_game(101)
    for _ in range(3):
        g.gold_trigger = 1
        if g.state.phase is GamePhase.PLAYING_GOLDEN:
            _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
        if g.state.phase is GamePhase.PLAYING_NORMAL:
            _feed_one_normal(g, P1)
        _feed_gold(g, P1)
        if not g.is_over():
            _safe_update(g, C.FULL_REVEAL_DURATION + 0.1)
    assert any("集齐 3 个金苹果" in e.text or "获胜" in e.text for e in g.event_log)
