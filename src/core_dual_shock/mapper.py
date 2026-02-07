"""正規化・デッドゾーン・デバイス差吸収モジュール.

送信周期のタイミングで呼ばれ、InputSnapshotを統一フォーマットに変換する。
"""

from core_dual_shock.input_state import InputSnapshot
from core_dual_shock.profile_loader import load_all_profiles

PROFILES, _ = load_all_profiles()


class Mapper:
    """デバイスプロファイルに基づいて入力を正規化するクラス."""

    def __init__(self, profile_name: str, deadzone: int = 10):
        """プロファイル名でデバイスプロファイルを選択.

        Args:
            profile_name: デバイスプロファイル名 (例: "DualShock4", "DualSense")
            deadzone: デッドゾーン閾値 (デフォルト: 10)

        Raises:
            ValueError: 未知のプロファイル名が指定された場合
        """
        if profile_name not in PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}")

        self.profile = PROFILES[profile_name]
        self.deadzone = deadzone

    def get_event_mapping(self) -> dict:
        """evdevイベントコード → (チャンネル名, チャンネル種別)のマッピングを返す.

        input_state側でイベントを振り分けるために使う。

        Returns:
            {evdev_code: (channel_name, channel_type), ...}
            channel_type は "button" または "analog"
        """
        mapping = {}

        # ボタンマッピング
        for button_name, button_code in self.profile["buttons"].items():
            mapping[button_code] = (button_name, "button")

        # スティックマッピング
        for stick_name, stick_config in self.profile["sticks"].items():
            mapping[stick_config["code"]] = (stick_name, "analog")

        # トリガーマッピング
        for trigger_name, trigger_config in self.profile["triggers"].items():
            mapping[trigger_config["code"]] = (trigger_name, "analog")

        # 十字キーマッピング（HAT方式の場合）
        if self.profile["dpad_type"] == "hat":
            dpad_config = self.profile["dpad"]
            mapping[dpad_config["hat_x"]] = ("dpad_hat_x", "hat")
            mapping[dpad_config["hat_y"]] = ("dpad_hat_y", "hat")
        else:
            # ボタン方式の場合（将来の拡張用）
            # dpadボタンは既にbuttonsに含まれているはず
            pass

        return mapping

    def normalize(self, snapshot: InputSnapshot) -> InputSnapshot:
        """生値のスナップショットを正規化済みに変換して返す.

        Args:
            snapshot: 生値を含む入力スナップショット

        Returns:
            正規化・デッドゾーン処理済みの入力スナップショット
        """
        # ボタンはそのままコピー（0 or 1なので正規化不要）
        normalized_buttons = snapshot.buttons.copy()

        # アナログ値を正規化
        normalized_analog = {}

        # スティックの正規化 + デッドゾーン処理
        for stick_name, stick_config in self.profile["sticks"].items():
            if stick_name in snapshot.analog:
                raw_value = snapshot.analog[stick_name]
                normalized_value = self._normalize_value(
                    raw_value, stick_config["min"], stick_config["max"]
                )
                # デッドゾーン処理（スティックのみ）
                normalized_value = self._apply_deadzone(normalized_value)
                normalized_analog[stick_name] = normalized_value

        # トリガーの正規化（デッドゾーンなし）
        for trigger_name, trigger_config in self.profile["triggers"].items():
            if trigger_name in snapshot.analog:
                raw_value = snapshot.analog[trigger_name]
                normalized_value = self._normalize_value(
                    raw_value, trigger_config["min"], trigger_config["max"]
                )
                normalized_analog[trigger_name] = normalized_value

        return InputSnapshot(buttons=normalized_buttons, analog=normalized_analog)

    def _normalize_value(self, raw: int, dev_min: int, dev_max: int) -> int:
        """生値を0-255の範囲に正規化.

        Args:
            raw: 生値
            dev_min: デバイスの最小値
            dev_max: デバイスの最大値

        Returns:
            0-255の範囲に正規化された値
        """
        # 線形スケーリング
        if dev_max == dev_min:
            # ゼロ除算を防ぐ
            normalized = 128
        else:
            normalized = int((raw - dev_min) * 255 / (dev_max - dev_min))

        # 0-255の範囲にクランプ
        return max(0, min(255, normalized))

    def _apply_deadzone(self, value: int) -> int:
        """デッドゾーン処理を適用（スティック用）.

        Args:
            value: 正規化済みの値 (0-255)

        Returns:
            デッドゾーン処理済みの値
        """
        CENTER = 128
        if abs(value - CENTER) < self.deadzone:
            return CENTER
        return value
