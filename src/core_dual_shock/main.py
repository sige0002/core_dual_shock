"""メインループとDualShockReaderクラス.

2つの出力方式を提供:
- ライブラリとして: イテレータプロトコルでInputSnapshotをyield
- CLIモード: stdout にJSON行を50Hzで出力
"""

from __future__ import annotations

import json
import sys
import threading
import time

from evdev import ecodes

from core_dual_shock.device import DualShockDevice
from core_dual_shock.input_state import InputSnapshot, InputState
from core_dual_shock.mapper import Mapper


class DualShockReader:
    """DualShockコントローラーのイテレータ.

    50Hz周期で正規化済みスナップショットを返す。
    """

    def __init__(self, deadzone: int = 10):
        """デバイス検出、mapper設定、入力状態テーブル初期化.

        Args:
            deadzone: デッドゾーン閾値 (デフォルト: 10)

        Raises:
            RuntimeError: DualShockコントローラーが見つからない場合
        """
        # デバイス検出
        result = DualShockDevice.detect()
        if result is None:
            raise RuntimeError("DualShock controller not found")

        self._device, profile = result
        self._mapper = Mapper(profile, deadzone=deadzone)
        self._input_state = InputState()

        # イベント受信スレッド
        self._running = False
        self._thread: threading.Thread | None = None

    def __iter__(self):
        """イテレータプロトコル."""
        # イベント受信スレッドを開始
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()
        return self

    def __next__(self) -> InputSnapshot:
        """50Hz周期で正規化済みスナップショットを返す.

        Returns:
            正規化済みの入力スナップショット

        Raises:
            StopIteration: stop()が呼ばれた場合
        """
        if not self._running:
            raise StopIteration

        # 50Hz周期 (20ms)
        time.sleep(0.02)

        # デバイス切断チェック
        if not self._device.is_connected():
            self._input_state.reset()

        # スナップショット取得 → 正規化
        snapshot = self._input_state.snapshot()
        return self._mapper.normalize(snapshot)

    def stop(self):
        """安全停止（ニュートラル値出力後に終了）."""
        self._running = False
        # ニュートラル値にリセット
        self._input_state.reset()
        # デバイスをクローズ
        self._device.close()

    def _event_loop(self):
        """イベント受信スレッド.

        evdevイベントを読み続け、input_stateを更新する。
        """
        # イベントマッピング取得
        event_mapping = self._mapper.get_event_mapping()

        while self._running:
            event = self._device.read_event()
            if event is None:
                # イベントがない場合は少し待つ
                time.sleep(0.001)
                continue

            # EV_KEY(ボタン)とEV_ABS(アナログ)のみ処理
            if event.type not in (ecodes.EV_KEY, ecodes.EV_ABS):
                continue

            # イベントコードからチャンネル名と種別を取得
            if event.code not in event_mapping:
                continue

            channel_name, channel_type = event_mapping[event.code]

            # チャンネル種別によって処理を分岐
            if channel_type == "button":
                # ボタンの更新
                self._input_state.update_button(channel_name, event.value)

            elif channel_type == "analog":
                # アナログの更新
                self._input_state.update_analog(channel_name, event.value)

            elif channel_type == "hat":
                # HAT方式の十字キー処理
                self._handle_hat_event(channel_name, event.value)

    def _handle_hat_event(self, hat_channel: str, value: int):
        """HAT方式の十字キーイベントを処理.

        Args:
            hat_channel: "dpad_hat_x" または "dpad_hat_y"
            value: -1, 0, +1
        """
        if hat_channel == "dpad_hat_x":
            # X軸: -1 → left, +1 → right, 0 → 両方0
            if value == -1:
                self._input_state.update_button("dpad_left", 1)
                self._input_state.update_button("dpad_right", 0)
            elif value == 1:
                self._input_state.update_button("dpad_left", 0)
                self._input_state.update_button("dpad_right", 1)
            else:
                self._input_state.update_button("dpad_left", 0)
                self._input_state.update_button("dpad_right", 0)

        elif hat_channel == "dpad_hat_y":
            # Y軸: -1 → up, +1 → down, 0 → 両方0
            if value == -1:
                self._input_state.update_button("dpad_up", 1)
                self._input_state.update_button("dpad_down", 0)
            elif value == 1:
                self._input_state.update_button("dpad_up", 0)
                self._input_state.update_button("dpad_down", 1)
            else:
                self._input_state.update_button("dpad_up", 0)
                self._input_state.update_button("dpad_down", 0)


def cli_main():
    """CLIモードのエントリーポイント.

    stdoutにJSON行を50Hzで出力する。
    """
    try:
        reader = DualShockReader(deadzone=10)

        for snapshot in reader:
            # InputSnapshotをJSON形式に変換
            output = {
                "buttons": snapshot.buttons,
                "analog": snapshot.analog,
            }
            # stdoutに出力
            print(json.dumps(output), flush=True)

    except KeyboardInterrupt:
        # Ctrl+Cで安全終了
        reader.stop()
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
