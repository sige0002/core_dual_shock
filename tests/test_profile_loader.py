"""profile_loaderモジュールの単体テスト."""

import pytest
from evdev import ecodes

from core_dual_shock.profile_loader import (
    _resolve_ecode,
    load_all_profiles,
)


class TestResolveEcode:
    """evdevコード解決のテスト."""

    def test_resolve_string_code(self):
        """文字列のevdevコード名を整数に解決できること."""
        assert _resolve_ecode("ABS_X") == ecodes.ABS_X
        assert _resolve_ecode("BTN_SOUTH") == ecodes.BTN_SOUTH

    def test_resolve_integer_passthrough(self):
        """整数値はそのまま返ること."""
        assert _resolve_ecode(547) == 547

    def test_resolve_unknown_raises_error(self):
        """不明なコード名でValueErrorが出ること."""
        with pytest.raises(ValueError, match="Unknown evdev code"):
            _resolve_ecode("NOT_A_REAL_CODE")


class TestLoadAllProfiles:
    """YAMLプロファイル読み込みのテスト."""

    def test_profiles_contain_dualshock4_and_dualsense(self):
        """DualShock4とDualSenseのプロファイルが読み込まれること."""
        profiles, _ = load_all_profiles()
        assert "DualShock4" in profiles
        assert "DualSense" in profiles

    def test_profile_structure(self):
        """プロファイルの構造がPROFILES互換であること."""
        profiles, _ = load_all_profiles()
        ds4 = profiles["DualShock4"]

        assert "vendor" in ds4
        assert "sticks" in ds4
        assert "triggers" in ds4
        assert "buttons" in ds4
        assert "dpad_type" in ds4
        assert "dpad" in ds4

    def test_sticks_resolved_to_ecodes(self):
        """スティックのコードがevdev整数値に解決されていること."""
        profiles, _ = load_all_profiles()
        ds4 = profiles["DualShock4"]

        assert ds4["sticks"]["left_x"]["code"] == ecodes.ABS_X
        assert ds4["sticks"]["right_x"]["code"] == ecodes.ABS_RX

    def test_buttons_resolved_to_ecodes(self):
        """ボタンのコードがevdev整数値に解決されていること."""
        profiles, _ = load_all_profiles()
        ds4 = profiles["DualShock4"]

        assert ds4["buttons"]["cross"] == ecodes.BTN_SOUTH
        assert ds4["buttons"]["triangle"] == ecodes.BTN_NORTH
        assert ds4["buttons"]["touchpad"] == 547

    def test_triggers_resolved_to_ecodes(self):
        """トリガーのコードがevdev整数値に解決されていること."""
        profiles, _ = load_all_profiles()
        ds4 = profiles["DualShock4"]

        assert ds4["triggers"]["L2"]["code"] == ecodes.ABS_Z
        assert ds4["triggers"]["R2"]["code"] == ecodes.ABS_RZ

    def test_dpad_resolved_to_ecodes(self):
        """十字キーのコードがevdev整数値に解決されていること."""
        profiles, _ = load_all_profiles()
        ds4 = profiles["DualShock4"]

        assert ds4["dpad_type"] == "hat"
        assert ds4["dpad"]["hat_x"] == ecodes.ABS_HAT0X
        assert ds4["dpad"]["hat_y"] == ecodes.ABS_HAT0Y


class TestDeviceMapping:
    """デバイスマッピングのテスト."""

    def test_device_mapping_contains_all_ids(self):
        """全デバイスIDがマッピングに含まれること."""
        _, device_mapping = load_all_profiles()

        assert (0x054C, 0x09CC) in device_mapping  # DS4 USB
        assert (0x054C, 0x05C4) in device_mapping  # DS4 旧型
        assert (0x054C, 0x0CE6) in device_mapping  # DualSense

    def test_device_mapping_correct_profile_names(self):
        """デバイスIDが正しいプロファイル名にマッピングされること."""
        _, device_mapping = load_all_profiles()

        assert device_mapping[(0x054C, 0x09CC)] == "DualShock4"
        assert device_mapping[(0x054C, 0x05C4)] == "DualShock4"
        assert device_mapping[(0x054C, 0x0CE6)] == "DualSense"
