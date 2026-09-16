# 黑暗森林贪吃蛇 (Dark Forest Snake)

> 双人、黑暗视野、信息不完全、资源争夺、技能、PvP 对抗的贪吃蛇。

地图处于黑暗状态。你看不到完整地图——只有蛇头周围半径 5 格的微光区域
（灰→暖黄渐变，越靠外越暗），以及可见范围最外圈上的一个光点：
它指向目标方向，颜色就是目标果子的颜色，越接近目标越亮。
果子与金苹果进入可见范围时会直接显形。在黑暗中摸索、争夺普通果子获得能力，
等待那枚金苹果出现，或者在黑夜里把对手逼死。

## 胜利条件

1. 先获得 **3 个金苹果**
2. 或使对方死亡

## 核心机制

- **黑暗视野**：正常只能看到蛇头周围半径 5 格，视野之外全黑；
  可见格发出灰→暖黄的渐变微光，越靠外越暗。
- **边缘光点**：可见范围最外圈上有一个光点指向目标方向，
  **颜色即目标果子的颜色**（疾跑青/护盾紫/灯笼蓝/金苹果金），
  并且**越接近目标越亮**。不存在箭头、不存在坐标、不存在小地图——你只能读光。
- **果子显形**：果子与金苹果本身不可见，但一旦进入你的可见范围就会显形——
  彩色圆果按能力分色（青/紫/蓝），金苹果是带果柄、叶子与星芒的金色圆果。
- **普通果子**（场上同时只有 1 个，吃掉立即刷新）
  - 青色 · 疾跑果 → 获得疾跑能力 10 秒（需按住 `Shift` 才加速）
  - 紫色 · 护盾果 → 抵挡 1 次致死撞击，10 秒有效
  - 蓝色 · 灯笼果 → 视野半径 5 → 6，持续 10 秒
- **隐藏金苹果**：每轮开始时随机一个 3~6 的隐藏阈值（绝不暴露给玩家）。
  全场累计吃掉的普通果子数达到阈值，进入金苹果阶段——普通果子消失，
  地图上只剩那个**同样不可见**的金苹果。
- **3 秒全图视野**：吃到金苹果的人独享 3 秒全图照亮，可以看到对手位置与身体。
  另一方只会收到"对方获得了金苹果"的通知。
- **PvP 碰撞**：撞墙 / 撞自己 / 撞对方身体都会死；头对头相遇时**更长的蛇获胜**，
  等长则双方同死、整局重开。护盾可以挡下一次致死（回弹不前进）。

## 环境要求

