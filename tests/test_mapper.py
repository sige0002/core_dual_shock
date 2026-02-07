"""Mapperクラスの単体テスト."""

import pytest
from evdev import ecodes

from core_dual_shock.input_state import InputSnapshot
from core_dual_shock.mapper import Mapper


class TestMapperInitialization:
    """Mapperの初期化テスト."""

    def test_initialize_with_dualshock4_profile(self):
        """DualShock4プロファイルでMapper初期化できること."""
        mapper = Mapper("DualShock4")
        assert mapper.profile is not None
        assert mapper.deadzone == 10  # デフォルト値

    def test_initialize_with_dualsense_profile(self):
        """DualSenseプロファイルでMapper初期化できること."""
        mapper = Mapper("DualSense")
        assert mapper.profile is not None
        assert mapper.deadzone == 10  # デフォルト値

    def test_unknown_profile_raises_error(self):
        """未知のプロファイル名でValueErrorが出ること."""
        with pytest.raises(ValueError, match="Unknown profile"):
            Mapper("UnknownDevice")


class TestMapperNormalization:
    """Mapperの正規化・デッドゾーン処理テスト."""

    def test_normalize_stick_min_value(self):
        """normalize: スティック生値0 -> 正規化0."""
        mapper = Mapper("DualShock4")

        snapshot = InputSnapshot(
            buttons={},
            analog={"left_x": 0},
        )

        normalized = mapper.normalize(snapshot)
        assert normalized.analog["left_x"] == 0

    def test_normalize_stick_max_value(self):
        """normalize: スティック生値255 -> 正規化255."""
        mapper = Mapper("DualShock4")

        snapshot = InputSnapshot(
            buttons={},
            analog={"left_x": 255},
        )

        normalized = mapper.normalize(snapshot)
        assert normalized.analog["left_x"] == 255

    def test_normalize_stick_center_value(self):
        """normalize: スティック生値128 -> デッドゾーン内で128."""
        mapper = Mapper("DualShock4", deadzone=10)

        snapshot = InputSnapshot(
            buttons={},
            analog={"left_x": 128},
        )

        normalized = mapper.normalize(snapshot)
        assert normalized.analog["left_x"] == 128

    def test_normalize_stick_near_center_applies_deadzone(self):
        """normalize: スティック中立付近(128±5) -> デッドゾーン適用で128."""
        mapper = Mapper("DualShock4", deadzone=10)

        # 128 + 5 (デッドゾーン内)
        snapshot1 = InputSnapshot(
            buttons={},
            analog={"left_x": 133},
        )
        normalized1 = mapper.normalize(snapshot1)
        assert normalized1.analog["left_x"] == 128

        # 128 - 5 (デッドゾーン内)
        snapshot2 = InputSnapshot(
            buttons={},
            analog={"left_x": 123},
        )
        normalized2 = mapper.normalize(snapshot2)
        assert normalized2.analog["left_x"] == 128

    def test_normalize_stick_outside_deadzone(self):
        """normalize: スティック中立から離れた値(128+15) -> デッドゾーンの外で素通り."""
        mapper = Mapper("DualShock4", deadzone=10)

        # 128 + 15 (デッドゾーンの外)
        snapshot = InputSnapshot(
            buttons={},
            analog={"left_x": 143},
        )

        normalized = mapper.normalize(snapshot)
        assert normalized.analog["left_x"] == 143

    def test_normalize_trigger_min_and_max(self):
        """normalize: トリガー生値0 -> 0、255 -> 255."""
        mapper = Mapper("DualShock4")

        # トリガー最小値
        snapshot_min = InputSnapshot(
            buttons={},
            analog={"L2": 0},
        )
        normalized_min = mapper.normalize(snapshot_min)
        assert normalized_min.analog["L2"] == 0

        # トリガー最大値
        snapshot_max = InputSnapshot(
            buttons={},
            analog={"L2": 255},
        )
        normalized_max = mapper.normalize(snapshot_max)
        assert normalized_max.analog["L2"] == 255


class TestMapperEventMapping:
    """Mapperのイベントマッピングテスト."""

    def test_get_event_mapping_includes_all_types(self):
        """get_event_mapping: ボタン・スティック・トリガー・HATのマッピングが含まれること."""
        mapper = Mapper("DualShock4")
        mapping = mapper.get_event_mapping()

        # ボタンのマッピングが含まれる
        assert (ecodes.BTN_SOUTH, ("cross", "button")) in mapping.items()
        assert (ecodes.BTN_NORTH, ("triangle", "button")) in mapping.items()

        # スティックのマッピングが含まれる
        assert (ecodes.ABS_X, ("left_x", "analog")) in mapping.items()
        assert (ecodes.ABS_Y, ("left_y", "analog")) in mapping.items()

        # トリガーのマッピングが含まれる
        assert (ecodes.ABS_Z, ("L2", "analog")) in mapping.items()
        assert (ecodes.ABS_RZ, ("R2", "analog")) in mapping.items()

        # HAT(十字キー)のマッピングが含まれる
        assert (ecodes.ABS_HAT0X, ("dpad_hat_x", "hat")) in mapping.items()
        assert (ecodes.ABS_HAT0Y, ("dpad_hat_y", "hat")) in mapping.items()
