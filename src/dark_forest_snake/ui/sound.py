"""程序生成音效（无需外部素材）。

用 pygame.mixer + numpy 生成短促的提示音。
没有 numpy 或没有音频设备时静默降级，绝不影响核心玩法。
"""

from __future__ import annotations

import math

import pygame

SAMPLE_RATE = 44100


def _synth(
    freqs: list[float],
    duration: float,
    *,
    volume: float = 0.25,
    decay: float = 6.0,
    wave: str = "sine",
) -> pygame.mixer.Sound | None:
    """合成一个简单的音效。

    freqs 会依次播放（若多个）形成一个短促的滑音/和弦序列。
    """
    try:
        import array

        n = int(SAMPLE_RATE * duration)
        if n <= 0:
            return None
        buf = array.array("h")
        total = len(freqs)
        for i in range(n):
            t = i / SAMPLE_RATE
            seg = min(int(t / duration * total), total - 1)
            f = freqs[seg]
            env = math.exp(-decay * (t / duration))
            v = math.sin(2 * math.pi * f * t)
            if wave == "square":
                v = 1.0 if v > 0 else -1.0
            elif wave == "tri":
                v = 2 / math.pi * math.asin(math.sin(2 * math.pi * f * t))
            s = int(max(-1.0, min(1.0, v * env * volume)) * 32767)
            buf.append(s)
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except Exception:
        return None


class SoundBank:
    """一组游戏音效。加载失败时全部降级为静默。"""

    def __init__(self) -> None:
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self._init()

    def _init(self) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
            self.enabled = True
        except Exception:
            self.enabled = False
            return

        specs = {
            # 吃普通果子：短促上扬
            "eat_sprint": ([660, 880], 0.10, 0.22, 8.0, "sine"),
            "eat_shield": ([520, 700], 0.12, 0.22, 7.0, "tri"),
            "eat_lantern": ([780, 1040], 0.12, 0.22, 7.0, "sine"),
            # 对手吃普通果子：轻微低音提示（避免误以为是自己吃到）
            "eat_remote": ([330, 300], 0.09, 0.10, 8.0, "sine"),
            # 金苹果刷新：低沉警示
            "gold_appear": ([180, 140, 240], 0.5, 0.28, 2.5, "sine"),
            # 获得金苹果：明亮和弦
            "gold_get": ([523, 659, 784, 1046], 0.55, 0.32, 2.0, "sine"),
            # 护盾破裂
            "shield_break": ([420, 180], 0.22, 0.30, 5.0, "square"),
            # 疾跑
            "sprint": ([300, 520], 0.14, 0.18, 6.0, "tri"),
            # 死亡
            "death": ([300, 220, 150, 90], 0.7, 0.30, 2.2, "tri"),
            # 胜利
            "victory": ([523, 659, 784, 1046, 1318], 1.0, 0.30, 1.2, "sine"),
            # 菜单
            "menu": ([440, 550], 0.07, 0.16, 10.0, "sine"),
        }
        for name, (freqs, dur, vol, dec, wave) in specs.items():
            s = _synth(freqs, dur, volume=vol, decay=dec, wave=wave)
            if s is not None:
                self.sounds[name] = s

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        s = self.sounds.get(name)
        if s is not None:
            try:
                s.play()
            except Exception:
                pass

    def play_for_event(self, text: str, *, mine: bool = True) -> None:
        """把公共事件文本映射到音效。

        ``mine=False``（对手触发的事件）时，普通吃果只给轻微提示音，
        避免听起来像自己吃到了果子；金苹果、死亡等重大事件保持原样。
        """
        if "金苹果出现" in text:
            self.play("gold_appear")
        elif "获得了金苹果" in text:
            self.play("gold_get")
        elif "护盾破裂" in text:
            if mine:
                self.play("shield_break")
        elif "疾跑果" in text:
            self.play("eat_sprint" if mine else "eat_remote")
        elif "护盾果" in text:
            self.play("eat_shield" if mine else "eat_remote")
        elif "灯笼果" in text:
            self.play("eat_lantern" if mine else "eat_remote")
        elif "死亡" in text:
            self.play("death")
        elif "获胜" in text:
            self.play("victory")


_shared: SoundBank | None = None


def get_sounds() -> SoundBank:
    global _shared
    if _shared is None:
        _shared = SoundBank()
    return _shared