- Windows / macOS / Linux
- [uv](https://docs.astral.sh/uv/)（唯一支持的环境管理器）
- Python 3.12（由 uv 自动管理，无需手动安装）

## 安装与运行

```bash
# 同步环境（uv 会自动准备好 Python 3.12 与全部依赖）
uv sync

# 启动游戏（进入主菜单）
uv run python -m dark_forest_snake
```

启动自检（不打开窗口，检查字体 / 引擎 / 音效）：

```bash
uv run python -m dark_forest_snake --headless-check
```

### 操作方式

| 按键 | 作用 |
| --- | --- |
| `W` `A` `S` `D` 或 方向键 | 转向 |
| `Shift`（按住） | 疾跑（需先吃到疾跑果） |
| `Esc` | 返回菜单 / 退出 |

### 单机模式（人对 AI）

```bash
uv run python -m dark_forest_snake --mode solo
```

或在主菜单选择「单人对战」。

## LAN 双人联机

一台机器做 Host，另一台做 Client，**权威服务器在 Host 上**：
客户端只发送方向输入，收到的永远是裁剪后的个人视角，不可能拿到隐藏目标坐标。

### Host（开房间的一方）

```bash
uv run python -m dark_forest_snake --mode lan_host
```

启动后界面会显示 `局域网 IP: xxx.xxx.xxx.xxx · 端口 8765`，把这个 IP 告诉对方。
默认端口 `8765`，可用 `--port` 修改：

```bash
uv run python -m dark_forest_snake --mode lan_host --port 9000
```

### Client（加入的一方）

主菜单选择「加入局域网」，输入 Host 的 IP（端口需与 Host 一致）。

### 防火墙提示

- **Windows**：首次做 Host 时，防火墙会弹出"是否允许 Python 访问网络"，
  请勾选**专用网络**并允许。若对方连不上，在
  `设置 → 网络和 Internet → Windows 防火墙 → 允许应用通过防火墙`
  中放行 Python，或手动放行 TCP 端口 8765（或你自定义的端口）。
- 两台机器必须在**同一局域网**（同一路由器 / 同一网段）。
- Client 连接超时会提示"请检查 IP 与防火墙"——先确认 Host 已启动且双方能互 ping。

### LAN 链路自测（无图形界面）

```bash
uv run python -m dark_forest_snake.tools.lan_selftest
```

会拉起一个本地服务器 + 两个模拟客户端，验证加入、状态同步、断线处理全链路。

## 项目结构

```
src/dark_forest_snake/
├── config.py            # 全部数值配置（地图、亮度、能力时长、金苹果阈值……）
├── core/                # 纯规则引擎：不依赖 pygame，单机与服务器共用
│   ├── geometry.py      #   Cell / Direction
│   ├── snake.py         #   蛇：方向队列、移动、成长
│   ├── collision.py     #   同步 Tick 碰撞判定（确定性优先级 R1~R5）
│   ├── fruit.py         #   普通果子与金苹果生成
│   ├── abilities.py     #   疾跑 / 护盾 / 灯笼能力与倒计时
│   ├── indicator.py     #   八方向目标指示格（方向导航的唯一依据）
│   ├── visibility.py    #   视野裁剪与环境光
│   ├── state.py         #   游戏阶段状态机
│   ├── clock.py         #   逻辑时钟与能力过期集合
│   └── game.py          #   Game 主引擎：Tick、进食、金苹果循环、视角生成
├── ai/snake_ai.py       # 信息受限 AI（只读玩家可见信息，禁止作弊）
├── network/             # LAN：权威服务器 + 2 客户端
│   ├── protocol.py      #   消息协议与客户端字段白名单
│   ├── room.py          #   房间与席位
│   ├── server.py        #   权威服务器
│   └── client.py        #   客户端（不运行引擎，只发输入收视角）
├── ui/                  # pygame-ce 渲染层
│   ├── renderer.py      #   地图 / 蛇 / 黑暗 / 亮度 / 光照
│   ├── hud.py           #   金苹果进度、能力倒计时、事件提示
│   ├── menu.py          #   菜单 / 倒计时 / 结算界面
│   ├── theme.py         #   配色与中文字体（tofu 检测）
│   ├── sound.py         #   程序生成音效（无外部素材）
│   └── input.py         #   键盘输入
└── main.py              # 顶层应用状态机（菜单 / 单机 / LAN）

tests/                   # 235 个测试：引擎 / 果子 / 能力 / 指示格 / 金苹果 /
                         # AI / 网络 / UI / 集成 / 回归
```

## 开发

```bash
uv run pytest              # 运行全部 235 个测试
uv run pytest -q           # 快速回归
uv run pytest tests/test_integration.py   # 完整对局集成测试
```

调试视图（显示隐藏信息，仅开发用）：

```bash
uv run python -m dark_forest_snake --mode solo --debug
```

### 环境约束（重要）

- 所有 Python 环境与命令**只用 uv**：`uv sync` / `uv run`，禁止 pip / venv / conda。
- 依赖锁定在 `uv.lock`，Python 版本固定在 `.python-version`（3.12）。
- 随机性全部注入 `random.Random(seed)`：相同 seed + 相同输入 → 逐帧一致，可复现 bug。
