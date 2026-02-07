"""evdevでDualShockコントローラーを自動検出するモジュール."""

from __future__ import annotations

import evdev


# 対応デバイスのVendor/Product ID
SUPPORTED_DEVICES = {
    (0x054C, 0x09CC): "DualShock4",  # DualShock4 USB
    (0x054C, 0x05C4): "DualShock4",  # DualShock4 旧型
    (0x054C, 0x0CE6): "DualSense",   # DualSense
}


class DualShockDevice:
    """DualShockコントローラーのevdevデバイスラッパー."""

    def __init__(self, device: evdev.InputDevice, profile: str) -> None:
        """デバイスを初期化.

        Args:
            device: evdevのInputDeviceインスタンス
            profile: プロファイル名 ("DualShock4" or "DualSense")
        """
        self._device = device
        self._profile = profile

    @staticmethod
    def detect() -> tuple[DualShockDevice, str] | None:
        """接続されたDualShockコントローラーを検出.

        Returns:
            検出されたデバイスとプロファイル名のタプル。見つからなければNone
        """
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for device in devices:
            vendor = device.info.vendor
            product = device.info.product
            key = (vendor, product)

            if key in SUPPORTED_DEVICES:
                # Touchpad / Motion Sensors ノードをスキップ
                name_lower = device.name.lower()
                if "touchpad" in name_lower or "motion" in name_lower:
                    continue

                profile = SUPPORTED_DEVICES[key]
                return DualShockDevice(device, profile), profile

        return None

    def is_connected(self) -> bool:
        """デバイスが接続中かどうかを確認.

        Returns:
            接続中ならTrue、切断されていればFalse
        """
        try:
            # デバイスのファイルディスクリプタが有効かチェック
            self._device.fd
            return True
        except (OSError, ValueError):
            return False

    def read_event(self) -> evdev.InputEvent | None:
        """evdevイベントを1つ読む（ノンブロッキング対応）.

        Returns:
            読み取ったイベント。イベントがなければNone
        """
        try:
            return self._device.read_one()
        except BlockingIOError:
            return None
        except OSError:
            return None

    def close(self) -> None:
        """デバイスを閉じる."""
        self._device.close()

    @property
    def profile(self) -> str:
        """プロファイル名を取得."""
        return self._profile

    @property
    def name(self) -> str:
        """デバイス名を取得."""
        return self._device.name

    @property
    def path(self) -> str:
        """デバイスパスを取得."""
        return self._device.path
