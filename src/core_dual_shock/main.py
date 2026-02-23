"""メインループとDualShockReaderクラス.

3つの出力方式を提供:
- ライブラリとして: イテレータプロトコルでInputSnapshotをyield
- CLIモード: stdout にJSON行を50Hzで出力
- TKGモード: TKG通信プロトコルでシリアル送信
"""

from __future__ import annotations

import argparse
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

    --port 指定時: TKG通信プロトコルでシリアル送信
    未指定時: stdoutにJSON行を50Hzで出力
    """
    parser = argparse.ArgumentParser(description="DualShock controller reader")
    parser.add_argument(
        "--port", type=str, default=None,
        help="TKG送信用シリアルポート (例: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baudrate", type=int, default=115200,
        help="ボーレート (デフォルト: 115200)",
    )
    parser.add_argument(
        "--hz", type=float, default=5.0,
        help="TKG送信レート [Hz] (デフォルト: 5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="シリアル接続なしでTKGフレームを画面表示（デバッグ用）",
    )
    args = parser.parse_args()

    if args.dry_run:
        _run_tkg_mode(port=None, baudrate=args.baudrate, hz=args.hz)
    elif args.port:
        _run_tkg_mode(args.port, args.baudrate, hz=args.hz)
    else:
        _run_json_mode()


def _run_json_mode():
    """JSON出力モード（従来動作）."""
    try:
        reader = DualShockReader(deadzone=10)

        for snapshot in reader:
            output = {
                "buttons": snapshot.buttons,
                "analog": snapshot.analog,
            }
            print(json.dumps(output), flush=True)

    except KeyboardInterrupt:
        reader.stop()
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_tkg_mode(port: str | None, baudrate: int, hz: float = 5.0):
    """TKG通信プロトコル送信モード.

    Args:
        port: シリアルポート名。Noneの場合はdry-run（画面表示のみ）
        baudrate: ボーレート
        hz: 送信レート [Hz]
    """
    from core_dual_shock.tkg_transmitter import (
        TKGTransmitter,
        _format_wire,
        calc_crc8,
    )

    dry_run = port is None
    transmitter = None
    send_interval = 1.0 / hz
    try:
        reader = DualShockReader(deadzone=10)

        if dry_run:
            transmitter = TKGTransmitter.__new__(TKGTransmitter)
            transmitter._serial = None
            transmitter._timestamp = 0
            transmitter._is_estop = True
            transmitter._wheel_speed = 0
            transmitter._hand_forward = 0
            print(f"TKG dry-run mode (no serial) @ {hz}Hz", file=sys.stderr)
        else:
            transmitter = TKGTransmitter(port, baudrate)
            print(f"TKG mode: {port} @ {baudrate}bps, {hz}Hz", file=sys.stderr)

        # ホイール速度エッジ検出用の前回状態
        prev_wheel_up = 0
        prev_wheel_down = 0
        last_send_time = 0.0
        frame_count = 0
        start_time = time.monotonic()
        prev_send_time = 0.0

        for snapshot in reader:
            buttons = snapshot.buttons

            # ESTOP制御: select(SHARE/Create)で有効化、start(OPTIONS)で解除
            if buttons.get("select", 0):
                transmitter.set_estop(True)
            elif buttons.get("start", 0):
                transmitter.set_estop(False)

            # ホイール速度: dpad_up/downのエッジ検出
            cur_wheel_up = buttons.get("dpad_up", 0)
            cur_wheel_down = buttons.get("dpad_down", 0)
            if cur_wheel_up and not prev_wheel_up:
                transmitter.wheel_speed_up()
            if cur_wheel_down and not prev_wheel_down:
                transmitter.wheel_speed_down()
            prev_wheel_up = cur_wheel_up
            prev_wheel_down = cur_wheel_down

            # 送信レート制御（入力読み取りは50Hz、送信はhzパラメータに従う）
            now = time.monotonic()
            if now - last_send_time < send_interval:
                continue

            # 実測Hz計算
            interval = now - prev_send_time if prev_send_time > 0 else 0.0
            actual_hz = 1.0 / interval if interval > 0 else 0.0
            prev_send_time = now
            last_send_time = now
            frame_count += 1
            elapsed = now - start_time

            # フレーム組み立て
            frame = transmitter.build_frame(snapshot)

            if dry_run:
                _print_decoded_frame(frame, frame_count, elapsed, actual_hz)
            else:
                transmitter.send(frame)

    except KeyboardInterrupt:
        if dry_run:
            elapsed = time.monotonic() - start_time
            print()
            print(
                f"\n--- {frame_count} frames / {elapsed:.1f}s"
                f" (avg {frame_count / elapsed:.2f} Hz) ---",
                file=sys.stderr,
            )
        reader.stop()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if transmitter and not dry_run:
            transmitter.close()


def _print_decoded_frame(
    frame: bytes,
    frame_count: int,
    elapsed: float,
    actual_hz: float,
):
    """パック済みフレームバイト列を逆符号化して表示.

    全フィールドをframe[]から直接デコードすることで、
    エンコード→デコードの往復検証を行う。

    Args:
        frame: 7バイトの論理フレーム
        frame_count: 送信フレーム通番
        elapsed: 開始からの経過時間 [s]
        actual_hz: 直近の実測送信周波数 [Hz]
    """
    from core_dual_shock.tkg_transmitter import _format_wire, calc_crc8

    # --- Byte 0: Header の逆符号化 ---
    hdr = frame[0]
    estop_bit = (hdr >> 7) & 0x01         # 0=ESTOP, 1=通常
    datatype = (hdr >> 5) & 0x03
    timestamp = (hdr >> 2) & 0x07

    estop_str = "  OK " if estop_bit else "ESTOP"

    # --- Byte 1-3: 速度の逆符号化 (unsigned → signed) ---
    vel_x = int.from_bytes([frame[1]], signed=True)
    vel_y = int.from_bytes([frame[2]], signed=True)
    vel_yaw = int.from_bytes([frame[3]], signed=True)

    # --- Byte 4: FIRING の逆符号化 ---
    f = frame[4]
    wheel = (f >> 6) & 0x03
    fire = (f >> 4) & 0x03
    taimatu = (f >> 2) & 0x03
    hand = (f >> 1) & 0x01
    angle = f & 0x01

    # --- Byte 5: OPT2 の逆符号化 ---
    o = frame[5]
    spd_mode = (o >> 7) & 0x01
    mg = (o >> 5) & 0x03

    # --- Byte 6: CRC8 検証 ---
    crc_rx = frame[6]
    crc_calc = calc_crc8(frame)
    crc_str = "OK" if crc_rx == crc_calc else "NG"

    # --- ワイヤーフォーマット ---
    wire = _format_wire(frame).decode("ascii").rstrip()

    # --- 各バイトの16進表示 ---
    hexdump = " ".join(f"{b:02X}" for b in frame)

    print(
        f"\r#{frame_count:<5d} {elapsed:7.1f}s {actual_hz:5.1f}Hz"
        f" [{estop_str}] ts={timestamp}"
        f" vel=({vel_x:+4d},{vel_y:+4d},{vel_yaw:+4d})"
        f" whl={wheel} fire={fire} tai={taimatu} hand={hand} ang={angle}"
        f" spd={spd_mode} mg={mg}"
        f" crc={crc_str}"
        f" [{hexdump}]",
        end="", flush=True,
    )


if __name__ == "__main__":
    cli_main()
