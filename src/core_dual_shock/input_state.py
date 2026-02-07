"""入力状態管理モジュール.

全チャンネルの生値を状態テーブルとして保持する。
イベント受信時は代入のみで処理負荷を最小化。
"""

from dataclasses import dataclass
from threading import Lock


# ボタン定義
BUTTONS = [
    "triangle",
    "circle",
    "cross",
    "square",
    "L1",
    "R1",
    "L3",
    "R3",
    "dpad_up",
    "dpad_down",
    "dpad_left",
    "dpad_right",
    "select",
    "start",
    "ps",
    "touchpad",
]

# アナログ定義
ANALOG_CHANNELS = [
    "left_x",
    "left_y",
    "right_x",
    "right_y",
    "L2",
    "R2",
]

# ニュートラル値
BUTTON_NEUTRAL = 0
STICK_NEUTRAL = 128
TRIGGER_NEUTRAL = 0


@dataclass
class InputSnapshot:
    """入力状態のスナップショット."""

    buttons: dict[str, int]  # 各 0 or 1
    analog: dict[str, int]  # 各 生値(int)


class InputState:
    """入力状態管理クラス.

    全チャンネルの生値を保持し、スナップショット取得機能を提供する。
    スレッドセーフ実装。
    """

    def __init__(self):
        """全チャンネルをニュートラル値で初期化."""
        self._lock = Lock()
        self._buttons: dict[str, int] = {}
        self._analog: dict[str, int] = {}
        self.reset()

    def update_button(self, name: str, value: int):
        """ボタンの値を更新（代入のみ）.

        Args:
            name: ボタン名
            value: ボタン値 (0 or 1)
        """
        with self._lock:
            self._buttons[name] = value

    def update_analog(self, name: str, value: int):
        """アナログの値を更新（代入のみ）.

        Args:
            name: アナログチャンネル名
            value: 生値 (int)
        """
        with self._lock:
            self._analog[name] = value

    def snapshot(self) -> InputSnapshot:
        """現在の全チャンネルの値をコピーして返す.

        Returns:
            現在の入力状態のスナップショット
        """
        with self._lock:
            return InputSnapshot(
                buttons=self._buttons.copy(),
                analog=self._analog.copy(),
            )

    def reset(self):
        """全チャンネルをニュートラル値にリセット（フェイルセーフ用）."""
        with self._lock:
            # ボタンを初期化
            for button in BUTTONS:
                self._buttons[button] = BUTTON_NEUTRAL

            # アナログを初期化
            for channel in ANALOG_CHANNELS:
                if channel in ("left_x", "left_y", "right_x", "right_y"):
                    # スティックは中立位置
                    self._analog[channel] = STICK_NEUTRAL
                else:
                    # トリガー(L2, R2)は0
                    self._analog[channel] = TRIGGER_NEUTRAL
