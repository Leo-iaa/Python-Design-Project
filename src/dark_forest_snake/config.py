"""集中管理所有游戏参数，禁止 magic number 散落各处。"""

from __future__ import annotations

# ---------------------------------------------------------------- 地图
MAP_WIDTH = 32
MAP_HEIGHT = 24

# ---------------------------------------------------------------- 蛇
INITIAL_SNAKE_LENGTH = 3

# 每 Tick 间隔（秒）。疾跑只改变 Tick 频率，每 Tick 仍然只移动一格。
BASE_MOVE_INTERVAL = 0.18
BOOST_MOVE_INTERVAL = 0.095

# 输入缓冲队列上限。允许同帧连按两键（如 ↑ 再 ←）而不掉头自杀。
MAX_QUEUED_DIRECTIONS = 2

# ---------------------------------------------------------------- 视野 / 光照
NORMAL_VIEW_RADIUS = 5
LANTERN_VIEW_RADIUS = 6

# 环境光亮度区间：蛇头附近局部照明的明暗范围（与目标无关）。
MIN_BRIGHTNESS = 0.22
MAX_BRIGHTNESS = 0.95

# 光照可视半径随亮度衰减的空间半径（渲染用软边，不影响规则）。
LIGHT_DECAY_RADIUS = 5.0

# ---------------------------------------------------------------- 能力
ABILITY_DURATION = 10.0
FULL_REVEAL_DURATION = 3.0

SPRINT_DURATION = ABILITY_DURATION
SHIELD_DURATION = ABILITY_DURATION
LANTERN_DURATION = ABILITY_DURATION

SHIELD_CHARGES = 1

# ---------------------------------------------------------------- 金苹果
GOLD_TRIGGER_MIN = 3
GOLD_TRIGGER_MAX = 6
GOLD_TO_WIN = 3

# ---------------------------------------------------------------- 出生
MIN_SPAWN_DISTANCE = 10  # 两条蛇出生点之间的曼哈顿距离下限

# ---------------------------------------------------------------- 倒计时
COUNTDOWN_DURATION = 3.0

# ---------------------------------------------------------------- 调试
DEBUG = False

# 用于探测"是否存在路径 / 死路"的递归搜索深度上限。
TRAP_SEARCH_MAX_DEPTH = 40
